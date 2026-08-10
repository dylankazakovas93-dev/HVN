"""Seekable HTTPS object that transfers only the byte ranges asked for.

Equivalent to `nq_data.remote.HTTPRangeReader`, vendored here so this pipeline
does not depend on a sibling checkout being present. The workspace has been
rolled back repeatedly and an external clone is not a dependency worth having
for forty lines.

PyArrow seeks the Parquet footer, reads the metadata, then fetches only the row
groups it needs, so a 1.9 GB object is usable without downloading it.

**Reads retry.** A scan makes tens of thousands of range requests over many
hours and the host drops one occasionally — a reset connection, a 500, a
timeout. Without a retry that single drop propagates all the way out and kills a
run that is otherwise healthy, which is how the first Stage 7 scan died after
ten sessions. Retrying is safe: a ranged GET is idempotent, so either the same
bytes come back or none do.
"""

from __future__ import annotations

import io
import time
from urllib.parse import urlparse

import requests

RETRIES = 6
BACKOFF_SECONDS = 2
RETRYABLE = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)


class HTTPRangeReader(io.RawIOBase):
    def __init__(self, url: str, timeout: int = 120) -> None:
        if urlparse(url).scheme != "https":
            raise ValueError("Remote Parquet access requires HTTPS")
        self.url = url
        self.timeout = timeout
        self.session = requests.Session()
        probe = self._fetch(0, 0)
        content_range = probe.headers.get("Content-Range", "")
        if "/" not in content_range:
            raise ValueError("Remote server does not support byte-range reads")
        self.size = int(content_range.rsplit("/", 1)[1])
        self.position = 0

    def _fetch(self, start: int, end: int):
        """One ranged GET, retried with exponential backoff.

        The last failure is re-raised rather than swallowed: a host that is
        genuinely gone should still stop the run, just not one that hiccuped.
        A 4xx other than 429 is not retried, because asking again will not fix
        a bad URL or an expired token.
        """
        delay = BACKOFF_SECONDS
        last: Exception | None = None
        for attempt in range(RETRIES):
            try:
                response = self.session.get(
                    self.url,
                    headers={"Range": f"bytes={start}-{end}"},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return response
            except (*RETRYABLE, requests.exceptions.HTTPError) as error:
                status = getattr(getattr(error, "response", None), "status_code", None)
                if status is not None and status != 429 and 400 <= status < 500:
                    raise
                last = error
                if attempt == RETRIES - 1:
                    break
                # A dropped connection usually means the pooled socket is stale,
                # so the session is rebuilt rather than reused.
                self.session.close()
                self.session = requests.Session()
                time.sleep(delay)
                delay *= 2
        raise last

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            position = offset
        elif whence == io.SEEK_CUR:
            position = self.position + offset
        elif whence == io.SEEK_END:
            position = self.size + offset
        else:
            raise ValueError(f"Unsupported whence: {whence}")
        if position < 0:
            raise ValueError("Negative seek position")
        self.position = min(position, self.size)
        return self.position

    def read(self, size: int = -1) -> bytes:
        if self.position >= self.size:
            return b""
        end = (
            self.size - 1
            if size is None or size < 0
            else min(self.position + size - 1, self.size - 1)
        )
        if end < self.position:
            return b""
        payload = self._fetch(self.position, end).content
        self.position += len(payload)
        return payload

    def readinto(self, buffer) -> int:
        payload = self.read(len(buffer))
        buffer[: len(payload)] = payload
        return len(payload)

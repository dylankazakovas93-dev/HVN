"""Seekable HTTPS object that transfers only the byte ranges asked for.

Equivalent to `nq_data.remote.HTTPRangeReader`, vendored here so this pipeline
does not depend on a sibling checkout being present. The workspace has been
rolled back repeatedly and an external clone is not a dependency worth having
for forty lines.

PyArrow seeks the Parquet footer, reads the metadata, then fetches only the row
groups it needs, so a 1.9 GB object is usable without downloading it.
"""

from __future__ import annotations

import io
from urllib.parse import urlparse

import requests


class HTTPRangeReader(io.RawIOBase):
    def __init__(self, url: str, timeout: int = 120) -> None:
        if urlparse(url).scheme != "https":
            raise ValueError("Remote Parquet access requires HTTPS")
        self.url = url
        self.timeout = timeout
        self.session = requests.Session()
        probe = self.session.get(url, headers={"Range": "bytes=0-0"}, timeout=timeout)
        probe.raise_for_status()
        content_range = probe.headers.get("Content-Range", "")
        if "/" not in content_range:
            raise ValueError("Remote server does not support byte-range reads")
        self.size = int(content_range.rsplit("/", 1)[1])
        self.position = 0

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
        response = self.session.get(
            self.url,
            headers={"Range": f"bytes={self.position}-{end}"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.content
        self.position += len(payload)
        return payload

    def readinto(self, buffer) -> int:
        payload = self.read(len(buffer))
        buffer[: len(payload)] = payload
        return len(payload)

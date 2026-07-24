from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from .atr import wilder_atr
from .engine import construct_profile
from .hvn import extract_hvns
from .ledger import write_profile_ledger, write_records
from .models import AllocationMethod, Bar, HvnNode, PeakCandidate, ProfileFamily
from .sessions import profile_window

NY = ZoneInfo("America/New_York")


def _bars_for_window(family: ProfileFamily) -> tuple[list[Bar], object]:
    anchor = date(2025, 1, 8)
    window = profile_window(family, anchor)
    warm_start = window.source_start - timedelta(minutes=30)
    bars: list[Bar] = []
    t = warm_start
    i = 0
    while t < window.source_start:
        t += timedelta(minutes=1)
        center = Decimal("21000")
        bars.append(
            Bar(
                f"SYN-{family.value}-W{i:03d}",
                t,
                center,
                center + Decimal("2"),
                center - Decimal("2"),
                center,
                Decimal("10"),
            )
        )
        i += 1
    fillers = [-8, -6, -4, -2, 2, 4, 6, 8, -7, -3, 3, 7]
    if family == ProfileFamily.PRIOR_RTH:
        offsets = [0] * 36 + fillers * 2
    elif family == ProfileFamily.FULL_OVERNIGHT:
        offsets = [-6] * 22 + [6] * 22 + (fillers + [-5, -1, 1, 5])
    elif family == ProfileFamily.MIDNIGHT:
        offsets = [0] * 24 + [1] * 24 + fillers
    else:
        offsets = [0] * 20 + [2] * 18 + [1] * 10 + fillers
    for ordinal, offset in enumerate(offsets):
        start = window.source_start + timedelta(minutes=ordinal)
        center = Decimal("21000") + Decimal(offset) * Decimal("0.5")
        bars.append(
            Bar(
                f"SYN-{family.value}-S{ordinal:03d}",
                start + timedelta(minutes=1),
                center,
                center,
                center,
                center,
                Decimal("10"),
            )
        )
    return bars, window


def _svg(profile, candidates, nodes, bars) -> str:
    width, height, margin = 900, 560, 50
    weights = [float(b.profile_weight) for b in profile.bins]
    maximum = max(weights)
    bar_h = max(2, 300 / len(weights))
    source = [
        b
        for b in bars
        if profile.window.source_start <= b.start_time < profile.window.source_end
    ]
    candle_min = float(min(b.low for b in source))
    candle_max = float(max(b.high for b in source))
    candle_span = max(0.25, candle_max - candle_min)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="20" y="24" font-family="monospace" font-size="14">{profile.profile_id} | proxy={profile.allocation_method.value} | freeze={profile.window.freeze_time.isoformat()}</text>',
        '<text x="50" y="48" font-family="monospace" font-size="11">synthetic completed 1m source candles; vertical rules = source start/freeze</text>',
        '<line x1="50" y1="55" x2="50" y2="190" stroke="#d62728" stroke-width="2"/>',
        '<line x1="700" y1="55" x2="700" y2="190" stroke="#d62728" stroke-width="2"/>',
    ]
    for n, bar in enumerate(source):
        x = 55 + n * (640 / max(1, len(source) - 1))
        y_high = 185 - (float(bar.high) - candle_min) / candle_span * 120
        y_low = 185 - (float(bar.low) - candle_min) / candle_span * 120
        y_open = 185 - (float(bar.open) - candle_min) / candle_span * 120
        y_close = 185 - (float(bar.close) - candle_min) / candle_span * 120
        color = "#2ca02c" if bar.close >= bar.open else "#d62728"
        parts.append(f'<line x1="{x:.2f}" y1="{y_high:.2f}" x2="{x:.2f}" y2="{y_low:.2f}" stroke="{color}"/>')
        parts.append(f'<rect x="{x-2:.2f}" y="{min(y_open,y_close):.2f}" width="4" height="{max(1,abs(y_close-y_open)):.2f}" fill="{color}"/>')
    parts.append('<text x="50" y="215" font-family="monospace" font-size="11">frozen profile histogram: orange=POC, purple=peak candidate; candidate/node ledgers contain baseline windows and qualification</text>')
    candidate_indices = {c.representative_bin_index for c in candidates}
    node_indices = {
        bin_.bin_index
        for bin_ in profile.bins
        if any(
            node.hvn_low <= bin_.bin_low and bin_.bin_high <= node.hvn_high
            for node in nodes
        )
    }
    for n, (bin_, value) in enumerate(zip(profile.bins, weights)):
        y = 225 + n * bar_h
        length = (value / maximum) * 650
        color = "#4c78a8"
        if bin_.bin_index in candidate_indices:
            color = "#8e44ad"
        if bin_.is_poc:
            color = "#d95f02"
        stroke = "#1b9e77" if bin_.bin_index in node_indices else "none"
        parts.append(f'<rect x="{margin}" y="{y:.2f}" width="{length:.2f}" height="{max(1,bar_h-1):.2f}" fill="{color}" stroke="{stroke}" stroke-width="2"/>')
        parts.append(f'<text x="715" y="{y+bar_h*.75:.2f}" font-family="monospace" font-size="10">{bin_.bin_low}</text>')
    parts.append(f'<text x="20" y="{height-16}" font-family="monospace" font-size="12">ATR@{profile.atr_reference_time.isoformat()}={profile.atr_value} bin={profile.bin_size_rounded} source_vol={profile.source_total_volume} allocated={profile.allocated_total_volume} nodes={len(nodes)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def generate_synthetic_audit_pack(
    output: Path, *, code_sha: str = "UNCOMMITTED"
) -> dict[str, str]:
    output.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for family in ProfileFamily:
        bars, window = _bars_for_window(family)
        points = wilder_atr(bars)
        for method in AllocationMethod:
            profile = construct_profile(
                bars,
                points,
                window,
                method,
                Decimal("0.10"),
                code_sha=code_sha,
                data_partition="synthetic",
            )
            candidates, nodes = extract_hvns(profile, Decimal("1.5"))
            stem = f"{family.value}__{method.value}"
            ledger = output / f"{stem}__profile.csv"
            write_profile_ledger(profile, ledger)
            write_records(
                candidates,
                output / f"{stem}__candidates.csv",
                record_type=PeakCandidate,
            )
            write_records(
                nodes,
                output / f"{stem}__nodes.csv",
                record_type=HvnNode,
            )
            svg = output / f"{stem}__audit.svg"
            svg.write_text(_svg(profile, candidates, nodes, bars), encoding="utf-8")
            hashes[stem] = hashlib.sha256(ledger.read_bytes()).hexdigest()
    manifest = output / "MANIFEST.txt"
    manifest.write_text(
        "\n".join(f"{key},{value}" for key, value in sorted(hashes.items())) + "\n",
        encoding="utf-8",
    )
    return hashes

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum


class AllocationMethod(StrEnum):
    UNIFORM_VOLUME = "uniform_bar_volume"
    TPO = "tpo_range_occupancy"


class ProfileFamily(StrEnum):
    PRIOR_RTH = "prior_rth"
    FULL_OVERNIGHT = "full_overnight"
    MIDNIGHT = "midnight"
    OPENING_HOUR = "opening_hour_rth"


@dataclass(frozen=True, slots=True)
class Bar:
    source_row_id: str
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    symbol: str = "NQ"

    @property
    def start_time(self) -> datetime:
        return self.close_time - timedelta(minutes=1)

    def __post_init__(self) -> None:
        if self.close_time.tzinfo is None:
            raise ValueError("close_time must be timezone-aware")
        if self.low > self.high:
            raise ValueError("low exceeds high")
        if self.volume < 0:
            raise ValueError("volume must be nonnegative")
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            raise ValueError("OHLC is internally inconsistent")
        if not self.symbol.startswith("NQ") or "-" in self.symbol:
            raise ValueError("Bar must represent one outright NQ contract")


@dataclass(frozen=True, slots=True)
class AtrPoint:
    available_time: datetime
    value: Decimal


@dataclass(frozen=True, slots=True)
class ProfileWindow:
    family: ProfileFamily
    source_session_date: str
    source_start: datetime
    source_end: datetime
    freeze_time: datetime

    def __post_init__(self) -> None:
        if not (
            self.source_start.tzinfo
            and self.source_end.tzinfo
            and self.freeze_time.tzinfo
        ):
            raise ValueError("profile window timestamps must be timezone-aware")
        if self.source_end != self.freeze_time:
            raise ValueError("Stage 1 freeze_time must equal exclusive source_end")
        if self.source_start >= self.source_end:
            raise ValueError("empty profile window")


@dataclass(frozen=True, slots=True)
class ProfileBin:
    bin_index: int
    bin_low: Decimal
    bin_high: Decimal
    bin_center: Decimal
    profile_weight: Decimal
    weight_share: Decimal
    cumulative_weight_share: Decimal
    is_poc: bool


@dataclass(frozen=True, slots=True)
class FrozenProfile:
    profile_id: str
    window: ProfileWindow
    allocation_method: AllocationMethod
    atr_reference_time: datetime
    atr_value: Decimal
    bin_ratio: Decimal
    bin_size_raw: Decimal
    bin_size_rounded: Decimal
    profile_range_low: Decimal
    profile_range_high: Decimal
    bins: tuple[ProfileBin, ...]
    poc_bin_index: int
    source_row_ids: tuple[str, ...]
    source_total_volume: Decimal
    allocated_total_volume: Decimal
    code_sha: str
    data_partition: str


@dataclass(frozen=True, slots=True)
class PeakCandidate:
    candidate_id: str
    start_bin_index: int
    end_bin_index: int
    representative_bin_index: int
    peak_price: Decimal
    peak_weight: Decimal
    local_baseline: Decimal | None
    prominence_ratio: Decimal | None
    baseline_bin_indices: tuple[int, ...]
    qualifies: bool
    rejection_reason: str


@dataclass(frozen=True, slots=True)
class HvnNode:
    hvn_id: str
    hvn_low: Decimal
    hvn_high: Decimal
    hvn_center: Decimal
    hvn_width: Decimal
    peak_price: Decimal
    peak_weight: Decimal
    local_baseline: Decimal | None
    prominence_ratio: Decimal | None
    node_total_weight: Decimal
    node_weight_share: Decimal
    node_bin_count: int
    constituent_candidate_ids: tuple[str, ...]
    representative_candidate_id: str

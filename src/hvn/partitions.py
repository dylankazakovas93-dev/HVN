from __future__ import annotations

from pathlib import Path

DEVELOPMENT_YEARS = frozenset({2019, 2021, 2023, 2025, 2026})
FORBIDDEN_YEARS = frozenset({2020, 2022, 2024})


def assert_development_year(year: int) -> None:
    if year not in DEVELOPMENT_YEARS:
        raise PermissionError(f"year {year} is not authorized for Stage 1")


def assert_path_not_forbidden(path: str | Path) -> None:
    text = str(path)
    for year in FORBIDDEN_YEARS:
        if str(year) in text:
            raise PermissionError(f"path names forbidden Stage 1 year {year}")

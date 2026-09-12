"""Per-source data quality assessment and report persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import json
import math
from pathlib import Path
import re
from threading import Lock
from typing import Any

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from farmwise_api.core.utils.coordinates_to_cells import get_s2_cells
from farmwise_api.core.utils.overlap_checks import resolve_range_date
from farmwise_api.core.utils.paths import CACHE_ROOT


DEFAULT_QUALITY_REPORT_DIR = CACHE_ROOT / "quality_reports"
_S2_CACHE_LOCK = Lock()


def bbox_intersects(b1, b2):
    """Return whether two NSEW bounding boxes intersect and their intersection."""
    north1, south1, east1, west1 = b1
    north2, south2, east2, west2 = b2

    north = min(north1, north2)
    south = max(south1, south2)
    east = min(east1, east2)
    west = max(west1, west2)

    if south < north and west < east:
        return True, (north, south, east, west)
    return False, None


def assess_data_quality(df, metadata, ranges, req_ranges):
    """Assess one source response against its advertised and requested coverage."""
    frame = df.copy(deep=False)
    api_bbox = ranges[0]
    api_time = ranges[1]
    api_factors = list(ranges[2])
    api_start = pd.Timestamp(resolve_range_date(api_time[0]))
    api_end = pd.Timestamp(resolve_range_date(api_time[1]))

    req_bbox = req_ranges["bbox"]
    req_level = req_ranges["level"]
    req_start = pd.Timestamp(req_ranges["time_from"])
    req_end = pd.Timestamp(req_ranges["time_to"])
    req_factors = list(req_ranges["factors"])

    intersects, intersection = bbox_intersects(api_bbox, req_bbox)
    expected_cells = (
        set(_get_s2_cells_cached(tuple(intersection), req_level))
        if intersects
        else set()
    )
    returned_cells = (
        set(frame.columns.get_level_values(1).unique())
        if not frame.empty and isinstance(frame.columns, pd.MultiIndex)
        else set()
    )
    expected_factors = sorted(set(api_factors).intersection(req_factors))
    returned_columns = [
        str(value)
        for value in metadata.get(
            "columns",
            _factor_columns(frame),
        )
    ]

    actual_start = max(req_start, api_start)
    actual_end = min(req_end, api_end)
    numeric = (
        frame.copy(deep=False)
        if all(is_numeric_dtype(dtype) for dtype in frame.dtypes)
        else frame.apply(pd.to_numeric, errors="coerce")
    )
    numeric.index = pd.to_datetime(numeric.index)
    numeric = numeric.sort_index()

    daily = _daily_frame(numeric, actual_start, actual_end)
    expected_days = _expected_day_count(actual_start, actual_end)
    report = {
        "api_name": metadata.get("api_name"),
        "source": metadata.get("source", metadata.get("api_name")),
        "S2_level": req_level,
        "expected_s2_cells": len(expected_cells),
        "returned_s2_cells": len(returned_cells),
        "S2_completeness": _rate(
            len(expected_cells.intersection(returned_cells)),
            len(expected_cells),
        ),
        "factor_missing_values": _missing_rate(
            daily, expected_rows=expected_days
        ),
        "factor_missing_value_rates": _factor_missing_rates(
            daily, expected_rows=expected_days
        ),
        "incomplete_day_rate": _missing_day_rate(
            daily, expected_rows=expected_days
        ),
        "expected_start": actual_start.isoformat(),
        "expected_end": actual_end.isoformat(),
        "returned_start": _timestamp_or_none(numeric.index.min()),
        "returned_end": _timestamp_or_none(numeric.index.max()),
        "data_delay": _temporal_gap_hours(
            numeric.index.min(), actual_start, leading=True
        ),
        "data_cutshort": _temporal_gap_hours(
            numeric.index.max(), actual_end, leading=False
        ),
        "factors_expected": expected_factors,
        "factors_returned": returned_columns,
        "factors_returned_completeness": _factor_completeness(
            expected_factors, returned_columns
        ),
    }

    implausible_rates = _implausible_value_rates(
        numeric, api_factors
    )
    report["implausible_value_rates"] = implausible_rates
    report["error_values"] = _mean_or_none(implausible_rates.values())
    return report


def persist_quality_report(
    report: dict[str, Any],
    *,
    output_dir: str | Path | None = None,
    request_id: str,
    source: str,
) -> Path:
    """Persist one JSON quality report and return its path."""
    directory = Path(output_dir or DEFAULT_QUALITY_REPORT_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    safe_source = re.sub(r"[^A-Za-z0-9_.-]+", "_", source).strip("._")
    path = directory / f"{request_id}_{safe_source}.json"
    payload = {
        **report,
        "request_id": request_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    return path


@lru_cache(maxsize=32)
def _get_s2_cells_cached_inner(bbox: tuple, level: int) -> tuple:
    """Cache immutable S2 coverings reused by overlapping source reports."""
    return tuple(get_s2_cells(bbox, level))


def _get_s2_cells_cached(bbox: tuple, level: int) -> tuple:
    """Serialize cache misses so concurrent source reports compute once."""
    with _S2_CACHE_LOCK:
        return _get_s2_cells_cached_inner(bbox, level)


# Expose the inner cache's clear hook on the locking wrapper; assigning an
# attribute to a function is not expressible in the type system.
_get_s2_cells_cached.cache_clear = (  # type: ignore[attr-defined]
    _get_s2_cells_cached_inner.cache_clear
)


def _daily_frame(
    frame: pd.DataFrame,
    expected_start: pd.Timestamp,
    expected_end: pd.Timestamp,
) -> pd.DataFrame:
    if frame.empty or expected_start > expected_end:
        return pd.DataFrame(columns=frame.columns)
    daily = frame.resample("D").mean()
    return daily.loc[
        expected_start.normalize():expected_end.normalize()
    ]


def _expected_day_count(
    expected_start: pd.Timestamp,
    expected_end: pd.Timestamp,
) -> int:
    if expected_start > expected_end:
        return 0
    return (expected_end.normalize() - expected_start.normalize()).days + 1


def _factor_columns(frame: pd.DataFrame) -> list[Any]:
    if frame.empty:
        return []
    if isinstance(frame.columns, pd.MultiIndex):
        return list(frame.columns.get_level_values(0).unique())
    return list(frame.columns.unique())


def _factor_missing_rates(
    frame: pd.DataFrame,
    *,
    expected_rows: int | None = None,
) -> dict[str, float | None]:
    rates: dict[str, float | None] = {}
    for factor in _factor_columns(frame):
        values = (
            frame.xs(factor, axis=1, level=0, drop_level=False)
            if isinstance(frame.columns, pd.MultiIndex)
            else frame[[factor]]
        )
        rates[str(factor)] = _missing_rate(
            values, expected_rows=expected_rows
        )
    return rates


def _missing_rate(
    frame: pd.DataFrame,
    *,
    expected_rows: int | None = None,
) -> float | None:
    rows = frame.shape[0] if expected_rows is None else expected_rows
    expected_values = rows * frame.shape[1]
    if expected_values == 0:
        return None
    returned_values = int(frame.notna().to_numpy().sum())
    return float(1 - min(returned_values, expected_values) / expected_values)


def _missing_day_rate(
    frame: pd.DataFrame,
    *,
    expected_rows: int | None = None,
) -> float | None:
    rows = frame.shape[0] if expected_rows is None else expected_rows
    if rows == 0 or frame.shape[1] == 0:
        return None
    represented_rows = min(frame.shape[0], rows)
    absent_rows = rows - represented_rows
    incomplete_returned_rows = int(frame.isna().any(axis=1).sum())
    return float((absent_rows + incomplete_returned_rows) / rows)


def _factor_completeness(
    expected_factors: list[str],
    returned_columns: list[str],
) -> float | None:
    if not expected_factors:
        return None
    normalized_columns = [_normalize_factor_text(column) for column in returned_columns]
    aliases = {
        "groundwater quantity": (
            "groundwater depth",
            "groundwater level",
            "water table depth",
        ),
        "surface water quantity": (
            "surface water level",
            "water level",
            "flow",
            "discharge",
        ),
        "land cover": (
            "cultivation code",
            "crop code",
            "crop type",
        ),
    }
    matched = {
        factor
        for factor in expected_factors
        if any(
            term in column
            for column in normalized_columns
            for term in (
                _normalize_factor_text(factor),
                *aliases.get(_normalize_factor_text(factor), ()),
            )
        )
    }
    return len(matched) / len(expected_factors)


def _normalize_factor_text(value: Any) -> str:
    """Normalize labels before matching logical factors to output columns."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value).lower()).split())


def _implausible_value_rates(
    frame: pd.DataFrame,
    api_factors: list[str],
) -> dict[str, float | None]:
    rates: dict[str, float | None] = {}
    for factor_value in _factor_columns(frame):
        factor = str(factor_value)
        normalized = factor.lower()
        factor_frame = (
            frame.xs(factor_value, axis=1, level=0, drop_level=False)
            if isinstance(frame.columns, pd.MultiIndex)
            else frame[[factor_value]]
        )
        values = factor_frame.to_numpy().ravel()
        values = values[~pd.isna(values)]
        if not values.size:
            continue
        if "precipitation" in normalized:
            rates[factor] = float(((values < 0) | (values > 500)).mean())
        elif "temperature" in normalized:
            rates[factor] = float(((values < -80) | (values > 80)).mean())

    source_type = api_factors[0] if api_factors else None
    all_values = frame.to_numpy().ravel()
    all_values = all_values[~pd.isna(all_values)]
    if all_values.size:
        negative_only = {
            "soil",
            "hydraulic conductivity",
            "depth to watertable",
            "groundwater quality",
            "groundwater quantity",
            "surface water quality",
            "potential evaporation",
            "surface water quantity",
        }
        if source_type in negative_only:
            rates.setdefault(
                source_type,
                float((all_values < 0).mean()),
            )
        elif source_type == "land cover":
            rates.setdefault(
                source_type,
                float(((all_values < 0) | (all_values > 255)).mean()),
            )
    return rates


def _temporal_gap_hours(
    returned: Any,
    expected: pd.Timestamp,
    *,
    leading: bool,
) -> float | None:
    if pd.isna(returned):
        return None
    returned = pd.Timestamp(returned)
    delta = returned - expected if leading else expected - returned
    return max(0.0, float(delta.total_seconds() / 3600))


def _timestamp_or_none(value: Any) -> str | None:
    return None if pd.isna(value) else pd.Timestamp(value).isoformat()


def _rate(numerator: int, denominator: int) -> float | None:
    return float(numerator / denominator) if denominator else None


def _mean_or_none(values) -> float | None:
    values = [value for value in values if value is not None and math.isfinite(value)]
    return float(np.mean(values)) if values else None


__all__ = [
    "DEFAULT_QUALITY_REPORT_DIR",
    "assess_data_quality",
    "bbox_intersects",
    "persist_quality_report",
]

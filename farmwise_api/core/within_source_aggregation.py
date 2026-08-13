"""Configurable aggregation of records produced by a single data source."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Callable
import warnings

import numpy as np
import pandas as pd

from farmwise_api.core.harmonization import normalize_method_name, resolve_data_type


SUPPORTED_WITHIN_SOURCE_METHODS = frozenset(
    {"mean", "median", "mode", "min", "max", "sum", "first", "last", "nunique"}
)


def validate_within_source_methods(
    methods: Mapping[str, str],
) -> dict[str, str]:
    """Validate and normalize data-type aggregation methods."""
    validated = {}
    for data_type, method in methods.items():
        canonical = normalize_method_name(method)
        if canonical not in SUPPORTED_WITHIN_SOURCE_METHODS:
            supported = ", ".join(sorted(SUPPORTED_WITHIN_SOURCE_METHODS))
            raise ValueError(
                f"Unknown within-source aggregation method '{method}' for "
                f"data type '{data_type}'. Supported methods: {supported}."
            )
        validated[_normalize_label(data_type)] = canonical
    return validated


def aggregate_to_s2(
    frame: pd.DataFrame,
    *,
    group_by: Sequence[str] = ("S2CELL", "Timestamp"),
    logical_data_types: Sequence[str] = (),
    methods: Mapping[str, str],
    column_data_types: Mapping[str, str] | None = None,
    column_aggregations: Mapping[str, str | Callable] | None = None,
    warn_on_aggregation: bool = True,
) -> pd.DataFrame:
    """Collapse records from one source according to a per-data-type policy.

    The returned grouping keys form the index, matching ``DataFrame.groupby``.
    ``column_data_types`` explicitly maps physical source columns to logical
    data types. ``column_aggregations`` is intended for metadata columns such
    as latitude, longitude, or a station count and takes precedence over the
    type policy.
    """
    group_by = list(group_by)
    missing = [column for column in group_by if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing aggregation key columns: {missing}")

    validated_methods = validate_within_source_methods(methods)
    default_method = validated_methods.get("default", "mean")
    explicit_data_types = dict(column_data_types or {})
    overrides = dict(column_aggregations or {})
    aggregations: dict[str, str | Callable] = {}

    for column in frame.columns:
        if column in group_by:
            continue
        if column in overrides:
            aggregation = overrides[column]
            if isinstance(aggregation, str):
                aggregation = _aggregator(normalize_method_name(aggregation))
            aggregations[column] = aggregation
            continue

        data_type = _normalize_label(explicit_data_types[column]) if (
            column in explicit_data_types
        ) else resolve_data_type(
            column,
            logical_data_types,
            validated_methods,
        )
        method = validated_methods.get(data_type, default_method)
        aggregations[column] = _aggregator(method)

    original_size = len(frame)
    if aggregations:
        result = frame.groupby(group_by).agg(aggregations)
    else:
        result = frame[group_by].drop_duplicates().set_index(group_by)

    if warn_on_aggregation and original_size != len(result):
        warnings.warn("Some data were aggregated", stacklevel=2)
    return result


def _aggregator(method: str) -> str | Callable[[pd.Series], Any]:
    if method not in SUPPORTED_WITHIN_SOURCE_METHODS:
        supported = ", ".join(sorted(SUPPORTED_WITHIN_SOURCE_METHODS))
        raise ValueError(
            f"Unknown within-source aggregation method '{method}'. "
            f"Supported methods: {supported}."
        )
    if method == "mode":
        return _mode
    if method in {"first", "last"}:
        return _first_non_null if method == "first" else _last_non_null
    if method == "nunique":
        return "nunique"
    return lambda values: _numeric_aggregate(values, method)


def _numeric_aggregate(values: pd.Series, method: str) -> Any:
    numeric = pd.to_numeric(values, errors="coerce")
    if method == "mean":
        return numeric.mean()
    if method == "median":
        return numeric.median()
    if method == "min":
        return numeric.min()
    if method == "max":
        return numeric.max()
    if method == "sum":
        return numeric.sum(min_count=1)
    raise ValueError(f"Unsupported numeric aggregation method: {method}")


def _mode(values: pd.Series) -> Any:
    modes = values.dropna().mode()
    return modes.iloc[0] if not modes.empty else np.nan


def _first_non_null(values: pd.Series) -> Any:
    values = values.dropna()
    return values.iloc[0] if not values.empty else np.nan


def _last_non_null(values: pd.Series) -> Any:
    values = values.dropna()
    return values.iloc[-1] if not values.empty else np.nan


def _normalize_label(value: Any) -> str:
    return " ".join(str(value).strip().lower().split())


__all__ = [
    "SUPPORTED_WITHIN_SOURCE_METHODS",
    "aggregate_to_s2",
    "validate_within_source_methods",
]

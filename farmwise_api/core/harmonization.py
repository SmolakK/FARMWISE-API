"""Configurable harmonization of overlapping data-source results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
import re
from typing import Any

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype


DEFAULT_SOURCE_WEIGHT = 1.0

_METHOD_ALIASES = {
    "average": "mean",
    "weighted_average": "weighted_mean",
}

SUPPORTED_HARMONIZATION_METHODS = frozenset(
    {
        "weighted_mean",
        "mean",
        "weighted_median",
        "median",
        "weighted_mode",
        "mode",
        "priority",
        "min",
        "max",
        "sum",
    }
)


def normalize_temporal_index(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a shallow copy with one timezone-neutral DatetimeIndex."""
    if isinstance(frame.index, pd.MultiIndex):
        raise ValueError("Source data must use a single temporal index.")
    normalized = frame.copy(deep=False)
    index_name = frame.index.name
    normalized.index = pd.to_datetime(
        frame.index,
        errors="raise",
        utc=True,
    ).tz_convert(None)
    normalized.index.name = index_name
    return normalized


def normalize_method_name(method: str) -> str:
    """Return the canonical spelling of a harmonization method."""
    if not isinstance(method, str):
        raise ValueError("Harmonization method names must be strings.")
    normalized = re.sub(r"[\s-]+", "_", method.strip().lower())
    return _METHOD_ALIASES.get(normalized, normalized)


def validate_source_weights(source_weights: Mapping[str, float]) -> dict[str, float]:
    """Validate and copy source weights."""
    validated = {}
    for source, weight in source_weights.items():
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise ValueError(f"Weight for source '{source}' must be a number.")
        if not math.isfinite(weight) or weight < 0:
            raise ValueError(
                f"Weight for source '{source}' must be finite and non-negative."
            )
        validated[str(source)] = float(weight)
    return validated


def validate_harmonization_methods(
    methods: Mapping[str, str],
) -> dict[str, str]:
    """Validate a data-type-to-method mapping and canonicalize its values."""
    validated = {}
    for data_type, method in methods.items():
        canonical = normalize_method_name(method)
        if canonical not in SUPPORTED_HARMONIZATION_METHODS:
            supported = ", ".join(sorted(SUPPORTED_HARMONIZATION_METHODS))
            raise ValueError(
                f"Unknown harmonization method '{method}' for data type "
                f"'{data_type}'. Supported methods: {supported}."
            )
        validated[_normalize_label(data_type)] = canonical
    return validated


def harmonize_data(
    source_frames: Sequence[tuple[str, pd.DataFrame, Sequence[str]]],
    *,
    source_weights: Mapping[str, float],
    data_type_methods: Mapping[str, str],
) -> pd.DataFrame:
    """Combine source frames using a method chosen separately per data type.

    ``source_frames`` contains ``(source_name, dataframe, logical_data_types)``
    tuples. DataFrames are aligned by timestamp and full column key. Source
    weights are applied only where a source has a non-null observation.
    """
    if not source_frames:
        return pd.DataFrame()

    source_frames = [
        (source, normalize_temporal_index(frame), logical_types)
        for source, frame, logical_types in source_frames
    ]
    weights = validate_source_weights(source_weights)
    methods = validate_harmonization_methods(data_type_methods)
    default_method = methods.get("default", "weighted_mean")
    columns = _ordered_columns(source_frames)
    output_series = []

    for column in columns:
        series_by_source = []
        column_weights = []
        available_types: list[str] = []

        for source, frame, logical_types in source_frames:
            if column not in frame.columns:
                continue
            series = frame[column]
            if isinstance(series, pd.DataFrame):
                series = series.bfill(axis=1).iloc[:, 0]
            series_by_source.append(_collapse_duplicate_index(series).rename(source))
            column_weights.append(weights.get(source, DEFAULT_SOURCE_WEIGHT))
            available_types.extend(logical_types)

        values = pd.concat(series_by_source, axis=1)
        data_type = resolve_data_type(column, available_types, methods)
        method = methods.get(data_type, default_method)
        output_series.append(
            _aggregate(values, column_weights, method).rename(column)
        )

    result = pd.concat(output_series, axis=1).sort_index()
    result.columns = _restore_column_index(source_frames, columns)
    return result


def resolve_data_type(
    column: Any,
    available_types: Sequence[str],
    data_type_methods: Mapping[str, str],
) -> str:
    """Resolve a physical output column to a configurable logical data type."""
    factor = column[0] if isinstance(column, tuple) else column
    normalized_factor = _normalize_label(factor)
    configured_types = [key for key in data_type_methods if key != "default"]

    matches = [
        data_type
        for data_type in configured_types
        if data_type and data_type in normalized_factor
    ]
    if matches:
        return max(matches, key=len)

    normalized_available = {
        _normalize_label(data_type)
        for data_type in available_types
        if _normalize_label(data_type)
    }
    if len(normalized_available) == 1:
        return next(iter(normalized_available))
    return "default"


def _ordered_columns(
    source_frames: Sequence[tuple[str, pd.DataFrame, Sequence[str]]],
) -> list[Any]:
    """Return the union of frame columns while preserving source order."""
    columns = []
    seen = set()
    for _source, frame, _logical_types in source_frames:
        for column in frame.columns:
            if column not in seen:
                seen.add(column)
                columns.append(column)
    return columns


def _restore_column_index(
    source_frames: Sequence[tuple[str, pd.DataFrame, Sequence[str]]],
    columns: Sequence[Any],
) -> pd.Index:
    first_columns = source_frames[0][1].columns
    if isinstance(first_columns, pd.MultiIndex):
        return pd.MultiIndex.from_tuples(columns, names=first_columns.names)
    return pd.Index(columns, name=first_columns.name)


def _collapse_duplicate_index(series: pd.Series) -> pd.Series:
    if not series.index.has_duplicates:
        return series
    if is_numeric_dtype(series.dtype):
        return series.groupby(level=0).mean()
    return series.groupby(level=0).agg(_first_non_null)


def _first_non_null(values: pd.Series) -> Any:
    values = values.dropna()
    return values.iloc[0] if not values.empty else np.nan


def _aggregate(
    values: pd.DataFrame,
    weights: Sequence[float],
    method: str,
) -> pd.Series:
    weight_series = pd.Series(weights, index=values.columns, dtype=float)

    if method == "weighted_mean":
        numeric = values.apply(pd.to_numeric, errors="coerce")
        numerator = numeric.mul(weight_series, axis=1).sum(axis=1, min_count=1)
        denominator = numeric.notna().mul(weight_series, axis=1).sum(axis=1)
        return numerator.div(denominator.replace(0, np.nan))
    if method == "mean":
        return values.apply(pd.to_numeric, errors="coerce").mean(axis=1)
    if method == "weighted_median":
        return values.apply(
            lambda row: _weighted_median(row, weight_series),
            axis=1,
        )
    if method == "median":
        return values.apply(pd.to_numeric, errors="coerce").median(axis=1)
    if method == "weighted_mode":
        return values.apply(
            lambda row: _weighted_mode(row, weight_series),
            axis=1,
        )
    if method == "mode":
        return values.apply(_mode, axis=1)
    if method == "priority":
        priority = sorted(
            range(len(weights)),
            key=lambda position: weights[position],
            reverse=True,
        )
        eligible = [position for position in priority if weights[position] > 0]
        if not eligible:
            return pd.Series(np.nan, index=values.index)
        return values.iloc[:, eligible].bfill(axis=1).iloc[:, 0]

    numeric = values.apply(pd.to_numeric, errors="coerce")
    if method == "min":
        return numeric.min(axis=1)
    if method == "max":
        return numeric.max(axis=1)
    if method == "sum":
        return numeric.sum(axis=1, min_count=1)
    raise ValueError(f"Unsupported harmonization method: {method}")


def _weighted_median(row: pd.Series, weights: pd.Series) -> float:
    numeric = pd.to_numeric(row, errors="coerce")
    valid = numeric.notna() & weights.gt(0)
    if not valid.any():
        return np.nan

    observations = pd.DataFrame(
        {
            "value": numeric[valid].astype(float),
            "weight": weights[valid],
        }
    ).sort_values("value", kind="stable")
    cumulative = observations["weight"].cumsum().to_numpy()
    values = observations["value"].to_numpy()
    half_weight = observations["weight"].sum() / 2
    position = int(np.searchsorted(cumulative, half_weight, side="left"))

    if (
        position + 1 < len(values)
        and math.isclose(cumulative[position], half_weight)
    ):
        return float((values[position] + values[position + 1]) / 2)
    return float(values[position])


def _weighted_mode(row: pd.Series, weights: pd.Series) -> Any:
    scores: dict[Any, float] = {}
    for value, weight in zip(row, weights):
        if pd.isna(value) or weight <= 0:
            continue
        scores[value] = scores.get(value, 0.0) + weight
    return max(scores, key=lambda value: scores[value]) if scores else np.nan


def _mode(row: pd.Series) -> Any:
    modes = row.dropna().mode()
    return modes.iloc[0] if not modes.empty else np.nan


def _normalize_label(value: Any) -> str:
    """Fold a label to a comparable form.

    Hyphens, underscores and slashes become spaces so that a column named
    "CORINE land-cover class code" still matches the configured data type
    "land cover". Without this the match failed whenever another factor was
    requested alongside it, and land cover silently fell back to the default
    weighted mean, averaging class codes into values that are not classes.
    """
    collapsed = re.sub(r"[-_/]+", " ", str(value))
    return " ".join(collapsed.strip().lower().split())


__all__ = [
    "DEFAULT_SOURCE_WEIGHT",
    "SUPPORTED_HARMONIZATION_METHODS",
    "harmonize_data",
    "normalize_method_name",
    "resolve_data_type",
    "validate_harmonization_methods",
    "validate_source_weights",
]

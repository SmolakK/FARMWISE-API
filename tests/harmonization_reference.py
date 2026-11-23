"""The column-by-column harmonization that harmonize_data replaced.

Kept only as an oracle: the vectorised implementation must give the same
result on every method. It is about 1 ms per output column, so it is not
fit for a Europe-wide request (millions of columns).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from farmwise_api.core.harmonization import (
    DEFAULT_SOURCE_WEIGHT,
    normalize_temporal_index,
    resolve_data_type,
    validate_harmonization_methods,
    validate_source_weights,
)


def reference_harmonize_data(
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
        raw_series = []
        column_weights = []
        available_types: list[str] = []

        for source, frame, logical_types in source_frames:
            if column not in frame.columns:
                continue
            series = frame[column]
            if isinstance(series, pd.DataFrame):
                series = series.bfill(axis=1).iloc[:, 0]
            raw_series.append((source, series))
            column_weights.append(weights.get(source, DEFAULT_SOURCE_WEIGHT))
            available_types.extend(logical_types)

        # Resolve the data type before collapsing repeated timestamps, so a
        # categorical column is reduced by its mode. Collapsing first averaged
        # every numeric column, turning CORINE classes 211 and 312 into 261.5.
        data_type = resolve_data_type(column, available_types, methods)
        method = methods.get(data_type, default_method)
        categorical = "mode" in method
        series_by_source = [
            _collapse_duplicate_index(series, categorical=categorical).rename(source)
            for source, series in raw_series
        ]
        values = pd.concat(series_by_source, axis=1)
        output_series.append(
            _aggregate(values, column_weights, method).rename(column)
        )

    result = pd.concat(output_series, axis=1).sort_index()
    result.columns = _restore_column_index(source_frames, columns)
    return result


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


def _collapse_duplicate_index(
    series: pd.Series, *, categorical: bool = False
) -> pd.Series:
    if not series.index.has_duplicates:
        return series
    if categorical:
        return series.groupby(level=0).agg(_series_mode)
    if is_numeric_dtype(series.dtype):
        return series.groupby(level=0).mean()
    return series.groupby(level=0).agg(_first_non_null)


def _series_mode(values: pd.Series) -> Any:
    """Most frequent non-null value; the first on a tie, NaN if none."""
    modes = values.dropna().mode()
    return modes.iloc[0] if not modes.empty else np.nan


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

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

    The frames are reshaped to one long table of observations and reduced
    with grouped operations, one pass per harmonization method. A
    Europe-wide request has millions of (variable, cell) columns; handling
    them one at a time took about a millisecond each, hours in total.
    """
    if not source_frames:
        return pd.DataFrame()

    weights = validate_source_weights(source_weights)
    methods = validate_harmonization_methods(data_type_methods)
    default_method = methods.get("default", "weighted_mean")

    frames = [
        _merge_duplicate_columns(normalize_temporal_index(frame))
        for _source, frame, _types in source_frames
    ]
    source_types = [list(types) for _source, _frame, types in source_frames]
    source_weight = np.array(
        [weights.get(source, DEFAULT_SOURCE_WEIGHT)
         for source, _frame, _types in source_frames],
        dtype=float,
    )

    columns = _union_columns(frames)
    times = _union_times(frames)
    column_positions = [columns.get_indexer(frame.columns) for frame in frames]
    time_positions = [times.get_indexer(frame.index) for frame in frames]
    column_methods = _column_methods(
        columns, column_positions, source_types, methods, default_method
    )

    blocks = []
    block_columns = []
    for method in pd.unique(column_methods):
        in_method = column_methods == method
        group_columns = np.flatnonzero(in_method)
        observations = _observations(
            frames, column_positions, time_positions, in_method,
            n_columns=len(columns), categorical="mode" in method,
        )
        keys, values = _reduce(observations, method, source_weight)
        blocks.append(
            _wide_block(keys, values, times, columns, group_columns,
                        integer=observations.integer)
        )
        block_columns.append(group_columns)

    result = pd.concat(blocks, axis=1)
    order = np.argsort(np.concatenate(block_columns), kind="stable")
    result = result.iloc[:, order]
    result.index = times
    result.columns = _named_columns(columns, frames)
    return result


class _Observations:
    """Non-null values of one method's columns, one row per observation.

    ``key`` is ``time_position * n_columns + column_position``; ``source`` is
    the position of the source in the request, which the order-sensitive
    methods (priority, weighted mode, weighted median ties) depend on.
    """

    def __init__(self, key, source, value, integer):
        self.key = key
        self.source = source
        self.value = value
        self.integer = integer


def _merge_duplicate_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Merge repeated column labels into one, first non-null value wins."""
    if not frame.columns.has_duplicates:
        return frame
    merged = frame.loc[:, ~frame.columns.duplicated()].copy()
    for label in frame.columns[frame.columns.duplicated()].unique():
        merged[label] = frame[label].bfill(axis=1).iloc[:, 0]
    return merged


def _union_columns(frames: Sequence[pd.DataFrame]) -> pd.Index:
    """The union of frame columns, in the order the sources list them."""
    columns = frames[0].columns
    for frame in frames[1:]:
        new = frame.columns.difference(columns, sort=False)
        if len(new):
            columns = columns.append(new)
    return columns


def _union_times(frames: Sequence[pd.DataFrame]) -> pd.DatetimeIndex:
    times = frames[0].index.unique()
    for frame in frames[1:]:
        times = times.union(frame.index.unique(), sort=True)
    names = {frame.index.name for frame in frames}
    return pd.DatetimeIndex(
        times.sort_values(), name=names.pop() if len(names) == 1 else None
    )


def _named_columns(columns: pd.Index, frames: Sequence[pd.DataFrame]) -> pd.Index:
    first = frames[0].columns
    if isinstance(first, pd.MultiIndex):
        if not isinstance(columns, pd.MultiIndex):
            columns = pd.MultiIndex.from_tuples(list(columns))
        return columns.set_names(first.names)
    return pd.Index(columns, name=first.name)


def _column_methods(columns, column_positions, source_types, methods, default_method):
    """The harmonization method of every column, resolved once per kind.

    A column's data type depends on its variable name and on the data types
    of the sources that provide it, so it is resolved once per distinct
    (variable, set of sources) pair rather than once per cell.
    """
    providers = np.zeros(len(columns), dtype=object)
    for position, column_position in enumerate(column_positions):
        providers[column_position] += 1 << position
    factors = (
        columns.get_level_values(0)
        if isinstance(columns, pd.MultiIndex)
        else columns
    )
    kinds, unique_kinds = pd.factorize(
        pd.MultiIndex.from_arrays([factors, providers])
    )
    kind_methods = []
    for factor, provider_bits in unique_kinds:
        available = [
            data_type
            for position, types in enumerate(source_types)
            if provider_bits >> position & 1
            for data_type in types
        ]
        data_type = resolve_data_type(factor, available, methods)
        kind_methods.append(methods.get(data_type, default_method))
    return np.asarray(kind_methods, dtype=object)[kinds]


def _observations(frames, column_positions, time_positions, in_method, *,
                  n_columns, categorical):
    keys, sources, values = [], [], []
    integer = True
    for position, frame in enumerate(frames):
        selected = np.flatnonzero(in_method[column_positions[position]])
        if not selected.size:
            continue
        sub = frame.iloc[:, selected]
        array = sub.to_numpy()
        rows, cols = np.nonzero(~pd.isna(array))
        key = (
            time_positions[position][rows].astype(np.int64) * n_columns
            + column_positions[position][selected][cols]
        )
        value = array[rows, cols]
        if frame.index.has_duplicates:
            numeric = np.array([is_numeric_dtype(dtype) for dtype in sub.dtypes])
            key, value = _collapse_repeated_timestamps(
                key, value, numeric[cols], categorical
            )
        # Checked after collapsing: averaging repeated integers gives floats.
        integer = integer and value.dtype.kind in "iu"
        keys.append(key)
        sources.append(np.full(len(key), position))
        values.append(value)
    if not keys:
        return _Observations(np.empty(0, np.int64), np.empty(0, int),
                             np.empty(0), integer=False)
    return _Observations(np.concatenate(keys), np.concatenate(sources),
                         _concatenate(values), integer)


def _concatenate(arrays):
    if all(array.dtype.kind in "iufb" for array in arrays):
        return np.concatenate(arrays)
    return np.concatenate([array.astype(object) for array in arrays])


def _collapse_repeated_timestamps(key, value, numeric, categorical):
    """Reduce one source's repeated timestamps to one value per cell.

    Categorical columns take the most frequent value, numeric ones the mean
    and anything else its first non-null value.
    """
    if categorical:
        return _mode_by_key(key, value)
    collapsed_keys, collapsed_values = [], []
    if numeric.any():
        means = (
            pd.Series(value[numeric].astype(float))
            .groupby(key[numeric], sort=False).mean()
        )
        collapsed_keys.append(means.index.to_numpy())
        collapsed_values.append(means.to_numpy())
    if (~numeric).any():
        firsts = pd.Series(value[~numeric]).groupby(key[~numeric], sort=False).first()
        collapsed_keys.append(firsts.index.to_numpy())
        collapsed_values.append(firsts.to_numpy())
    return np.concatenate(collapsed_keys), _concatenate(collapsed_values)


def _mode_by_key(key, value, weight=None, first_source=None):
    """Most frequent (or highest-scoring) value per key.

    Ties go to the smallest value, as ``Series.mode`` sorts its result, or,
    when ``first_source`` is given, to the value seen in the earliest source.
    """
    frame = pd.DataFrame({
        "key": key,
        "value": value,
        "score": 1.0 if weight is None else weight,
        "first": 0 if first_source is None else first_source,
    })
    scores = frame.groupby(["key", "value"], sort=False).agg(
        score=("score", "sum"), first=("first", "min")
    ).reset_index()
    tie_break = "value" if first_source is None else "first"
    scores = scores.sort_values(
        ["key", "score", tie_break], ascending=[True, False, True],
        kind="stable",
    ).drop_duplicates("key")
    return scores["key"].to_numpy(), scores["value"].to_numpy()


def _numeric(values) -> np.ndarray:
    if values.dtype.kind in "iufb":
        return values.astype(float)
    return pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)


def _reduce(observations, method, source_weight):
    """One value per key from the observations of every source."""
    key = observations.key
    source = observations.source
    value = observations.value
    weight = source_weight[source] if len(source) else np.empty(0)

    if method in {"mode", "weighted_mode", "priority"}:
        if method == "mode":
            return _mode_by_key(key, value)
        eligible = weight > 0
        key, source, value, weight = (
            key[eligible], source[eligible], value[eligible], weight[eligible]
        )
        if method == "weighted_mode":
            return _mode_by_key(key, value, weight=weight, first_source=source)
        rank = np.empty(len(source_weight), dtype=int)
        rank[np.argsort(-source_weight, kind="stable")] = np.arange(len(source_weight))
        best = pd.DataFrame({"key": key, "rank": rank[source], "value": value})
        best = best.sort_values(["key", "rank"], kind="stable").drop_duplicates("key")
        return best["key"].to_numpy(), best["value"].to_numpy()

    numbers = _numeric(value)
    valid = ~np.isnan(numbers)
    key, numbers, weight, source = (
        key[valid], numbers[valid], weight[valid], source[valid]
    )
    if method == "weighted_mean":
        totals = pd.DataFrame(
            {"weighted": numbers * weight, "weight": weight}
        ).groupby(key, sort=False).sum()
        denominator = totals["weight"].to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            result = np.where(
                denominator > 0, totals["weighted"].to_numpy() / denominator, np.nan
            )
        return totals.index.to_numpy(), result
    if method == "weighted_median":
        return _weighted_median(key, numbers, weight, source)
    grouped = pd.Series(numbers).groupby(key, sort=False)
    reduced = getattr(grouped, method)()
    return reduced.index.to_numpy(), reduced.to_numpy(dtype=float)


def _weighted_median(key, numbers, weight, source):
    """Weighted median per key; an exact half-weight split averages the two."""
    eligible = weight > 0
    key, numbers, weight, source = (
        key[eligible], numbers[eligible], weight[eligible], source[eligible]
    )
    if not len(key):
        return key, numbers
    order = np.lexsort((source, numbers, key))
    key, numbers, weight = key[order], numbers[order], weight[order]
    starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
    ends = np.r_[starts[1:], len(key)]
    group = np.repeat(np.arange(len(starts)), ends - starts)
    cumulative = pd.Series(weight).groupby(group).cumsum().to_numpy()
    half = cumulative[ends - 1][group] / 2
    candidates = np.where(cumulative >= half, np.arange(len(key)), len(key))
    position = np.minimum.reduceat(candidates, starts)
    result = numbers[position].copy()
    has_next = position + 1 < ends
    at_position = cumulative[position]
    half_weight = half[position]
    exact = has_next & (
        np.abs(at_position - half_weight)
        <= 1e-9 * np.maximum(np.abs(at_position), np.abs(half_weight))
    )
    following = np.minimum(position + 1, len(key) - 1)
    result[exact] = (numbers[position][exact] + numbers[following][exact]) / 2
    return key[starts], result


def _wide_block(keys, values, times, columns, group_columns, *, integer):
    """The method's results as a time-by-column frame, NaN where none."""
    n_columns = len(columns)
    rows = keys // n_columns
    local = np.searchsorted(group_columns, keys % n_columns)
    shape = (len(times), len(group_columns))
    values = np.asarray(values)

    if values.dtype.kind in "iufb" or not len(values):
        block = np.full(shape, np.nan)
        block[rows, local] = values
        frame = pd.DataFrame(block)
        if integer and len(values):
            complete = ~np.isnan(block).any(axis=0)
            if complete.any():
                frame = pd.concat(
                    [frame.loc[:, complete].astype(np.int64),
                     frame.loc[:, ~complete]],
                    axis=1,
                ).reindex(columns=frame.columns)
        return frame
    block = np.full(shape, np.nan, dtype=object)
    block[rows, local] = values
    return pd.DataFrame(block).infer_objects()


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

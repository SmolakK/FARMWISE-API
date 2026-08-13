"""Assembly and S2 aggregation helpers for QUADICA."""

from __future__ import annotations

from functools import reduce

import pandas as pd

from farmwise_api.adapters.API_readers.quadica.mappings.quadica_mappings import DATA_ALIASES
from farmwise_api.adapters.API_readers.quadica.utils.extractors import (
    combined_extractions,
    requested_data_files,
)
from farmwise_api.core.within_source_aggregation import aggregate_to_s2


def multi_factor_values(
    data_paths,
    factors,
    spatial_range,
    time_range,
    level,
):
    """Extract every required source file once and merge its variables."""
    requested_files = requested_data_files(factors)
    fragments = []

    for filename, values in requested_files.items():
        fragment = combined_extractions(
            data_paths[filename],
            filename,
            values,
            spatial_range,
            time_range,
            level,
        )
        if fragment is not None and not fragment.empty:
            fragment = fragment.copy()
            fragment["OBJECTID"] = fragment["OBJECTID"].astype(str)
            fragments.append(fragment)

    if not fragments:
        return pd.DataFrame()

    keys = ["OBJECTID", "date", "S2CELL"]
    merged = reduce(
        lambda left, right: pd.merge(left, right, on=keys, how="outer"),
        fragments,
    )
    merged["date"] = pd.to_datetime(merged["date"], errors="raise")
    start, end = map(pd.Timestamp, time_range)
    return merged.loc[merged["date"].between(start, end)].reset_index(drop=True)


def data_aggregation(df, factors, methods):
    """Collapse stations in one S2 cell using the configured type policy.

    Observation-count columns are additive metadata and are always summed;
    concentrations, fluxes, temperature and the other physical variables use
    the method configured for their logical data type.
    """
    if df.empty:
        return pd.DataFrame()

    frame = df.rename(columns={"date": "Timestamp"}).copy()
    value_columns = [
        column
        for column in frame.columns
        if column not in {"OBJECTID", "S2CELL", "Timestamp"}
    ]
    column_data_types = {
        column: DATA_ALIASES[column]
        for column in value_columns
        if column in DATA_ALIASES
    }
    count_aggregations = {
        column: "sum" for column in value_columns if column.startswith("n_")
    }

    return aggregate_to_s2(
        frame.drop(columns=["OBJECTID"], errors="ignore"),
        logical_data_types=factors,
        methods=methods,
        column_data_types=column_data_types,
        column_aggregations=count_aggregations,
    )


def pivoting_table(df):
    """Convert unique S2/timestamp records to FARMWISE's wide format."""
    if df.empty:
        return pd.DataFrame()
    return (
        df.reset_index()
        .pivot(index="Timestamp", columns="S2CELL")
        .sort_index()
        .sort_index(axis=1)
    )


# Backwards-compatible spelling used by the source branch.
data_agregation = data_aggregation


__all__ = [
    "data_aggregation",
    "data_agregation",
    "multi_factor_values",
    "pivoting_table",
]

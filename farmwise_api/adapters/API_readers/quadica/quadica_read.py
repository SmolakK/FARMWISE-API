"""Reader for the QUADICA v1 catchment data set."""

from __future__ import annotations

import asyncio

import pandas as pd

from farmwise_api.adapters.API_readers.quadica.mappings.quadica_mappings import GLOBAL_MAPPING
from farmwise_api.adapters.API_readers.quadica.utils.extractors import requested_data_files
from farmwise_api.adapters.API_readers.quadica.utils.preparation import (
    data_aggregation,
    multi_factor_values,
    pivoting_table,
)
from farmwise_api.adapters.mappings.data_source_mapping import WITHIN_SOURCE_AGGREGATION_METHODS
from farmwise_api.core.utils.paths import adapter_data


def _read_data_sync(
    spatial_range,
    time_range,
    data_range,
    level,
    within_source_aggregation_methods,
):
    """Run the blocking DuckDB/Pandas pipeline in a worker thread."""
    requested_files = requested_data_files(data_range)
    if not requested_files:
        return pd.DataFrame()

    data_paths = {
        filename: adapter_data("quadica", "data", filename)
        for filename in requested_files
    }
    extracted_data = multi_factor_values(
        data_paths,
        data_range,
        spatial_range,
        time_range,
        level,
    )
    if extracted_data.empty:
        return pd.DataFrame()

    aggregated_data = data_aggregation(
        extracted_data,
        data_range,
        within_source_aggregation_methods,
    )
    if aggregated_data.empty:
        return pd.DataFrame()

    pivot_data = pivoting_table(aggregated_data)
    return pivot_data.rename(columns=GLOBAL_MAPPING, level=0)


async def read_data(
    spatial_range,
    time_range,
    data_range,
    level,
    within_source_aggregation_methods=None,
):
    """Read QUADICA v1 values at their native monthly or yearly timestamps.

    Source files are deliberately not bundled in the wheel. They must be
    placed under ``FARMWISE_DATA_DIR/quadica/data`` as documented in
    ``DATA_SETUP.md``.
    """
    methods = (
        within_source_aggregation_methods or WITHIN_SOURCE_AGGREGATION_METHODS
    )
    return await asyncio.to_thread(
        _read_data_sync,
        spatial_range,
        time_range,
        data_range,
        level,
        methods,
    )


__all__ = ["read_data"]

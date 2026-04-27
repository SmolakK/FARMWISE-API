import os
import pandas as pd
from typing import Tuple, List

from API_readers.EuroCropV2.utils.extractors import extract_data_by_bbox, extract_years
from API_readers.EuroCropV2.utils.preparation import data_agregation, data_melting
from API_readers.EuroCropV2.mappings.EuroCropV2_mappings import GLOBAL_MAPPING

async def read_data(
    spatial_range: Tuple[float, float, float, float],
    time_range: Tuple[str, str],
    data_range: List[str],
    level: int
) -> pd.DataFrame:
    """
    Read, filter, and transform EuroCropV2 data into a time-series format.

    This function executes a full data processing pipeline:
    1. Loads raw data from a CSV file.
    2. Filters data within a spatial bounding box.
    3. Selects columns corresponding to a given time range.
    4. Aggregates data into S2 cells.
    5. Transforms yearly data into a daily time series.

    Parameters
    ----------
    spatial_range : tuple of float
        Bounding box defined as (N, S, E, W).
    time_range : tuple of str
        Time range as (start_date, end_date), e.g. ("2018-01-01", "2022-12-31").
    data_range : list of str
        Reserved for future use (e.g., selecting specific variables like 'c', 'cf').
    level : int
        S2 cell level defining spatial resolution.

    Returns
    -------
    pd.DataFrame
        Time-indexed DataFrame with:
        - index: 'Timestamp'
        - columns: MultiIndex (variable, S2CELL)
        - values: numeric data

    Notes
    -----
    - Missing values are converted to NaN during processing.
    - Output is suitable for time-series analysis or visualization.
    - `data_range` is currently unused but kept for API compatibility.
    """

    data_path = os.path.join(
        os.getcwd(),
        "API_readers",
        "EuroCropV2",
        "data",
        "points.csv",
    )

    extracted_data = extract_data_by_bbox(data_path, spatial_range)

    if extracted_data.empty:
        return pd.DataFrame()
    extracted_data = extract_years(extracted_data, time_range)
    aggregated_data = data_agregation(extracted_data, spatial_range, level)

    if aggregated_data.empty:
        return pd.DataFrame()

    melted_data = data_melting(aggregated_data, time_range)
    melted_data = melted_data.rename(columns=GLOBAL_MAPPING, level=0)
    return melted_data
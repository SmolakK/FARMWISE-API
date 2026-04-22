import os
import pandas as pd
from typing import Tuple

from utils.coordinates_to_cells import prepare_coordinates
from API_readers.correctiv.utils.extractors import (
    spatial_extraction, 
    time_extraction, 
    cols_extraction, 
    time_extraction_wide
)
from API_readers.correctiv.utils.preparation import data_melting


async def read_data(
    spatial_range: Tuple[float, float, float, float],
    time_range: Tuple[str, str],
    data_range: Tuple[str, str],  # (niewykorzystywane, ale zostawiam dla kompatybilności)
    level: int
) -> pd.DataFrame:
    """
    Load, filter, aggregate and transform groundwater data into a daily pivot table.

    The function performs a full preprocessing pipeline:
    1. Loads spatial data and clips it to a bounding box.
    2. Filters data by time (with extended range).
    3. Cleans and selects relevant columns.
    4. Assigns spatial S2CELL identifiers.
    5. Aggregates measurements per (S2CELL, month).
    6. Expands monthly data to daily resolution.
    7. Filters again to the exact requested time range.
    8. Returns a pivoted time-series table.

    Parameters
    ----------
    spatial_range : tuple of float (N, S, E, W)
        Bounding box for spatial filtering.
    time_range : tuple of str
        Time range in format ('YYYY-MM-DD', 'YYYY-MM-DD').
    data_range : tuple of str
        Currently unused (reserved for future extensions).
    level : int
        S2 cell level used for spatial aggregation.

    Returns
    -------
    pd.DataFrame
        Pivot table with:
        - index: daily timestamps ('date')
        - columns: MultiIndex (variable, S2CELL)
        - values: groundwater metrics ('min_gwl', 'mean_gwl', 'max_gwl')

    Notes
    -----
    - Monthly values are expanded to daily using step-wise repetition.
    - Aggregation strategy:
        min_gwl → min
        mean_gwl → mean
        max_gwl → max
    - Assumes input data contains 'year' and 'month' columns.
    """

    DATA_PATH = os.path.join(
        os.getcwd(),
        'API_readers', 'correctiv', 'data', 'data_points.parquet'
    )

    data_clipped = spatial_extraction(DATA_PATH, spatial_range)
    date_filtered = time_extraction_wide(data_clipped, time_range)
    date_final = cols_extraction(date_filtered)

    data_with_S2CELL = prepare_coordinates(
        date_final, spatial_range, level
    )
    data_with_S2CELL = data_with_S2CELL[
        ['min_gwl', 'mean_gwl', 'max_gwl', 'S2CELL', 'date']
    ].copy()
    data_agg = (
        data_with_S2CELL
        .groupby(['S2CELL', 'date'], as_index=False)
        .agg({
            'min_gwl': 'min',
            'mean_gwl': 'mean',
            'max_gwl': 'max'
        })
    )

    data_daily = data_melting(data_agg)
    data_daily = time_extraction(data_daily, time_range)

    result = data_daily.pivot_table(
        index='date',
        columns='S2CELL',
        values=['min_gwl', 'mean_gwl', 'max_gwl'],
        aggfunc='first'
    )

    return result
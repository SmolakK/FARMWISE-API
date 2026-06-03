from API_readers.quadica.utils.extractors import (
    files_with_params_extraction,
    combined_extractions
)
import pandas as pd
from functools import reduce


def single_factor_values(
    data_path,
    factor,
    spatial_range,
    time_range,
    level,
    df_list
):
    """
    Extract and append all dataset fragments for a single factor.

    Parameters
    ----------
    data_path : str
        Base directory of dataset files.
    factor : str
        Logical factor name.
    spatial_range : tuple
        Bounding box (north, south, east, west).
    time_range : tuple
        Time range for filtering data.
    level : int
        Spatial resolution level.
    df_list : list
        Accumulator list for extracted DataFrames.

    Returns
    -------
    list
        Updated list containing extracted DataFrames.
    """
    files = files_with_params_extraction(factor=factor)

    for file, values in files.items():
        df_list.append(
            combined_extractions(
                data_path,
                file,
                values,
                spatial_range,
                time_range,
                level
            )
        )

    return df_list


def multi_factor_values(
    data_path,
    factors,
    spatial_range,
    time_range,
    level
):
    """
    Extract and merge multiple factors into a single dataset.

    Performs:
    1. Extraction per factor
    2. Outer merge across all datasets
    3. Temporal filtering
    4. Cleanup of metadata columns

    Parameters
    ----------
    data_path : str
        Base directory of dataset files.
    factors : list
        List of factor names to extract.
    spatial_range : tuple
        Bounding box (north, south, east, west).
    time_range : tuple
        Time range for filtering data.
    level : int
        Spatial resolution level.

    Returns
    -------
    pd.DataFrame
        Merged dataset containing all selected factors.
    """
    df_list = []

    for factor in factors:
        df_list = single_factor_values(
            data_path,
            factor,
            spatial_range,
            time_range,
            level,
            df_list
        )

    keys = ["OBJECTID", "lat", "lon", "date", "S2CELL"]

    df_all = reduce(
        lambda left, right: pd.merge(left, right, on=keys, how="outer"),
        df_list
    )

    df_cut = df_all[
        (df_all["date"] >= time_range[0]) &
        (df_all["date"] <= time_range[1])
    ]

    df_cut = df_cut.drop(columns=['OBJECTID', 'lat', 'lon'])

    return df_cut


def data_agregation(df):
    """
    Aggregate dataset by S2 cell and date.

    Computes mean values for all numeric columns.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataset.

    Returns
    -------
    pd.DataFrame
        Aggregated dataset grouped by S2CELL and date.
    """
    return (
        df.groupby(['S2CELL', 'date'], as_index=False)
          .mean(numeric_only=True)
    )


def pivoting_table(df):
    """
    Pivot time-series dataset into matrix form.

    Converts rows into a matrix where:
    - index = Timestamp
    - columns = S2CELL

    Parameters
    ----------
    df : pd.DataFrame
        Input aggregated dataset.

    Returns
    -------
    pd.DataFrame
        Pivoted dataset in wide format.
    """
    df = df.rename(columns={"date": "Timestamp"})

    return df.pivot_table(
        index="Timestamp",
        columns="S2CELL"
    )
import geopandas
import pandas as pd
import duckdb
import os

from API_readers.quadica.utils.definition import DATA_FRAME, DATA_RANGES
from API_readers.quadica.mappings.quadica_mappings import (
    PARAMETER_VALUES,
    DATA_ALIASES,
    GLOBAL_MAPPING
)
from utils.coordinates_to_cells import prepare_coordinates


def files_with_params_extraction(factor):
    """
    Map a factor to available data files and corresponding parameters.

    Parameters
    ----------
    factor : str
        Logical factor name defined in DATA_ALIASES.

    Returns
    -------
    dict
        Dictionary mapping file identifiers to lists of parameters
        belonging to each file. Empty keys are removed.
    """
    factor_params = [k for k, v in DATA_ALIASES.items() if v == factor]

    data_files = {k: None for k in DATA_RANGES.keys()}

    for key, value in DATA_RANGES.items():
        params_in_file = [x for x in factor_params if x in value]

        if params_in_file:
            data_files[key] = params_in_file
        else:
            del data_files[key]

    return data_files


def expand_monthly_to_daily(df, date_col="date"):
    """
    Expand monthly data to daily resolution.

    Each monthly record is duplicated across all days
    within the corresponding month.

    Parameters
    ----------
    df : pd.DataFrame
        Input monthly DataFrame containing a date column.
    date_col : str, optional
        Name of the date column (default is "date").

    Returns
    -------
    pd.DataFrame
        Daily-expanded DataFrame.
    """
    df = df.copy()

    df[date_col] = pd.to_datetime(df[date_col])
    df["year"] = df[date_col].dt.year
    df["month"] = df[date_col].dt.month

    result = []

    for (obj, year, month), g in df.groupby(["OBJECTID", "year", "month"]):

        start = f"{year}-{month:02d}-01"
        end = pd.to_datetime(start) + pd.offsets.MonthEnd(0)

        daily_dates = pd.date_range(start, end, freq="D")

        tmp = pd.DataFrame({"date": daily_dates})

        row = g.iloc[0]

        for col in df.columns:
            if col not in ["date", "year", "month"]:
                tmp[col] = row[col]

        result.append(tmp)

    return pd.concat(result, ignore_index=True)


def expand_yearly_to_daily(df):
    """
    Expand yearly data to daily resolution.

    Each yearly record is duplicated across all days
    within that year.

    Parameters
    ----------
    df : pd.DataFrame
        Input yearly DataFrame containing a Year column.

    Returns
    -------
    pd.DataFrame
        Daily-expanded DataFrame.
    """
    df = df.copy()

    df["Year"] = pd.to_datetime(df["Year"].astype(str) + "-01-01")
    df["year"] = df["Year"].dt.year

    result = []

    for (obj, year), g in df.groupby(["OBJECTID", "year"]):

        daily_dates = pd.date_range(
            f"{year}-01-01",
            f"{year}-12-31",
            freq="D"
        )

        tmp = pd.DataFrame({"date": daily_dates})

        row = g.iloc[0]

        for col in df.columns:
            if col not in ["Year", "year"]:
                tmp[col] = row[col]

        result.append(tmp)

    return pd.concat(result, ignore_index=True)


def combined_extractions(data_path, file, values, spatial_range, time_range, level):
    """
    Dispatch extraction method based on file type configuration.

    Parameters
    ----------
    data_path : str
        Base directory for dataset files.
    file : str
        File identifier.
    values : list
        List of variables to extract.
    spatial_range : tuple
        Bounding box (north, south, east, west).
    time_range : tuple
        Time range for filtering data.
    level : int
        Spatial resolution level.

    Returns
    -------
    pd.DataFrame
        Extracted and processed dataset.
    """
    file_path = os.path.join(data_path, file)

    if DATA_FRAME[file] == 'year_vertical':
        return year_vertical_extraction(file_path, values, spatial_range, time_range, level)
    if DATA_FRAME[file] == 'date_vertical':
        return date_vertical_extraction(file_path, values, spatial_range, time_range, level)
    if DATA_FRAME[file] == 'monthly_horizontal':
        return monthly_horizontal_extraction(file_path, spatial_range, time_range, level)


def monthly_horizontal_extraction(data_path, spatial_range, time_range, level):
    """
    Extract and transform monthly horizontal dataset to daily resolution.

    Uses DuckDB for fast CSV filtering and then expands
    monthly values to daily granularity.

    Returns
    -------
    pd.DataFrame
        Daily-expanded dataset.
    """
    north, south, east, west = spatial_range

    start = pd.Timestamp(time_range[0]) - pd.DateOffset(months=2)
    end = pd.Timestamp(time_range[1]) + pd.DateOffset(months=2)

    with duckdb.connect() as con:
        cols_info = con.execute(
            f"DESCRIBE SELECT * FROM read_csv('{data_path}')"
        ).fetchall()
        columns = [c[0] for c in cols_info]

    base_cols = ["OBJECTID", "lat", "lon"]

    date_cols = [
        c for c in columns
        if c not in base_cols
        and pd.Timestamp(c) >= start
        and pd.Timestamp(c) <= end
    ]

    all_cols = base_cols + date_cols
    columns_sql = ", ".join([f'"{c}"' for c in all_cols])

    query = f"""
    SELECT {columns_sql}
    FROM read_csv('{data_path}')
    WHERE lat BETWEEN {south} AND {north}
      AND lon BETWEEN {west} AND {east}
    """

    with duckdb.connect() as con:
        result = con.execute(query).df()

    value_col_name = os.path.basename(data_path).split('_')[0]

    df_long = result.melt(
        id_vars=["OBJECTID", "lat", "lon"],
        var_name="date",
        value_name=value_col_name
    )

    df_long["date"] = pd.to_datetime(df_long["date"])
    df_long = prepare_coordinates(df_long, spatial_range, level)

    return expand_monthly_to_daily(df_long)


def date_vertical_extraction(data_path, values, spatial_range, time_range, level):
    """
    Extract date-based vertical dataset and expand to daily resolution.

    Returns
    -------
    pd.DataFrame
        Daily-expanded dataset.
    """
    north, south, east, west = spatial_range

    columns = ', '.join(['OBJECTID', 'date', 'lat', 'lon'] + values)
    date_from = time_range[0]
    date_to = time_range[1]

    with duckdb.connect() as con:
        query = f"""
        SELECT {columns}
        FROM read_csv('{data_path}')
        WHERE lat BETWEEN {south} AND {north}
          AND lon BETWEEN {west} AND {east}
          AND date BETWEEN
            DATE '{date_from}' - INTERVAL 2 MONTHS
            AND DATE '{date_to}' + INTERVAL 2 MONTHS
        """
        result = con.execute(query).df()

    result = prepare_coordinates(result, spatial_range, level)
    return expand_monthly_to_daily(result)


def year_vertical_extraction(data_path, values, spatial_range, time_range, level):
    """
    Extract yearly dataset and expand to daily resolution.

    Returns
    -------
    pd.DataFrame
        Daily-expanded dataset.
    """
    north, south, east, west = spatial_range

    columns = ', '.join(['OBJECTID', 'Year', 'lat', 'lon'] + values)

    year_from, year_to = (int(t[:4]) for t in time_range)
    year_from -= 1
    year_to += 1

    with duckdb.connect() as con:
        query = f"""
        SELECT {columns}
        FROM read_csv('{data_path}')
        WHERE lat BETWEEN {south} AND {north}
          AND lon BETWEEN {west} AND {east}
          AND Year BETWEEN {year_from} AND {year_to}
        """
        result = con.execute(query).df()

    result = prepare_coordinates(result, spatial_range, level)
    return expand_yearly_to_daily(result)


def temporal_extraction(data, timerange):
    """
    Filter melted dataset by a given time range.

    Parameters
    ----------
    data : pd.DataFrame
        Input melted dataset with a date column.
    timerange : tuple
        Start and end date range.

    Returns
    -------
    pd.DataFrame
        Filtered dataset (not implemented).
    """
    # logika wycinajaca konkretny zakres z melted danych
    pass
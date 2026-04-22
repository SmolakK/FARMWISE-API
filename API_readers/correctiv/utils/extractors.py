import pandas as pd
import geopandas as gpd


def spatial_extraction(
        data: str,
        spatial_range: tuple
    ) -> gpd.GeoDataFrame:
    """
    Load spatial data from a parquet file and clip it to a bounding box.

    Additionally creates a monthly datetime column based on 'year' and 'month'.

    Parameters
    ----------
    data : str or os.PathLike
        Path to the input parquet file.
    spatial_range : tuple of float (N, S, E, W)
        Bounding box defined as (North, South, East, West).

    Returns
    -------
    gpd.GeoDataFrame
        Clipped GeoDataFrame with an added 'date' column (datetime64[ns]),
        representing the first day of each month.

    Notes
    -----
    - Uses GeoPandas `.cx` indexer for spatial filtering.
    - Returns a copy to avoid SettingWithCopyWarning.
    """
    gdf = gpd.read_parquet(data)

    N, S, E, W = spatial_range
    bbox = (W, S, E, N)
    gdf_clipped = gdf.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]].copy()

    gdf_clipped['date'] = pd.to_datetime(
        gdf_clipped[['year', 'month']].assign(day=1)
    )

    return gdf_clipped


def time_extraction_wide(
        data: pd.DataFrame,
        time_range: tuple
    ) -> pd.DataFrame:
    """
    Filter data by time range with an extended buffer of ±1 month.

    Parameters
    ----------
    data : pd.DataFrame
        Input DataFrame containing a 'date' column.
    time_range : tuple of str
        Start and end date in format ('YYYY-MM-DD', 'YYYY-MM-DD').

    Returns
    -------
    pd.DataFrame
        Filtered DataFrame including data within the extended time range.

    Notes
    -----
    - Expands the range by subtracting one month from TIME_FROM
      and adding one month to TIME_TO.
    - Useful for later interpolation or temporal expansion.
    """
    TIME_FROM = pd.to_datetime(time_range[0]) - pd.DateOffset(months=1)
    TIME_TO   = pd.to_datetime(time_range[1]) + pd.DateOffset(months=1)

    df_filtered = data[
        (data['date'] >= TIME_FROM) &
        (data['date'] <= TIME_TO)
    ].copy()

    return df_filtered

def time_extraction(
        data: pd.DataFrame,
        timerange: tuple
    ) -> pd.DataFrame:
    """
    Filter data strictly within a given time range.

    Parameters
    ----------
    data : pd.DataFrame
        Input DataFrame containing a 'date' column.
    timerange : tuple of str
        Start and end date in format ('YYYY-MM-DD', 'YYYY-MM-DD').

    Returns
    -------
    pd.DataFrame
        Filtered DataFrame containing only rows within the specified range.

    Notes
    -----
    - Does not extend the time range (unlike time_extraction_wide).
    """
    TIME_FROM = pd.to_datetime(timerange[0])
    TIME_TO   = pd.to_datetime(timerange[1])
    date_extracted = data[
        (data['date'] >= TIME_FROM) &
        (data['date'] <= TIME_TO)
    ]
    return date_extracted

def cols_extraction(data: pd.DataFrame) -> pd.DataFrame:
    """
    Select and clean relevant columns for further processing.

    Renames coordinate columns and ensures numeric types for groundwater data.

    Parameters
    ----------
    data : pd.DataFrame
        Input DataFrame containing groundwater and coordinate data.

    Returns
    -------
    pd.DataFrame
        Cleaned DataFrame with columns:
        ['min_gwl', 'mean_gwl', 'max_gwl', 'lat', 'lon', 'date'].

    Notes
    -----
    - Converts 'min_gwl', 'mean_gwl', 'max_gwl' to numeric (NaN if invalid).
    - Renames 'latitude' → 'lat' and 'longitude' → 'lon'.
    - Returns a copy to avoid chained assignment issues.
    """
    data = data.rename(
        columns={'latitude': 'lat', 'longitude': 'lon'}
    )
    data_cols = ['min_gwl', 'mean_gwl', 'max_gwl']
    data[data_cols] = data[data_cols].apply(pd.to_numeric, errors='coerce')
    return data[['min_gwl', 'mean_gwl', 'max_gwl', 'lat', 'lon', 'date']].copy()
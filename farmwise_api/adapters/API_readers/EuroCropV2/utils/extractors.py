import pandas as pd
import duckdb


def extract_data_by_bbox(path:str, spatial_range:tuple) -> pd.DataFrame:
    """
    Extract data from a CSV file within a given geographic bounding box.

    The function uses DuckDB to efficiently query a CSV file and filter rows
    based on latitude and longitude constraints.

    Parameters
    ----------
    path : str
        Path to the input CSV file.
    spatial_range : tuple of float
        Bounding box defined as (N, S, E, W), where:
        - N : North latitude (max latitude)
        - S : South latitude (min latitude)
        - E : East longitude (max longitude)
        - W : West longitude (min longitude)

    Returns
    -------
    pd.DataFrame
        DataFrame containing rows within the specified bounding box.

    Notes
    -----
    - This function assumes the CSV file contains 'lat' and 'lon' columns.
    - DuckDB is used for performance when working with large files.
    """

    north, south, east, west = spatial_range

    with duckdb.connect() as con:
        # A small number of source rows can be truncated. Skipping only those
        # malformed records keeps a multi-gigabyte import usable without
        # padding corrupt values into the scientific columns.
        source = con.read_csv(
            path,
            strict_mode=False,
            ignore_errors=True,
        )
        result = source.filter(
            f"lat BETWEEN {float(south)!r} AND {float(north)!r} "
            f"AND lon BETWEEN {float(west)!r} AND {float(east)!r}"
        ).df()

    return result


def extract_years(df: pd.DataFrame, time_range:tuple) -> pd.DataFrame:
    """
    Extract columns corresponding to a given year range from a DataFrame.

    The function selects longitude, latitude, and all columns whose names
    end with years falling within the specified range. It also ensures that
    missing values are represented as NaN instead of None.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame containing spatial and temporal data.
    time_range : tuple of str
        Tuple specifying the time range (start, end), where each value
        contains at least the year (e.g., "2018-01-01").

    Returns
    -------
    pd.DataFrame
        Filtered DataFrame containing:
        - 'lon', 'lat'
        - columns matching the selected year range

    Notes
    -----
    - Cultivation columns follow the ``cYYYY`` convention. Source parcel-ID
      columns (``cfYYYY``) are deliberately excluded.
    - All None values are converted to NaN for compatibility with numeric operations.
    """

    base_cols = ["lon", "lat"]

    year_from, year_to = (int(t[:4]) for t in time_range)
    years = tuple(str(year) for year in range(year_from, year_to + 1))

    # ``cYYYY`` contains the cultivation class. ``cfYYYY`` is the source
    # parcel identifier and must not be exposed as an environmental factor.
    year_cols = [
        col
        for col in df.columns
        if col.startswith("c") and col[1:] in years
    ]

    result = df[base_cols + year_cols].copy()

    # Ensure missing values are represented as NaN instead of None
    result = result.replace({None: float("nan")})

    return result

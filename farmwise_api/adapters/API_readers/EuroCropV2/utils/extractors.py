from collections.abc import Iterator

import pandas as pd
import duckdb

# DuckDB vectors are 2048 rows: 512 of them is about a million rows a chunk,
# a few hundred MB of pandas objects at most.
CHUNK_VECTORS = 512


def _read_options() -> str:
    # A small number of source rows can be truncated. Skipping only those
    # malformed records keeps a multi-gigabyte import usable without padding
    # corrupt values into the scientific columns.
    return "strict_mode = false, ignore_errors = true"


def requested_year_columns(columns, time_range: tuple) -> list[str]:
    """The ``cYYYY`` cultivation columns of ``columns`` inside ``time_range``.

    ``cfYYYY`` (the source parcel identifier) is never included.
    """
    year_from, year_to = (int(t[:4]) for t in time_range)
    years = {str(year) for year in range(year_from, year_to + 1)}
    return [
        col for col in columns
        if col.startswith("c") and col[1:] in years
    ]


def iter_cultivation_chunks(
    path: str,
    spatial_range: tuple,
    time_range: tuple,
    chunk_vectors: int = CHUNK_VECTORS,
) -> Iterator[pd.DataFrame]:
    """Yield the points inside the box in chunks: ``lon``, ``lat`` and the
    requested ``cYYYY`` columns only.

    ``extract_data_by_bbox`` loads every column at once. For a Europe-wide box
    that is the whole 46-million-row file with 37 text columns, which ran out
    of memory; this reads only the columns a request uses, a million rows at a
    time.
    """
    north, south, east, west = spatial_range
    with duckdb.connect() as con:
        source = f"read_csv($path, {_read_options()})"
        columns = [
            row[0]
            for row in con.execute(
                f"DESCRIBE SELECT * FROM {source}", {"path": str(path)}
            ).fetchall()
        ]
        selected = ["lon", "lat", *requested_year_columns(columns, time_range)]
        select_list = ", ".join('"' + column + '"' for column in selected)
        con.execute(
            f"SELECT {select_list} FROM {source} "
            "WHERE lat BETWEEN $south AND $north AND lon BETWEEN $west AND $east",
            {
                "path": str(path),
                "south": float(south), "north": float(north),
                "west": float(west), "east": float(east),
            },
        )
        while True:
            chunk = con.fetch_df_chunk(chunk_vectors)
            if chunk.empty:
                return
            yield chunk


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
        # See _read_options: truncated rows are skipped, not padded.
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

    # ``cYYYY`` contains the cultivation class. ``cfYYYY`` is the source
    # parcel identifier and must not be exposed as an environmental factor.
    year_cols = requested_year_columns(df.columns, time_range)

    result = df[base_cols + year_cols].copy()

    # Ensure missing values are represented as NaN instead of None
    result = result.replace({None: float("nan")})

    return result

import pandas as pd
from utils.coordinates_to_cells import prepare_coordinates

def data_agregation(extracted_data, spatial_range, level):
    """
    Aggregate spatial data into S2 cells and compute representative values.

    The function maps coordinates to S2 cells and aggregates data per cell
    using the statistical mode (most frequent value). If no mode is found,
    None is returned for that group.

    Parameters
    ----------
    extracted_data : pd.DataFrame
        Input DataFrame containing at least spatial coordinates and values.
    spatial_range : tuple of float
        Bounding box defined as (N, S, E, W).
    level : int
        S2 cell level defining spatial resolution.

    Returns
    -------
    pd.DataFrame
        Aggregated DataFrame indexed by 'S2CELL', where each value represents
        the mode of the original data within the cell.

    Notes
    -----
    - Uses `prepare_coordinates` to assign S2 cell identifiers.
    - Mode is used instead of mean to preserve categorical or discrete data.
    """

    df = prepare_coordinates(extracted_data, spatial_range, level)

    df = (
        df.set_index("S2CELL")
        .groupby(level=0)
        .agg(lambda x: x.mode().iloc[0] if not x.mode().empty else None)
    )

    return df


def data_melting(df, time_range):
    """
    Transform wide-format temporal data into a daily time series format.

    The function reshapes a DataFrame containing yearly values (e.g., c2018, cf2020)
    into a long format, expands it to daily frequency, and pivots it into a
    time-indexed structure.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame indexed by 'S2CELL', containing:
        - spatial columns ('lon', 'lat')
        - yearly columns (e.g., 'c2018', 'cf2020')
    time_range : tuple of str
        Tuple specifying the time range (start, end), e.g. ("2018-01-01", "2022-12-31").

    Returns
    -------
    pd.DataFrame
        Pivoted DataFrame with:
        - index: 'Timestamp' (daily frequency)
        - columns: MultiIndex ('c', 'cf') x S2CELL
        - values: numeric data

    Notes
    -----
    - Missing values are coerced to NaN.
    - Yearly values are expanded to daily resolution by repetition.
    - Uses 'first' aggregation when pivoting (data assumed constant per year).
    """

    # --- reshape wide -> long ---
    df_long = (
        pd.wide_to_long(
            df.reset_index(),
            stubnames=["c", "cf"],
            i=["S2CELL", "lon", "lat"],
            j="year",
            sep="",
            suffix=r"\d+",
        )
        .reset_index()
        .set_index("S2CELL")
    )

    # --- ensure numeric types (critical for later aggregations) ---
    df_long[["c", "cf"]] = df_long[["c", "cf"]].apply(
        pd.to_numeric, errors="coerce"
    )

    # --- generate full date range ---
    start_date, end_date = pd.to_datetime(time_range)
    all_dates = pd.date_range(start=start_date, end=end_date)

    daily_frames = []

    # --- expand yearly data to daily ---
    for year, group in df_long.groupby("year"):
        year_dates = all_dates[all_dates.year == year]

        if year_dates.empty:
            continue

        repeated = group.loc[group.index.repeat(len(year_dates))].copy()
        repeated["Timestamp"] = list(year_dates) * len(group)

        daily_frames.append(repeated)

    # --- combine all years ---
    df_daily = pd.concat(daily_frames)

    # --- cleanup ---
    df_daily = (
        df_daily.drop(columns=["lat", "lon", "year"])
        .sort_values(["S2CELL", "Timestamp"])
    )

    # --- pivot to final structure ---
    return df_daily.pivot_table(
        index="Timestamp",
        columns="S2CELL",
        values=["c", "cf"],
        aggfunc="first",
    )
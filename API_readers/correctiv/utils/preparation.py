import pandas as pd

def data_melting(data: pd.DataFrame) -> pd.DataFrame:
    """
    Expand monthly groundwater data to daily resolution.

    For each unique combination of ('S2CELL', 'date'), where 'date' represents
    the first day of a month, the function generates daily records by repeating
    the monthly values across all days within that month.

    Parameters
    ----------
    data : pd.DataFrame
        Input DataFrame containing at least the following columns:
        - 'S2CELL' : spatial cell identifier
        - 'date'   : datetime64[ns], expected to be the first day of a month
        - 'min_gwl', 'mean_gwl', 'max_gwl' : numeric groundwater values

    Returns
    -------
    pd.DataFrame
        DataFrame expanded to daily frequency with columns:
        - 'S2CELL'
        - 'date' (daily timestamps)
        - 'min_gwl', 'mean_gwl', 'max_gwl'

    Notes
    -----
    - Each monthly value is repeated for all days within its month.
    - Assumes that each ('S2CELL', 'date') group contains a single row.
    - If multiple rows exist per group, only the first one is used.
    - No interpolation is performed (step-wise constant values).
    """
    daily_frames = []

    for (cell, date), group in data.groupby(['S2CELL', 'date']):
        value = group.iloc[0]

        days = pd.date_range(
            start=date,
            end=date + pd.offsets.MonthEnd(0),
            freq='D'
        )

        repeated = pd.DataFrame({
            'S2CELL': cell,
            'date': days,
            'min_gwl': value['min_gwl'],
            'mean_gwl': value['mean_gwl'],
            'max_gwl': value['max_gwl'],
        })

        daily_frames.append(repeated)

    df_daily = pd.concat(daily_frames, ignore_index=True)
    return df_daily
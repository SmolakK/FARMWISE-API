import pandas as pd
from datetime import datetime


def expand_range(range_str):
    if '_' in range_str:
        start, end = map(int, range_str.split('_'))
        return {str(year): range_str for year in range(start, end + 1)}
    else:
        return {range_str: range_str}


def create_timestamp_from_row(row):
    """
    Create a Pandas Timestamp from day, month, and year columns in a DataFrame row.

    Parameters:
        row (pd.Series): A row from a DataFrame containing 'day', 'month', and 'year' columns.

    Returns:
        pd.Timestamp: Timestamp object representing the given date.
    """
    day = int(row['Day'])
    month = int(row['Month'])
    year = int(row['Year'])
    return pd.Timestamp(year=year, month=month, day=day)


def get_years_between_dates(date_from, date_to):
    # Convert date strings to datetime objects
    start_date = datetime.strptime(date_from, '%Y-%m-%d')
    end_date = datetime.strptime(date_to, '%Y-%m-%d')

    # Get the years between the dates
    years = []
    current_year = start_date.year
    while current_year <= end_date.year:
        years.append(str(current_year))
        current_year += 1

    return years

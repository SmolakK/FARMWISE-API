from datetime import datetime

import pandas as pd


def expand_range(range_str):
    """
    Expands a range string into a dictionary mapping each year in the range to the original range string.

    If the input string contains an underscore (_), it is treated as a range (e.g., "2000_2005").
    The function returns a dictionary where each key is a year within that range, and the value is
    the original range string. If the input does not contain an underscore, it returns a dictionary
    with the input string as both the key and the value.

    :param range_str: A string representing a range of years in the format "start_end" or a single year as "year".
                      E.g., "2000_2005" or "2000".
    :return: A dictionary where the keys are the years as strings and the values are the original range string.
    """
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
    """
    Retrieves a list of years between two specified dates.

    The function converts the input date strings to datetime objects, then iterates through
    the years from the start date to the end date, collecting each year in a list.

    :param date_from: A string representing the start date in the format 'YYYY-MM-DD'.
    :param date_to: A string representing the end date in the format 'YYYY-MM-DD'.
    :return: A list of strings representing the years between the two dates, inclusive.
    """
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

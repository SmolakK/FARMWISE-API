import pytest
import pandas as pd
from utils.imgw_utils import expand_range, create_timestamp_from_row, get_years_between_dates


def test_expand_range_single_year():
    range_str = "2000"
    result = expand_range(range_str)
    expected = {"2000": "2000"}
    assert result == expected, f"Expected {expected}, got {result}"


def test_expand_range_multiple_years():
    range_str = "2000_2005"
    result = expand_range(range_str)
    expected = {
        "2000": "2000_2005",
        "2001": "2000_2005",
        "2002": "2000_2005",
        "2003": "2000_2005",
        "2004": "2000_2005",
        "2005": "2000_2005",
    }
    assert result == expected, f"Expected {expected}, got {result}"


def test_expand_range_invalid_format():
    range_str = "2000-2005"
    result = expand_range(range_str)
    expected = {"2000-2005": "2000-2005"}  # Handles cases without underscores as single values
    assert result == expected, f"Expected {expected}, got {result}"


def test_create_timestamp_from_row():
    row = pd.Series({"Day": 15, "Month": 8, "Year": 2023})
    result = create_timestamp_from_row(row)
    expected = pd.Timestamp(year=2023, month=8, day=15)
    assert result == expected, f"Expected {expected}, got {result}"


def test_create_timestamp_from_row_invalid_date():
    row = pd.Series({"Day": 32, "Month": 13, "Year": 2023})
    with pytest.raises(ValueError):
        create_timestamp_from_row(row)


def test_get_years_between_dates():
    date_from = "2020-01-01"
    date_to = "2023-12-31"
    result = get_years_between_dates(date_from, date_to)
    expected = ["2020", "2021", "2022", "2023"]
    assert result == expected, f"Expected {expected}, got {result}"


def test_get_years_between_dates_same_year():
    date_from = "2020-01-01"
    date_to = "2020-12-31"
    result = get_years_between_dates(date_from, date_to)
    expected = ["2020"]
    assert result == expected, f"Expected {expected}, got {result}"


def test_get_years_between_dates_invalid_format():
    date_from = "2020/01/01"
    date_to = "2023/12/31"
    with pytest.raises(ValueError, match="time data '2020/01/01' does not match format '%Y-%m-%d'"):
        get_years_between_dates(date_from, date_to)

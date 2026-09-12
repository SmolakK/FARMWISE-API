from datetime import date, datetime, time, timedelta
import re

_RELATIVE_DATE = re.compile(r"^today(?:-(\d+)d)?$")


def resolve_range_date(value) -> datetime:
    """Turn a coverage-range bound into a datetime.

    Accepts ISO dates and the relative forms ``'today'`` and ``'today-Nd'``
    used for continuously updated sources, which are evaluated now rather
    than when the mapping module was imported.
    """
    if isinstance(value, str):
        match = _RELATIVE_DATE.match(value.strip())
        if match:
            days = int(match.group(1) or 0)
            return datetime.combine(date.today() - timedelta(days=days), time.min)
    return datetime.fromisoformat(str(value))


def spatial_ranges_overlap(range1, range2):
    """
    Check if two spatial ranges overlap.

    Parameters:
        range1 (tuple): Spatial range 1 as (northmost, southmost, eastmost, westmost).
        range2 (tuple): Spatial range 2 as (northmost, southmost, eastmost, westmost).

    Returns:
        bool: True if the spatial ranges overlap, False otherwise.
    """
    north1, south1, east1, west1 = range1
    north2, south2, east2, west2 = range2

    # Check if ranges overlap
    if (south1 <= north2 and north1 >= south2) and (west1 <= east2 and east1 >= west2):
        return True
    else:
        return False


def time_ranges_overlap(range1, range2):
    """
    Check if two time ranges overlap.

    Parameters:
        range1 (tuple): Time range 1 as (start1, end1) in 'YYYY-MM-DD' format.
        range2 (tuple): Time range 2 as (start2, end2) in 'YYYY-MM-DD' format.

    Returns:
        bool: True if the time ranges overlap, False otherwise.
    """
    start1, end1 = map(resolve_range_date, range1)
    start2, end2 = map(resolve_range_date, range2)

    # Check if ranges overlap
    if start1 <= end2 and end1 >= start2:
        return True
    else:
        return False

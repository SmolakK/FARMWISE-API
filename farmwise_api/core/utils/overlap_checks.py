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


def validate_bounding_box(bounding_box) -> tuple[float, float, float, float]:
    """Return ``(north, south, east, west)`` as floats, rejecting malformed boxes.

    The overlap test assumes north >= south and east >= west. With the values
    swapped it still returns an answer, but a meaningless one: a box "from 10
    north to -10 south" was reported as overlapping sources it does not touch,
    and those sources were dispatched.
    """
    try:
        north, south, east, west = (float(value) for value in bounding_box)
    except (TypeError, ValueError):
        raise ValueError(
            f"bounding_box must be four numbers (north, south, east, west); got {bounding_box!r}"
        ) from None
    if not (-90 <= south <= north <= 90):
        raise ValueError(
            f"bounding_box latitudes must satisfy -90 <= south <= north <= 90; "
            f"got north={north}, south={south}"
        )
    if not (-180 <= west <= east <= 180):
        raise ValueError(
            f"bounding_box longitudes must satisfy -180 <= west <= east <= 180; "
            f"got east={east}, west={west}"
        )
    return north, south, east, west


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

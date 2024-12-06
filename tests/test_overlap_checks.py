import pytest
from datetime import datetime
from utils.overlap_checks import spatial_ranges_overlap, time_ranges_overlap


# Test spatial_ranges_overlap
@pytest.mark.parametrize("range1, range2, expected", [
    ((50.0, 40.0, 10.0, 0.0), (45.0, 35.0, 15.0, 5.0), True),  # Overlapping ranges
    ((50.0, 40.0, 10.0, 0.0), (60.0, 55.0, 15.0, 5.0), False),  # No overlap
    ((50.0, 40.0, 10.0, 0.0), (45.0, 35.0, 10.0, 0.0), True),   # Touching edges
    ((50.0, 40.0, 10.0, 0.0), (50.0, 40.0, 10.0, 0.0), True),   # Identical ranges
])
def test_spatial_ranges_overlap(range1, range2, expected):
    assert spatial_ranges_overlap(range1, range2) == expected


# Test time_ranges_overlap
@pytest.mark.parametrize("range1, range2, expected", [
    (("2023-01-01", "2023-12-31"), ("2023-06-01", "2023-06-30"), True),  # Overlapping ranges
    (("2023-01-01", "2023-12-31"), ("2024-01-01", "2024-12-31"), False),  # No overlap
    (("2023-01-01", "2023-12-31"), ("2023-12-31", "2024-01-01"), True),  # Touching end date
    (("2023-01-01", "2023-12-31"), ("2023-01-01", "2023-12-31"), True),  # Identical ranges
])
def test_time_ranges_overlap(range1, range2, expected):
    assert time_ranges_overlap(range1, range2) == expected

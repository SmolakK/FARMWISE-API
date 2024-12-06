import pytest
import pandas as pd
import numpy as np
from utils.interpolate_data import (
    mean_cell_size,
    mean_cell_edge,
    haversine,
    bounding_box_area,
    how_many,
    interpolate
)
from s2sphere import CellId, LatLng
from unittest.mock import patch

def test_mean_cell_size():
    level = 5
    result = mean_cell_size(level)
    # Expected result derived from known calculations for level 5
    expected = 83018.57 # Example value in km²
    assert abs(result - expected) < 50, f"Expected {expected}, got {result}"


def test_mean_cell_edge():
    level = 5
    result = mean_cell_edge(level)/1000
    # Expected result based on calculations
    expected = 140
    assert abs(result - expected) < 100, f"Expected {expected}, got {result}"


def test_haversine():
    lat1, lon1 = 40.748817, -73.985428  # New York
    lat2, lon2 = 34.052235, -118.243683  # Los Angeles
    result = haversine(lat1, lon1, lat2, lon2)
    # Known distance between NY and LA
    expected = 3937.0 * 1000
    assert abs(result - expected) < 1000.0, f"Expected {expected}, got {result}"


def test_bounding_box_area():
    north, south, east, west = 40.0, 30.0, -70.0, -80.0
    result = bounding_box_area(north, south, east, west)/1000**2
    # Expected result based on known area calculation
    expected = 1_011_437
    assert abs(result - expected) < 1000, f"Expected {expected}, got {result}"


def test_how_many():
    N, S, E, W = 40.0, 30.0, -70.0, -80.0
    level = 5
    result = how_many(N, S, E, W, level)
    # Expected values based on known calculations
    expected_lat, expected_lon = 8, 6  # Example values, replace with actual expected results
    assert result == (expected_lat, expected_lon), f"Expected {(expected_lat, expected_lon)}, got {result}"


@pytest.fixture
def sample_data():
    # Fixture for testing interpolate function
    timestamps = ["2023-01-01", "2023-01-02"]
    latitudes = [35.0, 36.0]
    longitudes = [-78.0, -77.0]
    values = [1.0, 2.0]


    data = {
        "Timestamp": np.repeat(timestamps, len(latitudes)),
        "lat": latitudes * len(timestamps),
        "lon": longitudes * len(timestamps),
        "value": values * len(timestamps),
    }
    data = pd.DataFrame(data)
    data.columns = pd.MultiIndex.from_product([data.columns.get_level_values(0)] + [['C']])
    data.set_index("Timestamp",inplace=True)

    return data


@patch("utils.interpolate_data.s2cells_to_coordinates", side_effect=lambda x: x)
def test_interpolate(mock_s2cells_to_coordinates, sample_data):
    spatial_range = (40.0, 30.0, -70.0, -80.0)
    level = 4
    result = interpolate(sample_data, spatial_range, level)

    assert not result.empty, "Interpolation result is empty"
    assert "value" in result.columns.levels[0], "Interpolated values column missing"
    assert len(result) > 0, "Interpolation returned no data"

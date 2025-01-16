import pytest
import pandas as pd
import s2sphere
from utils.coordinates_to_cells import prepare_coordinates


def test_prepare_coordinates_with_valid_data():
    # Input data
    coordinates = pd.DataFrame({
        'lat': [50.0, 49.5, 51.0],
        'lon': [14.0, 13.5, 15.0]
    })
    spatial_range = (51.5, 49.0, 15.5, 13.0)  # N, S, E, W
    level = 10

    # Call the function
    result = prepare_coordinates(coordinates, spatial_range, level)

    # Assert that the result is not None
    assert result is not None

    # Assert that the coordinates are limited to the spatial range
    for _, row in result.iterrows():
        assert 49.0 <= row.lat <= 51.5
        assert 13.0 <= row.lon <= 15.5

    # Assert that the S2CELL column exists
    assert 'S2CELL' in result.columns

    # Assert that S2CELL values are valid
    for cell_id in result['S2CELL']:
        assert isinstance(cell_id, s2sphere.CellId)


def test_prepare_coordinates_with_no_matching_coordinates():
    # Input data
    coordinates = pd.DataFrame({
        'lat': [52.0, 53.0, 54.0],  # Outside spatial range
        'lon': [16.0, 17.0, 18.0]   # Outside spatial range
    })
    spatial_range = (51.5, 49.0, 15.5, 13.0)  # N, S, E, W
    level = 10

    # Call the function
    result = prepare_coordinates(coordinates, spatial_range, level)

    # Assert that the result is None
    assert result is None


def test_prepare_coordinates_with_empty_dataframe():
    # Input data
    coordinates = pd.DataFrame(columns=['lat', 'lon'])  # Empty DataFrame
    spatial_range = (51.5, 49.0, 15.5, 13.0)  # N, S, E, W
    level = 10

    # Call the function
    result = prepare_coordinates(coordinates, spatial_range, level)

    # Assert that the result is None
    assert result is None


def test_prepare_coordinates_with_edge_case_coordinates():
    # Input data
    coordinates = pd.DataFrame({
        'lat': [51.5, 49.0],  # On the boundary of the spatial range
        'lon': [15.5, 13.0]   # On the boundary of the spatial range
    })
    spatial_range = (51.5, 49.0, 15.5, 13.0)  # N, S, E, W
    level = 10

    # Call the function
    result = prepare_coordinates(coordinates, spatial_range, level)

    # Assert that the result is not None
    assert result is not None

    # Assert that all coordinates are included
    assert len(result) == 2

    # Assert that the S2CELL column exists
    assert 'S2CELL' in result.columns

    # Assert that S2CELL values are valid
    for cell_id in result['S2CELL']:
        assert isinstance(cell_id, s2sphere.CellId)

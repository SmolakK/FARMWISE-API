import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from utils.cells_to_coordinates import s2cells_to_coordinates, _s2cell_id_to_coordinate
import s2sphere


@pytest.fixture
def mock_s2cell():
    # Mock an S2Cell ID object
    mock = MagicMock()
    mock.to_lat_lng.return_value.lat.return_value.degrees = 50.0
    mock.to_lat_lng.return_value.lng.return_value.degrees = 14.0
    return mock


def test_s2cell_id_to_coordinate():
    mock_s2cell = s2sphere.CellId.from_lat_lng(s2sphere.LatLng.from_degrees(50,14))
    # Assert that the function produces the correct results
    result = _s2cell_id_to_coordinate(mock_s2cell)
    assert result == pytest.approx((50, 14))


@patch("utils.cells_to_coordinates._s2cell_id_to_coordinate")
def test_s2cells_to_coordinates(mock_s2cell_id_to_coordinate, mock_s2cell):
    # Mock the _s2cell_id_to_coordinate function
    mock_s2cell_id_to_coordinate.side_effect = lambda x: (50.0 + x, 14.0 + x)

    # Create a sample pivoted_table with S2Cell IDs
    s2cells = [mock_s2cell, mock_s2cell]
    pivoted_table = pd.DataFrame(
        {
            "data1": [1, 2],
            "data2": [3, 4]
        },
        index=pd.MultiIndex.from_tuples(
            [(pd.Timestamp("2023-01-01"), cell) for cell in s2cells],
            names=["Timestamp", "S2CELL"]
        )
    )

    # Call the function under test
    result = s2cells_to_coordinates(pivoted_table)

    # Validate the results
    assert "lat" in result.columns
    assert "lon" in result.columns
    assert len(result["lat"]) == len(s2cells)
    assert len(result["lon"]) == len(s2cells)

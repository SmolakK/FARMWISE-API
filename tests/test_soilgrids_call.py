import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
from farmwise_api.adapters.API_readers.soilgrids.soilgrids_call import read_data
from farmwise_api.adapters.API_readers.soilgrids.soilgrids_mappings.soilgrids_mapping import (
    CONVERSION_DIVISORS,
    GLOBAL_MAPPING,
)


@pytest.mark.asyncio
@patch("farmwise_api.adapters.API_readers.soilgrids.soilgrids_call.fetch_soil_data")
@patch("farmwise_api.adapters.API_readers.soilgrids.soilgrids_call.prepare_coordinates")
@patch("farmwise_api.adapters.API_readers.soilgrids.soilgrids_call.how_many")
@patch("farmwise_api.adapters.API_readers.soilgrids.soilgrids_call.SoilGrids")
async def test_read_data(mock_soilgrids, mock_how_many, mock_prepare_coordinates, mock_fetch_soil_data):
    # Mock SoilGrids client
    mock_soilgrids_instance = MagicMock()
    mock_soilgrids.return_value = mock_soilgrids_instance

    # Mock the `how_many` function
    mock_how_many.return_value = (10, 10)  # Mock latitude and longitude sizes

    # Mock the `fetch_soil_data` function
    def mock_fetch_soil_data_side_effect(soilgrids, soil_property, west, south, east, north, size_lon, size_lat):
        # Return a mock dataset as a numpy array
        return np.full(
            (1, size_lat, size_lon),
            2 * CONVERSION_DIVISORS[soil_property],
        )

    mock_fetch_soil_data.side_effect = mock_fetch_soil_data_side_effect

    # Mock `prepare_coordinates`
    def mock_prepare(df, spatial_range, level):
        df["S2CELL"] = [f"cell{i}" for i in range(len(df))]
        return df

    mock_prepare_coordinates.side_effect = mock_prepare

    # Define test parameters
    spatial_range = (50.0, 40.0, 10.0, 0.0)
    time_range = ("2020-01-01", "2020-12-31")
    data_range = ["soil"]
    level = 8

    # Call the function under test
    result = await read_data(spatial_range, time_range, data_range, level)

    # Assertions
    assert result is not None
    assert isinstance(result, pd.DataFrame)
    assert "S2CELL" in result.columns.names
    assert not result.empty

    # Verify the mocks
    mock_soilgrids.assert_called_once()
    mock_how_many.assert_called_once_with(*spatial_range, level)
    assert mock_fetch_soil_data.call_count == 11  # Called once per soil property, soil mapping
    mock_prepare_coordinates.assert_called_once()
    prepared = mock_prepare_coordinates.call_args.args[0]
    assert prepared["lat"].iloc[0] > prepared["lat"].iloc[-1]
    assert prepared["lon"].iloc[0] < prepared["lon"].iloc[-1]
    for output_column in GLOBAL_MAPPING.values():
        assert (result[output_column] == 2).all().all()

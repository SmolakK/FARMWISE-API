import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import datetime
from API_readers.cds.cds_single_levels import read_data


@pytest.mark.asyncio
@patch("API_readers.cds.cds_single_levels.cdsapi.Client")
@patch("API_readers.cds.cds_single_levels.xr.open_dataset")
@patch("API_readers.cds.cds_single_levels.prepare_coordinates")
@patch("API_readers.cds.cds_single_levels.os.path.join", return_value="/mocked/path/temp_data.nc")
async def test_read_data(mock_join, mock_prepare_coordinates, mock_open_dataset, mock_cds_client):
    # Mock the CDS API client retrieve method
    mock_retrieve = MagicMock()
    mock_cds_client.return_value.retrieve = mock_retrieve

    # Mock xarray Dataset
    mock_dataset = MagicMock()
    mock_open_dataset.return_value = mock_dataset

    # Mock Dataset to DataFrame conversion
    mock_df = pd.DataFrame({
        'latitude': [50.0, 50.1],
        'longitude': [10.0, 10.1],
        'valid_time': [datetime(2023, 1, 1, 0, 0), datetime(2023, 1, 1, 1, 0)],
        't2m': [273.15, 274.15],  # Temperature in Kelvin
        'tp': [0.01, 0.02],  # Precipitation in meters
        'expver': [1, 1],
        'number': [0, 0]
    })
    mock_dataset.to_dataframe.return_value = mock_df

    # Define a side effect for prepare_coordinates
    def add_s2cell_column(df, spatial_range, level):
        df['S2CELL'] = ['cell1', 'cell2']
        return df

    # Assign the side effect to the mock
    mock_prepare_coordinates.side_effect = add_s2cell_column

    # Test data
    spatial_range = (50, 40, -10, 10)
    time_range = ('2023-01-01', '2023-01-02')
    data_range = ['temperature', 'precipitation']
    level = 10

    # Call the function
    result = await read_data(spatial_range, time_range, data_range, level)

    # Assertions
    mock_retrieve.assert_called_once()
    mock_open_dataset.assert_called_once_with("/mocked/path/temp_data.nc")
    mock_prepare_coordinates.assert_called_once()

    # Validate the arguments passed to prepare_coordinates
    called_args = mock_prepare_coordinates.call_args[0]
    assert isinstance(called_args[0], pd.DataFrame)
    assert 'lat' in called_args[0].columns
    assert 'lon' in called_args[0].columns
    assert 'Timestamp' in called_args[0].columns

    # Check mappings for aliases and global mappings
    assert "Temperature [°C]" in result.columns
    assert "Precipitation total [mm]" in result.columns

    # Validate data transformations
    assert isinstance(result, pd.DataFrame)
    # Temperature should be converted from Kelvin to Celsius
    assert result["Temperature [°C]"].iloc[0][0] == pytest.approx(0)  # 273.15 K -> 0°C
    # Precipitation should be converted from meters to daily total in mm
    assert result["Precipitation total [mm]"].iloc[0][0] == pytest.approx(0.01 * 24 * 60 * 60)  # Converted to mm

    # Ensure the result is pivoted by Timestamp and S2CELL
    assert result.index.name == "Timestamp"
    assert "S2CELL" in result.columns.names

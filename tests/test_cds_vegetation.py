import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import os
from datetime import datetime
from API_readers.cds.cds_vegetation import read_data


@pytest.mark.asyncio
@patch("API_readers.cds.cds_vegetation.cdsapi.Client")
@patch("API_readers.cds.cds_vegetation.zipfile.ZipFile")
@patch("API_readers.cds.cds_vegetation.glob.glob")
@patch("API_readers.cds.cds_vegetation.xr.open_dataset")
@patch("API_readers.cds.cds_vegetation.prepare_coordinates")
@patch("API_readers.cds.cds_vegetation.os.remove")
@patch("API_readers.cds.cds_vegetation.os.path.join", return_value="/mocked/path/temp_data.zip")
async def test_read_data(
    mock_join,
    mock_os_remove,
    mock_prepare_coordinates,
    mock_open_dataset,
    mock_glob,
    mock_zipfile,
    mock_cds_client,
):
    # Mock the CDS API client retrieve method
    mock_retrieve = MagicMock()
    mock_cds_client.return_value.retrieve = mock_retrieve

    # Mock zipfile extraction
    mock_zip = MagicMock()
    mock_zipfile.return_value.__enter__.return_value = mock_zip

    # Mock glob to find NetCDF files
    mock_glob.return_value = ["/mocked/path/file1.nc", "/mocked/path/file2.nc"]

    # Mock xarray Dataset
    mock_dataset = MagicMock()
    mock_open_dataset.return_value = mock_dataset

    # Mock xarray datasets
    mock_dataset1 = MagicMock()
    mock_dataset1.sel.return_value.to_dataframe.return_value.reset_index.return_value = pd.DataFrame({
        'lat_var': [50.0, 50.1],
        'lon_var': [10.0, 10.1],
        'time': [datetime(2023, 1, 1), datetime(2023, 1, 2)],
        'POTENTIAL_ET': [0.05, 0.06],  # Potential Evaporation in meters
        'crs': [None, None],
        'PIXEL_COUNTS': [None, None],
        'ALBH_QFLAG': [None, None],
        'FCOVER_QFLAG': [None, None],
        'LAI_QFLAG': [None, None]
    })

    mock_dataset2 = MagicMock()
    mock_dataset2.sel.return_value.to_dataframe.return_value.reset_index.return_value = pd.DataFrame({
        'lat_var': [50.0, 50.1],
        'lon_var': [10.0, 10.1],
        'time': [datetime(2023, 1, 3), datetime(2023, 1, 4)],
        'POTENTIAL_ET': [0.07, 0.08],
        'crs': [None, None],
        'PIXEL_COUNTS': [None, None],
        'ALBH_QFLAG': [None, None],
        'FCOVER_QFLAG': [None, None],
        'LAI_QFLAG': [None, None]
    })

    mock_open_dataset.side_effect = [mock_dataset1, mock_dataset2]

    # Mock prepare_coordinates
    def add_s2cell_column(df, spatial_range, level):
        df['S2CELL'] = ['cell1', 'cell2', 'cell3', 'cell4']
        return df

    mock_prepare_coordinates.side_effect = add_s2cell_column

    # Test data
    spatial_range = (50, 40, -10, 10)
    time_range = ('2023-01-01', '2023-01-04')
    data_range = ['potential evaporation']
    level = 10

    # Call the function
    result = await read_data(spatial_range, time_range, data_range, level)

    # Assertions
    mock_retrieve.assert_called_once()
    mock_zipfile.assert_called_once_with("/mocked/path/temp_data.zip", 'r')
    mock_glob.assert_called_once_with("/mocked/path/temp_data.zip")
    assert mock_open_dataset.call_count == 2
    mock_prepare_coordinates.assert_called()

    # Validate result DataFrame
    assert isinstance(result, pd.DataFrame)
    assert "S2CELL" in result.columns.names
    assert "Timestamp" == result.index.name
    assert "Potential Evaporation [m]" in result.columns.levels[0]  # From GLOBAL_MAPPING

    # Cleanup assertions
    mock_os_remove.assert_any_call("/mocked/path/temp_data.zip")
    for nc_file in mock_glob.return_value:
        mock_os_remove.assert_any_call(nc_file)

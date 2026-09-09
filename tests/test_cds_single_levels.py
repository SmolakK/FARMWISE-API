import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import datetime
from farmwise_api.adapters.API_readers.cds.cds_single_levels import (
    _open_downloaded_dataset,
    read_data,
)


@pytest.mark.asyncio
@patch("farmwise_api.adapters.API_readers.cds.cds_single_levels.cdsapi.Client")
@patch("farmwise_api.adapters.API_readers.cds.cds_single_levels.xr.open_dataset")
@patch("farmwise_api.adapters.API_readers.cds.cds_single_levels.prepare_coordinates")
async def test_read_data(mock_prepare_coordinates, mock_open_dataset, mock_cds_client):
    # Mock the CDS API client retrieve method
    mock_retrieve = MagicMock()
    mock_cds_client.return_value.retrieve = mock_retrieve

    # Mock xarray Dataset
    mock_dataset = MagicMock()
    mock_open_dataset.return_value = mock_dataset

    # Mock Dataset to DataFrame conversion
    timestamps = pd.date_range("2023-01-01", periods=25, freq="h")
    mock_df = pd.DataFrame({
        'latitude': [50.0] * len(timestamps),
        'longitude': [10.0] * len(timestamps),
        'valid_time': timestamps,
        't2m': [273.15] * len(timestamps),
        'tp': [0.001] * len(timestamps),
        'expver': [1] * len(timestamps),
        'number': [0] * len(timestamps),
    })
    mock_dataset.to_dataframe.return_value = mock_df

    # Define a side effect for prepare_coordinates
    def add_s2cell_column(df, spatial_range, level):
        df['S2CELL'] = ['cell1'] * len(df)
        return df

    # Assign the side effect to the mock
    mock_prepare_coordinates.side_effect = add_s2cell_column

    # Test data
    spatial_range = (50, 40, -10, 10)
    time_range = ('2023-01-01', '2023-01-01')
    data_range = ['temperature', 'precipitation']
    level = 10

    # Call the function
    result = await read_data(spatial_range, time_range, data_range, level)

    # Assertions
    mock_retrieve.assert_called_once()
    opened_path = mock_open_dataset.call_args.args[0]
    assert str(opened_path).endswith(
        "reanalysis-era5-single-levels_202301_temp_data.nc"
    )
    request = mock_retrieve.call_args.args[1]
    assert request["day"] == ["01", "02"]
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
    assert result["Temperature [°C]"].iloc[0, 0] == pytest.approx(0)
    # Precipitation should be converted from meters to daily total in mm
    assert result["Precipitation total [mm]"].iloc[0, 0] == pytest.approx(
        24.0
    )

    # Ensure the result is pivoted by Timestamp and S2CELL
    assert result.index.name == "Timestamp"
    assert "S2CELL" in result.columns.names


def test_open_downloaded_dataset_extracts_zip_wrapped_netcdf(tmp_path):
    import zipfile

    archive_path = tmp_path / "era5.nc"
    source_path = tmp_path / "data.nc"
    source_path.write_bytes(b"netcdf-placeholder")
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(source_path, arcname="data.nc")

    dataset = MagicMock()
    with patch(
        "farmwise_api.adapters.API_readers.cds.cds_single_levels.xr.open_dataset",
        return_value=dataset,
    ) as open_dataset:
        assert _open_downloaded_dataset(archive_path) is dataset

    opened_path = open_dataset.call_args.args[0]
    assert opened_path.name == "data.nc"
    assert opened_path.parent.name == "extracted"

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import pandas as pd
from wetterdienst.provider.dwd.observation import DwdObservationRequest, DwdObservationResolution
from API_readers.wetterdienst.wetterdienst_dwd import read_data
from utils.coordinates_to_cells import prepare_coordinates


@pytest.mark.asyncio
@patch("API_readers.wetterdienst.wetterdienst_dwd.prepare_coordinates")
@patch("API_readers.wetterdienst.wetterdienst_dwd.DwdObservationRequest")
async def test_read_data(mock_dwd_request, mock_prepare_coordinates):
    # Mock DwdObservationRequest
    mock_request_instance = MagicMock()
    mock_dwd_request.return_value = mock_request_instance

    # Mock the request.filter_by_bbox method to return the same mock instance
    mock_request_instance.filter_by_bbox.return_value = mock_request_instance

    # Mock the to_dict method
    mock_request_instance.values.all.return_value.to_dict.return_value = {
        "stations": [
            {
                "station_id": "02225",
                "start_date": "1922-01-01T00:00:00+00:00",
                "end_date": "1984-09-30T00:00:00+00:00",
                "latitude": 50.9167,
                "longitude": 14.3667,
                "height": 385.0,
                "name": "Hinterhermsdorf",
                "state": "Sachsen"
            },
            {
                "station_id": "02985",
                "start_date": "1991-01-01T00:00:00+00:00",
                "end_date": "2024-12-02T00:00:00+00:00",
                "latitude": 50.9383,
                "longitude": 14.2094,
                "height": 321.0,
                "name": "Lichtenhain-Mittelndorf",
                "state": "Sachsen"
            },
            {
                "station_id": "06129",
                "start_date": "1999-05-01T00:00:00+00:00",
                "end_date": "2024-12-02T00:00:00+00:00",
                "latitude": 51.0594,
                "longitude": 14.4266,
                "height": 291.0,
                "name": "Sohland/Spree",
                "state": "Sachsen"
            }
        ],
        "values": [
            {
                "station_id": "02225",
                "dataset": "climate_summary",
                "parameter": "precipitation_height",
                "date": "2017-01-10T00:00:00+00:00",
                "value": None,
                "quality": None
            },
            {
                "station_id": "02225",
                "dataset": "climate_summary",
                "parameter": "temperature_air_mean_2m",
                "date": "2017-01-11T00:00:00+00:00",
                "value": None,
                "quality": None
            },
            {
                "station_id": "02985",
                "dataset": "climate_summary",
                "parameter": "precipitation_height",
                "date": "2017-01-10T00:00:00+00:00",
                "value": 0.0,
                "quality": 9.0
            },
            {
                "station_id": "02985",
                "dataset": "climate_summary",
                "parameter": "temperature_air_mean_2m",
                "date": "2017-01-10T00:00:00+00:00",
                "value": 267.95,
                "quality": 9.0
            },
        ]
    }

    # Mock prepare_coordinates
    def mock_prepare(df, spatial_range, level):
        df["S2CELL"] = ["cell1"]
        return df

    mock_prepare_coordinates.side_effect = mock_prepare

    # Test parameters
    spatial_range = (51.0, 49.0, 12.0, 9.0)
    time_range = ("2017-01-01", "2017-01-12")
    data_range = ["temperature", "precipitation"]
    level = 8

    # Call the function under test
    result = await read_data(spatial_range, time_range, data_range, level)

    # Assertions
    assert result is not None
    assert isinstance(result, pd.DataFrame)
    assert "Temperature [°C]" in result.columns.levels[0]
    assert "Precipitation total [mm]" in result.columns.levels[0]
    assert "cell1" in result.columns.levels[1]
    mock_prepare_coordinates.assert_called_once()
    assert result['Temperature [°C]'].values[0][0] == pytest.approx(-5.2)  # validate temperature convertion

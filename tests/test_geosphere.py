import pytest
import pandas as pd
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
from API_readers.geosphere.geosphere import read_data, fetch_station_metadata, fetch_station_data

@pytest.mark.asyncio
@patch("API_readers.geosphere.geosphere.prepare_coordinates")
@patch("API_readers.geosphere.geosphere.fetch_station_metadata")
@patch("API_readers.geosphere.geosphere.fetch_station_data")
async def test_read_data(mock_fetch_station_data, mock_fetch_station_metadata, mock_prepare_coordinates):
    # Mock fetch_station_metadata
    mock_metadata = pd.DataFrame({
        "id": ["station1", "station2"],
        "name": ["Station 1", "Station 2"],
        "lat": [50.0, 49.5],
        "lon": [10.0, 10.5]
    })
    mock_fetch_station_metadata.return_value = mock_metadata

    # Mock fetch_station_data
    mock_data = pd.DataFrame({
        "station": ["station1", "station2"],
        "time": ["2023-01-01", "2023-01-01"],
        "tl_mittel": [5.0, 6.0],
        "rr": [-3, 0.2]
    })
    mock_fetch_station_data.return_value = mock_data

    # Mock prepare_coordinates
    def mock_prepare(df, spatial_range, level):
        df["S2CELL"] = [f"cell{i}" for i in range(len(df))]
        return df

    mock_prepare_coordinates.side_effect = mock_prepare

    # Test parameters
    spatial_range = (51.0, 49.0, 11.0, 9.0)
    time_range = ("2023-01-01", "2023-01-02")
    data_range = ["temperature", "precipitation"]
    level = 8

    # Call the function
    result = await read_data(spatial_range, time_range, data_range, level)

    # Assertions
    mock_fetch_station_metadata.assert_called_once()
    mock_fetch_station_data.assert_called_once_with(
        "klima-v2-1d", ["station1", "station2"], time_range, ["tl_mittel", "rr"]
    )
    mock_prepare_coordinates.assert_called_once()

    assert isinstance(result, pd.DataFrame)
    assert not result.empty
    assert "Temperature [°C]" in result.columns.levels[0]
    assert "Precipitation total [mm]" in result.columns.levels[0]
    assert "Timestamp" == result.index.name


@pytest.mark.asyncio
@patch("API_readers.geosphere.geosphere.httpx.AsyncClient")
async def test_fetch_station_metadata(mock_httpx_client):
    # Mock HTTP response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "stations": [
            {"id": "station1", "name": "Station 1", "lat": 50.0, "lon": 10.0},
            {"id": "station2", "name": "Station 2", "lat": 49.5, "lon": 10.5}
        ]
    }
    mock_httpx_client.return_value.__aenter__.return_value.get.return_value = mock_response

    # Call the function
    result = await fetch_station_metadata()

    # Assertions
    mock_httpx_client.assert_called_once()
    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["id", "name", "lat", "lon"]
    assert len(result) == 2


@pytest.mark.asyncio
@patch("API_readers.geosphere.geosphere.httpx.AsyncClient")
async def test_fetch_station_data(mock_httpx_client):
    # Mock HTTP response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = (
        "station,time,tl_mittel,rr\n"
        "station1,2023-01-01,5.0,0.1\n"
        "station2,2023-01-01,6.0,0.2\n"
    )
    mock_httpx_client.return_value.__aenter__.return_value.get.return_value = mock_response

    # Test parameters
    resource_id = "klima-v2-1d"
    station_ids = ["station1", "station2"]
    time_range = ("2023-01-01", "2023-01-02")
    parameters = ["tl_mittel", "rr"]

    # Call the function
    result = await fetch_station_data(resource_id, station_ids, time_range, parameters)

    # Assertions
    mock_httpx_client.assert_called_once()
    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["station", "time", "tl_mittel", "rr"]
    assert len(result) == 2

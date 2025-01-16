import pytest
from unittest.mock import AsyncMock, patch, Mock
import pandas as pd
from API_readers.hubeau.get_piezo_stations import get_station_codes  # Adjust the import path as necessary

@pytest.mark.asyncio
@patch("API_readers.hubeau.get_piezo_stations.httpx.AsyncClient")  # Adjust based on your import
async def test_get_station_codes(mock_async_client):
    # Create mock responses
    mock_response_page_1 = AsyncMock()
    mock_response_page_1.json = Mock(return_value={
        "data": [
            {"code_bss": "STATION1", "x": 2.3522, "y": 48.8566},
            {"code_bss": "STATION2", "x": 2.3333, "y": 48.8333}
        ],
        "next": True
    })
    mock_response_page_1.status_code = 200

    mock_response_page_2 = AsyncMock()
    mock_response_page_2.json = Mock(return_value={
        "data": [
            {"code_bss": "STATION3", "x": 2.3636, "y": 48.8636}
        ],
        "next": False
    })
    mock_response_page_2.status_code = 200

    # Configure the mock AsyncClient instance
    instance = mock_async_client.return_value.__aenter__.return_value
    instance.get.side_effect = [mock_response_page_1, mock_response_page_2]

    # Define test inputs
    bbox = "2.0,48.0,3.0,49.0"
    time_range = ("2023-01-01", "2023-12-31")

    # Call the function under test
    result = await get_station_codes(bbox, time_range)

    # Define the expected DataFrame
    expected_df = pd.DataFrame({
        "code_bss": ["STATION1", "STATION2", "STATION3"],
        "x": [2.3522, 2.3333, 2.3636],
        "y": [48.8566, 48.8333, 48.8636]
    })

    # Assert that the result matches the expected DataFrame
    pd.testing.assert_frame_equal(result.reset_index(drop=True), expected_df)

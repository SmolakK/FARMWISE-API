import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import numpy as np
import pandas as pd
from API_readers.corine.corine_read import read_data


@pytest.mark.asyncio
@patch("API_readers.corine.corine_read.asyncio.to_thread")
@patch("API_readers.corine.corine_read.Image.open")
@patch("API_readers.corine.corine_read.prepare_coordinates")
@patch("API_readers.corine.corine_read.httpx.AsyncClient")
async def test_read_data(
    mock_httpx_client,
    mock_prepare_coordinates,
    mock_image_open,
    mock_to_thread
):
    # Mock the CORINE API client
    mock_client = AsyncMock()
    mock_httpx_client.return_value.__aenter__.return_value = mock_client

    # Mock the API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"mocked_image_data"
    mock_client.get.return_value = mock_response

    # Mock image processing
    mock_image = MagicMock()
    mock_image_open.return_value = mock_image

    # Define a fixed array to return when asyncio.to_thread is called
    fixed_array = np.array([
    [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]],
    [[13, 14, 15, 16], [17, 18, 19, 20], [21, 22, 23, 24]],
    [[25, 26, 27, 28], [29, 30, 31, 32], [33, 34, 35, 36]]
    ])
    mock_to_thread.return_value = fixed_array

    # Mock prepare_coordinates
    def mock_prepare(df, spatial_range, level):
        df['S2CELL'] = [f'cell{i}' for i in range(len(df))]
        return df

    mock_prepare_coordinates.side_effect = mock_prepare

    # Test parameters
    spatial_range = (51.2, 50.8, 17.1, 16.5)
    time_range = ('2018-01-01', '2018-12-31')
    data_range = ['land cover']
    level = 8

    # Call the function
    result = await read_data(spatial_range, time_range, data_range, level)

    # Assertions
    mock_client.get.assert_called()

    assert isinstance(result, pd.DataFrame)
    assert "S2CELL" in result.columns.names
    assert "Timestamp" == result.index.name
    assert all(param in result.columns.levels[0] for param in ['CORINE R', 'CORINE G', 'CORINE B', 'CORINE ALPHA'])
    assert result.shape == (365,36)

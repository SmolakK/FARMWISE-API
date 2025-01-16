import pytest
import numpy as np
import pandas as pd
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
from API_readers.egdi.egdi_read_d10 import read_data

@pytest.mark.asyncio
@patch("API_readers.egdi.egdi_read_d10.asyncio.to_thread")
@patch("API_readers.egdi.egdi_read_d10.prepare_coordinates")
@patch("API_readers.egdi.egdi_read_d10.rasterio.open")
async def test_read_data(mock_rasterio_open, mock_prepare_coordinates, mock_to_thread):
    # Mock rasterio dataset
    mock_dataset = MagicMock()
    mock_rasterio_open.return_value.__enter__.return_value = mock_dataset
    mock_dataset.read.return_value = np.array([[10, 20], [30, 40]])  # Mock raster data
    mock_dataset.transform = MagicMock()

    # Mock rasterio.transform.xy to return coordinates
    def mock_xy(transform, rows, cols, offset):
        return [[15.0, 15.1], [15.2, 15.3]], [[50.0, 50.1], [50.2, 50.3]]

    mock_dataset.xy.side_effect = mock_xy

    # Mock prepare_coordinates
    def mock_prepare(df, spatial_range, level):
        df['S2CELL'] = [f'cell{i}' for i in range(len(df))]
        return df

    mock_prepare_coordinates.side_effect = mock_prepare

    # Mock asyncio.to_thread
    async def mock_to_thread_side_effect(func, *args, **kwargs):
        if func.__name__ == "load_raster_data":
            return (
                np.array([[10, 20], [30, 40]]),  # Mock data
                [[15.0, 15.1], [15.2, 15.3]],  # Mock x-coords
                [[50.0, 50.1], [50.2, 50.3]]   # Mock y-coords
            )
        return func(*args, **kwargs)

    mock_to_thread.side_effect = mock_to_thread_side_effect

    # Test parameters
    spatial_range = (51.2, 49.0, 17.1, 15.0)
    time_range = ('2010-01-01', '2010-01-02')
    data_range = ['hydraulic conductivity']
    level = 8

    # Call the async function
    result = await read_data(spatial_range, time_range, data_range, level)

    # Assertions
    mock_prepare_coordinates.assert_called()
    assert isinstance(result, pd.DataFrame)
    assert "S2CELL" in result.columns.names
    assert "Timestamp" == result.index.name
    assert result.shape == (2,4)

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
from API_readers.gios.gios_scraper import extract_point_ids, scrape_point_data, read_data


@pytest.mark.asyncio
@patch("API_readers.gios.gios_scraper.httpx.AsyncClient")
async def test_extract_point_ids(mock_client):
    # Mock the AsyncClient response
    mock_response = AsyncMock()
    mock_response.text = """
    <html>
        <body>
            <a href="?p=123"></a>
            <a href="?p=456"></a>
            <a href="?p=789"></a>
        </body>
    </html>
    """
    mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

    url = "https://example.com"
    result = await extract_point_ids(url)

    assert result == "123,456,789", "Extracted point IDs are incorrect"


@pytest.mark.asyncio
@patch("API_readers.gios.gios_scraper.extract_point_ids")
@patch("API_readers.gios.gios_scraper.scrape_point_data")
@patch("API_readers.gios.gios_scraper.prepare_coordinates")
@patch("API_readers.gios.gios_scraper.pd.read_csv")
async def test_read_data(mock_read_csv, mock_prepare_coordinates, mock_scrape_point_data, mock_extract_point_ids):
    # Mock the point IDs
    mock_extract_point_ids.return_value = "123,456"

    # Mock coordinates DataFrame
    mock_coordinates = pd.DataFrame({
        "id": [123, 456],
        "S2CELL": ["cell1", "cell2"]
    })
    mock_prepare_coordinates.return_value = mock_coordinates

    # Mock scraped data
    mock_scrape_point_data.return_value = pd.DataFrame({
        "point_id": [123, 456],
        "year": [2020, 2020],
        "Parameter1": [1.0, 2.0],
        "Parameter2": [3.0, 4.0]
    })

    # Mock CSV read
    mock_read_csv.return_value = mock_coordinates

    # Test parameters
    spatial_range = (50, 40, 10, 20)
    time_range = ("2020-01-01", "2020-12-31")
    data_range = ["Parameter1", "Parameter2"]
    level = 8

    result = await read_data(spatial_range, time_range, data_range, level)

    assert result is not None, "The returned DataFrame is None"
    assert isinstance(result, pd.DataFrame), "The returned result is not a DataFrame"
    assert "cell1" in result.columns.get_level_values(1), "S2CELL mapping failed"

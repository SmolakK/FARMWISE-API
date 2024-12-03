import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
from API_readers.imgw.imgw_api_synop_daily import read_data  # Adjust the import path
from io import BytesIO
import zipfile


@pytest.mark.asyncio
@patch("API_readers.imgw.imgw_api_synop_daily.prepare_coordinates")
@patch("API_readers.imgw.imgw_api_synop_daily.httpx.AsyncClient")
@patch("API_readers.imgw.imgw_api_synop_daily.pd.read_csv")
async def test_read_data(mock_read_csv, mock_httpx_client, mock_prepare_coordinates):
    # Mock the imgw_coordinates.csv file
    def mock_read_csv_side_effect(file, *args, **kwargs):
        if isinstance(file, zipfile.ZipExtFile):  # This handles reading from the mocked ZIP
            return pd.DataFrame({
                "Station code": [250180460],
                "Year": [2020],
                "Month": [1],
                "Day": [1],
                "Temperature [°C]": [5.2],
            })
        else:  # Handles other CSV files (e.g., imgw_coordinates.csv)
            return pd.DataFrame({
                "Code": [250180460, 254230010, 250190430, 250210030],
                "Name": ["ADAMOWICE,Poland", "ALEKSANDRÓWKA,Poland", "ALWERNIA,Poland", "ANNOPOL,Poland"],
                "lat": [51.9399783, 51.5719923, 50.0690434, 50.8851655],
                "lon": [20.4814776, 21.5422823, 19.5396737, 21.8550836]
            })

    mock_read_csv.side_effect = mock_read_csv_side_effect

    # Mock prepare_coordinates
    def mock_prepare(coordinates, spatial_range, level):
        coordinates["S2CELL"] = [f"cell{i}" for i in range(len(coordinates))]
        return coordinates

    mock_prepare_coordinates.side_effect = mock_prepare

    # Create a valid in-memory ZIP file
    zip_buffer_t = BytesIO()
    with zipfile.ZipFile(zip_buffer_t, mode="w") as zf:
        zf.writestr("_t_file.csv", "Station code,Year,Month,Day,Temperature [°C]\n250180460,2020,01,01,5.2")
    zip_buffer_t.seek(0)

    zip_buffer_d_t = BytesIO()
    with zipfile.ZipFile(zip_buffer_d_t , mode="w") as zf:
        zf.writestr("_d_file.csv", "Station code,Year,Month,Day,Temperature [°C]\n250180460,2020,01,01,5.2")
    zip_buffer_d_t.seek(0)

    # Define the dynamic mock_get function
    async def mock_get(url, params=None, **kwargs):
        if url.endswith("synop"):  # Replace "URL" with the actual base URL in your function
            # Simulate the response for the main URL listing folders
            return AsyncMock(
                status_code=200,
                text="<a href='2020/'>2020/</a><a href='2021/'>2021/</a>"
            )
        elif ("/2020" in url or "/2021" in url) and not 'file' in url:
            # Simulate the response for a specific year folder listing files
            return AsyncMock(
                status_code=200,
                text="<a href='file1.zip'>file1.zip</a><a href='file2.zip'>file2.zip</a>"
            )
        elif url.endswith("file1.zip"):
            # Simulate the response for downloading zip files
            return AsyncMock(
                status_code=200,
                content=zip_buffer_t.getvalue()
            )
        elif url.endswith("file2.zip"):
            # Simulate the response for downloading zip files
            return AsyncMock(
                status_code=200,
                content=zip_buffer_d_t.getvalue()
            )
        else:
            # Default to a generic 404 error
            return AsyncMock(
                status_code=404,
                text="Not Found"
            )

    # Apply the dynamic mock_get to the HTTPX client's get method
    mock_httpx_client.return_value.__aenter__.return_value.get.side_effect = mock_get

    # Test parameters
    spatial_range = (50.0, 40.0, 10.0, 0.0)
    time_range = ("2020-01-01", "2021-12-31")
    data_range = ["temperature", "precipitation"]
    level = 8

    # Call the function under test
    result = await read_data(spatial_range, time_range, data_range, level)

    # Assertions
    assert result is not None
    assert "S2CELL" in result.columns.names
    assert isinstance(result, pd.DataFrame)

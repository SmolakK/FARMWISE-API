import pytest
from unittest.mock import AsyncMock, patch
import pandas as pd
from farmwise_api.adapters.API_readers.imgw_hydro.imgw_api_hydro_daily import read_data
from io import BytesIO
import zipfile


@pytest.mark.asyncio
@patch("farmwise_api.adapters.API_readers.imgw_hydro.imgw_api_hydro_daily.prepare_coordinates")
@patch("farmwise_api.adapters.API_readers.imgw_hydro.imgw_api_hydro_daily.httpx.AsyncClient")
@patch("farmwise_api.adapters.API_readers.imgw_hydro.imgw_api_hydro_daily.pd.read_csv")
async def test_read_data(
    mock_read_csv, mock_httpx_client, mock_prepare_coordinates, monkeypatch
):
    monkeypatch.setenv("FARMWISE_ENABLE_PRIVATE_IMGW", "1")
    monkeypatch.setattr(
        "farmwise_api.adapters.API_readers.imgw_hydro.imgw_api_hydro_daily.adapter_data",
        lambda *_parts: "private-imgw-hydro-coordinates.csv",
    )
    # Mock the imgw_coordinates.csv file
    def mock_read_csv_side_effect(file, *args, **kwargs):
        if isinstance(file, zipfile.ZipExtFile):  # This handles reading from the mocked ZIP
            # Column names must match WATER_COLUMNS exactly - "Water level",
            # not "Water Level" - or the adapter selects nothing at all and
            # the test silently asserts against an empty frame.
            return pd.DataFrame({
                "Station code": [250180460, 254230010],
                "Hydrological year": [2020, 2020],
                "Calendar month": [1, 1],
                "Day": [1, 1],
                # 9999 / 99999.999 are IMGW's "no observation" sentinels, not
                # a 100-metre river stage and a 100000 m3/s discharge.
                "Water level [cm]": [120, 9999],
                "Flow [m³/s]": [5.5, 99999.999],
            })
        else:  # Handles other CSV files (e.g., imgw_coordinates.csv)
            return pd.DataFrame({
                "Unnamed: 0": [250180460, 254230010, 250190430, 250210030],
                "Name": ["ADAMOWICE,Poland", "ALEKSANDRĂ“WKA,Poland", "ALWERNIA,Poland", "ANNOPOL,Poland"],
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
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w") as zf:
        # Only the member name matters here: pd.read_csv is mocked above, so
        # the archive contents are never parsed. The name must contain "codz"
        # because that is what the adapter looks for.
        zf.writestr("_codz.csv", "placeholder")
    zip_buffer.seek(0)

    # Define the dynamic mock_get function
    async def mock_get(url, params=None, **kwargs):
        if url.endswith("dobowe/"):  # Replace with the actual base URL
            # Simulate the response for the main URL listing folders
            return AsyncMock(
                status_code=200,
                text="<a href='2020/'>2020/</a><a href='2021/'>2021/</a>"
            )
        elif url.endswith(".zip"):
            # Simulate downloading the archive itself. Checked before the
            # folder branch because the archive URL also contains the year.
            return AsyncMock(
                status_code=200,
                content=zip_buffer.getvalue()
            )
        elif "/2020" in url or "/2021" in url:
            # A year folder listing. The adapter selects only IMGW's
            # `codz_*` daily archives, so the name has to be realistic.
            return AsyncMock(
                status_code=200,
                text="<a href='codz_2020_01.zip'>codz_2020_01.zip</a>"
            )
        elif url.endswith("never-matched.zip"):
            # Simulate the response for downloading zip files
            return AsyncMock(
                status_code=200,
                content=zip_buffer.getvalue()
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
    # This adapter serves surface water quantity; asking for meteorological
    # factors selects no value columns and the test asserts nothing.
    data_range = ["surface water quantity"]
    level = 8

    # Call the function under test
    result = await read_data(spatial_range, time_range, data_range, level)

    # Assertions
    assert result is not None
    assert "S2CELL" in result.columns.names
    assert isinstance(result, pd.DataFrame)
    # IMGW writes 9999 for "no observation". It must arrive as NaN, not as a
    # 100-metre river stage that would skew every downstream statistic.
    values = pd.to_numeric(
        pd.Series(result.to_numpy().ravel()), errors="coerce"
    ).dropna()
    assert not values.empty, "the real observation should have survived"
    assert values.max() <= 120, (
        f"IMGW no-data sentinel leaked into the output: max={values.max()}"
    )

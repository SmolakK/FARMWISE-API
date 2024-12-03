import pytest
from unittest.mock import AsyncMock, patch, Mock
import pandas as pd
from API_readers.hubeau.hubeau_piezo_read import read_data


@pytest.mark.asyncio
@patch("API_readers.hubeau.hubeau_piezo_read.prepare_coordinates")
@patch("API_readers.hubeau.hubeau_piezo_read.get_station_codes")
@patch("API_readers.hubeau.hubeau_piezo_read.httpx.AsyncClient")
async def test_read_data(mock_client, mock_get_station_codes, mock_prepare_coordinates):
    # Mock station codes response
    mock_get_station_codes.return_value = pd.DataFrame({
        "code_bss": ["STATION1", "STATION2"],
        "x": [2.3522, 2.3333],
        "y": [48.8566, 48.8333]
    })

    # Mock API response for groundwater data
    mock_response_page_1 = AsyncMock()
    mock_response_page_1.json = Mock(return_value={
        "data": [
            {"date_mesure": "2018-01-01", "niveau_nappe_eau": 2.0, "profondeur_nappe": 10.0, "code_bss": "STATION1"},
            {"date_mesure": "2018-01-01", "niveau_nappe_eau": 1.5, "profondeur_nappe": 8.0, "code_bss": "STATION2"}
        ],
        "next": False
    })
    mock_response_page_1.status_code = 200

    # Mock the HTTP client's get method
    mock_client.return_value.__aenter__.return_value.get.return_value = mock_response_page_1

    # Mock prepare_coordinates
    def mock_prepare(df, spatial_range, level):
        df["S2CELL"] = [f"cell{i}" for i in range(len(df))]
        return df

    mock_prepare_coordinates.side_effect = mock_prepare

    # Test parameters
    spatial_range = (48.2, 40.0, 6.1, 3.0)
    time_range = ('2018-01-01', '2018-12-31')
    data_range = ['land cover']
    level = 8

    # Call the async function
    result = await read_data(spatial_range, time_range, data_range, level)

    # Assert the result is a DataFrame
    assert isinstance(result, pd.DataFrame)

    # Assert the shape of the DataFrame
    assert not result.empty

    # Assert the column structure (check for presence of S2CELLs and timestamps)
    assert "Groundwater Level [cm]" in result.columns.get_level_values(0)
    assert "Groundwater Depth [cm]" in result.columns.get_level_values(0)

    # Assert that data values are multiplied correctly
    df_values = result["Groundwater Level [cm]"].iloc[0, 0]
    assert df_values == 200

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from shapely.geometry import box, mapping

from farmwise_api.adapters.API_readers.corine.corine_read import (
    OUTPUT_COLUMN,
    read_data,
)


@pytest.mark.asyncio
@patch("farmwise_api.adapters.API_readers.corine.corine_read._s2_cell_polygons")
@patch("farmwise_api.adapters.API_readers.corine.corine_read.httpx.AsyncClient")
async def test_read_data_returns_dominant_categorical_class(
    mock_httpx_client,
    mock_s2_polygons,
):
    mock_s2_polygons.return_value = {
        "west-cell": box(0, 0, 1, 1),
        "east-cell": box(1, 0, 2, 1),
    }
    response = MagicMock()
    response.json.return_value = {
        "features": [
            {
                "geometry": mapping(box(0, 0, 1.4, 1)),
                "properties": {"Code_18": "211"},
            },
            {
                "geometry": mapping(box(1.4, 0, 2, 1)),
                "properties": {"Code_18": "311"},
            },
        ]
    }
    client = AsyncMock()
    client.get.return_value = response
    mock_httpx_client.return_value.__aenter__.return_value = client

    result = await read_data(
        (1, 0, 2, 0),
        ("2018-01-01", "2018-12-31"),
        ["land cover"],
        8,
    )

    assert isinstance(result, pd.DataFrame)
    assert result.index.name == "Timestamp"
    assert result.columns.names[1] == "S2CELL"
    assert result.shape == (365, 2)
    assert (result[(OUTPUT_COLUMN, "west-cell")] == 211).all()
    assert (result[(OUTPUT_COLUMN, "east-cell")] == 311).all()
    request_url = client.get.call_args.args[0]
    request_params = client.get.call_args.kwargs["params"]
    assert "CLC2018_WM/MapServer/0/query" in request_url
    assert request_params["f"] == "geojson"
    assert request_params["outFields"] == "Code_18"


@pytest.mark.asyncio
@patch("farmwise_api.adapters.API_readers.corine.corine_read._s2_cell_polygons")
@patch("farmwise_api.adapters.API_readers.corine.corine_read.httpx.AsyncClient")
async def test_read_data_uses_latest_snapshot_not_later_than_request(
    mock_httpx_client,
    mock_s2_polygons,
):
    mock_s2_polygons.return_value = {"cell": box(0, 0, 1, 1)}
    response = MagicMock()
    response.json.return_value = {
        "features": [
            {
                "geometry": mapping(box(0, 0, 1, 1)),
                "properties": {"Code_12": 211},
            }
        ]
    }
    client = AsyncMock()
    client.get.return_value = response
    mock_httpx_client.return_value.__aenter__.return_value = client

    await read_data(
        (1, 0, 1, 0),
        ("2017-01-01", "2017-01-02"),
        ["land cover"],
        8,
    )

    assert "CLC2012_WM/MapServer/0/query" in client.get.call_args.args[0]

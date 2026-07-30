from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from adapters.API_readers.hubeau import hubeau_sw_quality_read as surface
from adapters.API_readers.hubeau import hubeau_wq_read as groundwater


@pytest.mark.asyncio
@pytest.mark.parametrize("module", [surface, groundwater])
async def test_fetch_data_formats_non_empty_response(module):
    frame = pd.DataFrame(
        {"resultat": [2.5]},
        index=pd.to_datetime(["2024-01-01"]),
    )
    api = SimpleAPI(frame)

    result = await module.fetch_data(
        api,
        "station",
        ["2024-01-01", "2024-01-02"],
        ["1340"],
        verbose_level=2,
    )

    assert result.loc[0, "date_debut_prelevement"] == pd.Timestamp("2024-01-01")
    assert result.loc[0, "resultat"] == 2.5
    assert api.get_data.call_count == 1


class SimpleAPI:
    def __init__(self, result):
        self.get_data = MagicMock(return_value=result)


@pytest.mark.asyncio
@pytest.mark.parametrize("module", [surface, groundwater])
async def test_fetch_data_returns_none_on_client_error(module):
    api = SimpleAPI(pd.DataFrame())
    api.get_data.side_effect = RuntimeError("offline")

    result = await module.fetch_data(
        api,
        "station",
        ["2024-01-01", "2024-01-02"],
        ["1340"],
        verbose_level=1,
    )

    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize("module", [surface, groundwater])
async def test_read_data_rejects_unknown_parameter_without_loading_points(module):
    read_csv = MagicMock()
    original = module.pd.read_csv
    module.pd.read_csv = read_csv
    try:
        result = await module.read_data(
            (51.0, 49.0, 3.0, 1.0),
            ("2024-01-01", "2024-01-02"),
            "unknown parameter",
            10,
            verbose_level=1,
        )
    finally:
        module.pd.read_csv = original

    assert result is None
    read_csv.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module, points",
    [
        (
            surface,
            pd.DataFrame(
                {
                    "code_station": ["SW1"],
                    "x_longitude": [2.0],
                    "y_latitude": [50.0],
                }
            ),
        ),
        (
            groundwater,
            pd.DataFrame(
                {
                    "code_bss_new": ["GW1"],
                    "lon": [2.0],
                    "lat": [50.0],
                }
            ),
        ),
    ],
)
async def test_read_data_returns_none_when_no_points_match(
    monkeypatch, module, points
):
    monkeypatch.setattr(module, "adapter_data", lambda *_args: "points.csv")
    monkeypatch.setattr(module.pd, "read_csv", MagicMock(return_value=points))
    monkeypatch.setattr(module, "prepare_coordinates", MagicMock(return_value=None))

    result = await module.read_data(
        (51.0, 49.0, 3.0, 1.0),
        ("2024-01-01", "2024-01-02"),
        ["nitrate"],
        10,
    )

    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module, points, point_id",
    [
        (
            surface,
            pd.DataFrame(
                {
                    "code_station": ["SW1", "SW2"],
                    "x_longitude": [2.0, 2.1],
                    "y_latitude": [50.0, 50.1],
                    "S2CELL": ["cell-1", "cell-2"],
                }
            ),
            "SW1",
        ),
        (
            groundwater,
            pd.DataFrame(
                {
                    "code_bss_new": ["GW1", "GW2"],
                    "lon": [2.0, 2.1],
                    "lat": [50.0, 50.1],
                    "S2CELL": ["cell-1", "cell-2"],
                }
            ),
            "GW1",
        ),
    ],
)
async def test_read_data_limits_points_formats_dates_and_handles_empty_responses(
    monkeypatch, module, points, point_id
):
    monkeypatch.setattr(module, "adapter_data", lambda *_args: "points.csv")
    monkeypatch.setattr(module.pd, "read_csv", MagicMock(return_value=points))
    monkeypatch.setattr(
        module,
        "prepare_coordinates",
        MagicMock(return_value=points.rename(
            columns={"x_longitude": "lon", "y_latitude": "lat"}
        )),
    )
    api = object()
    init_api = MagicMock(return_value=api)
    monkeypatch.setattr(module.hub, "init_api", init_api)
    fetch = AsyncMock(return_value=None)
    monkeypatch.setattr(module, "fetch_data", fetch)

    result = await module.read_data(
        (51.0, 49.0, 3.0, 1.0),
        (date(2024, 1, 1), date(2024, 1, 2)),
        ["NITRATE", "nitrate"],
        10,
        nmax_pts=1,
        verbose_level=2,
    )

    assert result is None
    fetch.assert_awaited_once()
    args = fetch.await_args.args
    assert args[1] == point_id
    assert args[2] == ["2024-01-01", "2024-01-02"]
    assert "1340" in args[3]
    if module is surface:
        init_api.assert_called_once_with("river_qual", version=2)
    else:
        init_api.assert_called_once_with("groundwater_qual")

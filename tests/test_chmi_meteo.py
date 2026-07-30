from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from adapters.API_readers.CHMI_Meteo import CHMI_meteo


@pytest.mark.asyncio
async def test_fetch_json_files_uses_cache(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "json_files_list.txt").write_text("a.json\nb.json\n", encoding="utf-8")
    get = MagicMock()
    monkeypatch.setattr(CHMI_meteo.requests, "get", get)

    assert await CHMI_meteo.fetch_json_files() == ["a.json", "b.json"]
    get.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_json_files_parses_remote_listing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    response = MagicMock()
    response.text = '<a href="a.json">A</a><a href="notes.txt">notes</a>'
    monkeypatch.setattr(
        CHMI_meteo.requests, "get", MagicMock(return_value=response)
    )

    result = await CHMI_meteo.fetch_json_files()

    assert result == ["a.json"]
    assert (tmp_path / "json_files_list.txt").read_text() == "a.json"


@pytest.mark.asyncio
async def test_fetch_json_files_handles_timeout(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        CHMI_meteo.requests,
        "get",
        MagicMock(side_effect=CHMI_meteo.requests.exceptions.Timeout),
    )

    assert await CHMI_meteo.fetch_json_files() == []


def test_process_metadata_normalizes_columns_and_open_end_date():
    metadata = {
        "data": {
            "data": {
                "header": "WSI,BEGIN_DATE,END_DATE,GEOGR1,GEOGR2",
                "values": [
                    [
                        "station",
                        "2020-01-01T00:00:00Z",
                        "3999-01-01T00:00:00Z",
                        17.0,
                        50.0,
                    ]
                ],
            }
        }
    }

    result = CHMI_meteo.process_metadata(metadata)

    assert result.columns.tolist() == [
        "wsi",
        "begin_date",
        "end_date",
        "lon",
        "lat",
    ]
    assert result.loc[0, "end_date"].year == 2262


@pytest.mark.asyncio
async def test_process_file_filters_elements_and_joins_location(monkeypatch, tmp_path):
    payload = {
        "data": {
            "data": {
                "header": "STATION,ELEMENT,DT,VAL",
                "values": [
                    ["station", "T", "2024-01-01T00:00:00Z", "10"],
                    ["station", "OTHER", "2024-01-01T00:00:00Z", "99"],
                ],
            }
        }
    }
    monkeypatch.setattr(CHMI_meteo, "load_json", AsyncMock(return_value=payload))
    locations = pd.DataFrame(
        {
            "wsi": ["station"],
            "begin_date": pd.to_datetime(["2020-01-01T00:00:00Z"]),
            "end_date": pd.to_datetime(["2030-01-01T00:00:00Z"]),
            "lon": [17.0],
            "lat": [50.0],
        }
    )

    result = await CHMI_meteo.process_file(tmp_path / "data.json", locations)

    assert result["element"].tolist() == ["T"]
    assert result["val"].tolist() == [10]
    assert result["lat"].tolist() == [50.0]


@pytest.mark.asyncio
async def test_process_file_returns_empty_frame_for_invalid_payload(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        CHMI_meteo, "load_json", AsyncMock(side_effect=ValueError("bad json"))
    )

    result = await CHMI_meteo.process_file(tmp_path / "bad.json", pd.DataFrame())

    assert result.empty
    assert result.columns.tolist() == [
        "station",
        "element",
        "dt",
        "val",
        "lat",
        "lon",
    ]


@pytest.mark.asyncio
async def test_read_data_aggregates_batches_without_network(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(CHMI_meteo, "DOWNLOAD_DIR", tmp_path / "downloads")
    monkeypatch.setattr(CHMI_meteo, "load_json", AsyncMock(return_value={}))
    locations = pd.DataFrame(
        {
            "wsi": ["station"],
            "begin_date": pd.to_datetime(["2020-01-01T00:00:00Z"]),
            "end_date": pd.to_datetime(["2030-01-01T00:00:00Z"]),
            "lon": [17.0],
            "lat": [50.0],
        }
    )
    monkeypatch.setattr(CHMI_meteo, "process_metadata", lambda _data: locations)
    monkeypatch.setattr(
        CHMI_meteo, "fetch_json_files", AsyncMock(return_value=["data.json"])
    )
    monkeypatch.setattr(
        CHMI_meteo, "download_missing_files", AsyncMock(return_value=None)
    )
    batch = pd.DataFrame(
        {
            "station": ["station", "station"],
            "element": ["T", "SRA"],
            "dt": pd.to_datetime(
                ["2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"]
            ),
            "val": [10.0, 2.0],
            "lat": [50.0, 50.0],
            "lon": [17.0, 17.0],
        }
    )
    monkeypatch.setattr(
        CHMI_meteo, "process_batch", AsyncMock(return_value=batch)
    )

    result = await CHMI_meteo.read_data("metadata.json")

    assert result.loc[0, "station_ID"] == "station"
    assert result.loc[0, "precipitation [mm]"] == 2.0
    assert result.loc[0, "temperature [°c]"] == 10.0
    assert (tmp_path / "CHMI_merged_data.csv").is_file()

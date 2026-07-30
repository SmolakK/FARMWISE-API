import asyncio
import importlib
import io
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pandas as pd
import pytest

daily = importlib.import_module(
    "adapters.API_readers.irish_meteo.Irish MS_daily"
)
monthly = importlib.import_module(
    "adapters.API_readers.irish_meteo.Irish MS_monthly"
)


def _zip_file(name, content):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, content)
    return buffer.getvalue()


def test_daily_generate_links_builds_urls_and_marks_invalid_station(tmp_path):
    stations = tmp_path / "stations.csv"
    pd.DataFrame(
        {
            "station name": ["123", None],
            "latitude": [50.0, 51.0],
            "longitude": [-8.0, -7.0],
        }
    ).to_csv(stations, index=False)

    result = daily.generate_links(stations)

    assert result.loc[0, "download_link"].endswith("dly123.zip")
    assert result.loc[1, "download_link"] == "Invalid station name"


def test_monthly_generate_links_builds_url(tmp_path):
    stations = tmp_path / "stations.csv"
    pd.DataFrame(
        {
            "station name": [123],
            "latitude": [50.0],
            "longitude": [-8.0],
        }
    ).to_csv(stations, index=False)

    result = monthly.generate_links(stations)

    assert result.loc[0, "download_link"].endswith("mly123.zip")


@pytest.mark.asyncio
@pytest.mark.parametrize("module", [daily, monthly])
async def test_check_link_returns_status(module):
    response = SimpleNamespace(status_code=200)
    client = SimpleNamespace(head=AsyncMock(return_value=response))

    assert await module.check_link(client, "https://example.test") == (
        "https://example.test",
        200,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("module", [daily, monthly])
async def test_check_link_returns_zero_on_network_error(module):
    client = SimpleNamespace(
        head=AsyncMock(side_effect=httpx.RequestError("offline"))
    )

    assert await module.check_link(client, "https://example.test") == (
        "https://example.test",
        0,
    )


@pytest.mark.asyncio
async def test_daily_download_and_process_reads_station_archive():
    payload = _zip_file(
        "dly123.csv",
        "station metadata\n"
        "date,rain,temp\n"
        "01-Jan-2024,2.5,10\n",
    )
    response = MagicMock(content=payload)
    client = SimpleNamespace(get=AsyncMock(return_value=response))
    row = pd.Series(
        {
            "download_link": "https://example.test/dly123.zip",
            "station name": "123",
            "latitude": 50.0,
            "longitude": -8.0,
        }
    )

    result = await daily.download_and_process(client, row)

    assert result.loc[0, "date"] == pd.Timestamp("2024-01-01")
    assert result.loc[0, "precipitation [mm]"] == 2.5
    assert result.loc[0, "id"] == "123"


@pytest.mark.asyncio
async def test_daily_download_and_process_retries_network_errors(monkeypatch):
    client = SimpleNamespace(
        get=AsyncMock(side_effect=httpx.RequestError("offline"))
    )
    sleep = AsyncMock()
    monkeypatch.setattr(daily.asyncio, "sleep", sleep)
    row = pd.Series(
        {
            "download_link": "https://example.test/dly123.zip",
            "station name": "123",
            "latitude": 50.0,
            "longitude": -8.0,
        }
    )

    result = await daily.download_and_process(client, row)

    assert result.empty
    assert client.get.await_count == 3
    assert sleep.await_count == 2


@pytest.mark.asyncio
async def test_monthly_download_and_process_reads_station_archive():
    payload = _zip_file(
        "mly123.csv",
        "station metadata\n"
        "year,month,rain,temp\n"
        "2024,1,3.5,10\n",
    )
    response = MagicMock(content=payload)
    client = SimpleNamespace(get=AsyncMock(return_value=response))
    row = pd.Series(
        {
            "download_link": "https://example.test/mly123.zip",
            "station name": 123,
            "latitude": 50.0,
            "longitude": -8.0,
        }
    )

    result = await monthly.download_and_process(client, row)

    assert result.loc[0, "date"] == pd.Timestamp("2024-01-01")
    assert result.loc[0, "precipitation [mm]"] == 3.5
    assert result.loc[0, "id"] == 123


@pytest.mark.asyncio
@pytest.mark.parametrize("module", [daily, monthly])
async def test_download_and_process_rejects_archive_without_station_csv(module):
    prefix = "dly" if module is daily else "mly"
    response = MagicMock(content=_zip_file("other.csv", "data"))
    client = SimpleNamespace(get=AsyncMock(return_value=response))
    row = pd.Series(
        {
            "download_link": f"https://example.test/{prefix}123.zip",
            "station name": 123,
            "latitude": 50.0,
            "longitude": -8.0,
        }
    )

    assert (await module.download_and_process(client, row)).empty


class _ClientContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


@pytest.mark.asyncio
@pytest.mark.parametrize("module", [daily, monthly])
async def test_process_working_links_returns_empty_without_status_200(module):
    result = await module.process_working_links(
        pd.DataFrame(
            {
                "station name": [123],
                "download_link": ["https://example.test"],
                "status": [404],
            }
        )
    )

    assert result.empty


@pytest.mark.asyncio
@pytest.mark.parametrize("module", [daily, monthly])
async def test_process_working_links_combines_successful_results(
    monkeypatch, module
):
    monkeypatch.setattr(module.httpx, "AsyncClient", _ClientContext)
    processed = pd.DataFrame(
        {
            "id": [123],
            "lat": [50.0],
            "lon": [-8.0],
            "date": pd.to_datetime(["2024-01-01"]),
            "precipitation [mm]": [2.0],
        }
    )
    monkeypatch.setattr(
        module, "download_and_process", AsyncMock(return_value=processed)
    )
    if module is daily:
        async def gather(*tasks, **_kwargs):
            return await asyncio.gather(*tasks)

        monkeypatch.setattr(module.tqdm, "gather", gather)

    result = await module.process_working_links(
        pd.DataFrame(
            {
                "station name": [123],
                "download_link": ["https://example.test"],
                "status": [200],
            }
        )
    )

    assert result.equals(processed)


@pytest.mark.asyncio
async def test_daily_read_data_filters_space_and_time(monkeypatch):
    monkeypatch.setattr(daily, "adapter_data", lambda *_args: "stations.csv")
    links = pd.DataFrame(
        {
            "station name": ["123"],
            "latitude": [50.0],
            "longitude": [-8.0],
            "download_link": ["https://example.test/dly123.zip"],
        }
    )
    monkeypatch.setattr(daily, "generate_links", lambda _path: links)
    monkeypatch.setattr(daily.httpx, "AsyncClient", _ClientContext)
    monkeypatch.setattr(
        daily, "check_link", AsyncMock(return_value=(links.loc[0, "download_link"], 200))
    )

    async def gather(*tasks, **_kwargs):
        return await asyncio.gather(*tasks)

    monkeypatch.setattr(daily.tqdm, "gather", gather)
    combined = pd.DataFrame(
        {
            "id": ["123", "123"],
            "lat": [50.0, 50.0],
            "lon": [-8.0, -8.0],
            "date": pd.to_datetime(["2024-01-01", "2025-01-01"]),
            "precipitation [mm]": ["2.5", "9.0"],
        }
    )
    monkeypatch.setattr(
        daily, "process_working_links", AsyncMock(return_value=combined)
    )

    def prepare(frame, **_kwargs):
        return frame.assign(S2CELL="cell")

    monkeypatch.setattr(daily, "prepare_coordinates", prepare)

    result = await daily.read_data(
        (51.0, 49.0, -7.0, -9.0),
        ("2024-01-01", "2024-01-02"),
        ["precipitation"],
        10,
    )

    assert result.iloc[0, 0] == 2.5


@pytest.mark.asyncio
async def test_daily_read_data_returns_empty_when_downloads_fail(monkeypatch):
    monkeypatch.setattr(daily, "adapter_data", lambda *_args: "stations.csv")
    links = pd.DataFrame(
        {
            "station name": ["123"],
            "latitude": [50.0],
            "longitude": [-8.0],
            "download_link": ["https://example.test/dly123.zip"],
        }
    )
    monkeypatch.setattr(daily, "generate_links", lambda _path: links)
    monkeypatch.setattr(daily.httpx, "AsyncClient", _ClientContext)
    monkeypatch.setattr(
        daily, "check_link", AsyncMock(return_value=(links.loc[0, "download_link"], 0))
    )

    async def gather(*tasks, **_kwargs):
        return await asyncio.gather(*tasks)

    monkeypatch.setattr(daily.tqdm, "gather", gather)
    monkeypatch.setattr(
        daily, "process_working_links", AsyncMock(return_value=pd.DataFrame())
    )

    result = await daily.read_data(
        (51.0, 49.0, -7.0, -9.0),
        ("2024-01-01", "2024-01-02"),
        ["precipitation"],
        10,
    )

    assert result.empty

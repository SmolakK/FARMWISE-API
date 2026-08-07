import asyncio
import io
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pandas as pd
import pytest

from adapters.API_readers.UA_sw_quality import ukrainian_surface_water as ua_water
from adapters.API_readers.epa_ireland import epa_gw
from adapters.API_readers.gios_gw import gios_gw


def test_ukrainian_load_and_clean_data():
    content = (
        "Controle_Date;drop1;drop2;drop3;drop4;nitrogen;Unnamed: 6\n"
        "2024-01-02;a;b;c;d;1.5;ignored\n"
    ).encode("utf-8-sig")

    result = ua_water.load_and_clean_data(content)

    assert result.columns.tolist() == ["Controle_Date", "nitrogen"]
    assert result.loc[0, "Controle_Date"] == pd.Timestamp("2024-01-02")


def test_ukrainian_load_and_clean_data_returns_none_for_invalid_csv():
    assert ua_water.load_and_clean_data(b"\xff") is None


@pytest.mark.asyncio
async def test_ukrainian_download_file_content_checks_response():
    response = MagicMock()
    response.content = b"csv"
    client = SimpleNamespace(get=AsyncMock(return_value=response))

    assert await ua_water.download_file_content(client, "https://example.test") == b"csv"
    response.raise_for_status.assert_called_once_with()


def _zip_payload():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "data.csv",
            "\n" * 7
            + "timestamp;level\n"
            + "2024-01-01;95.5\n",
        )
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_epa_process_link_reads_zip_and_calculates_depth():
    response = MagicMock()
    response.aread = AsyncMock(return_value=_zip_payload())

    class Stream:
        async def __aenter__(self):
            return response

        async def __aexit__(self, *_args):
            return False

    client = SimpleNamespace(stream=lambda *_args, **_kwargs: Stream())
    row = pd.Series(
        {
            "id": "station",
            "download_link": "https://example.test/data.zip",
            "lat": 50.0,
            "lon": 17.0,
            "measuring_point_height": 100.0,
        }
    )

    result = await epa_gw.process_link(client, row)

    assert result.loc[0, "groundwater level [m]"] == 95.5
    assert result.loc[0, "groundwater depth [m b.g.l]"] == 4.5
    response.raise_for_status.assert_called_once_with()


@pytest.mark.asyncio
async def test_epa_read_data_returns_empty_without_downloads(monkeypatch):
    monkeypatch.setattr(epa_gw, "fetch_all_data", AsyncMock(return_value=[None]))

    result = await epa_gw.read_data(
        (51.0, 49.0, 18.0, 16.0),
        ("2024-01-01", "2024-01-02"),
        ["groundwater quantity"],
        10,
    )

    assert result.empty


@pytest.mark.asyncio
async def test_epa_read_data_filters_and_converts_depth_to_cm(monkeypatch):
    downloaded = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-01", "2025-01-01"]),
            "groundwater level [m]": [95.5, 95.0],
            "groundwater depth [m b.g.l]": [4.5, 5.0],
            "id": ["station", "station"],
            "lat": [50.0, 50.0],
            "lon": [17.0, 17.0],
        }
    )
    monkeypatch.setattr(
        epa_gw, "fetch_all_data", AsyncMock(return_value=[downloaded])
    )

    def prepare(coordinates, **_kwargs):
        return coordinates.assign(S2CELL="cell")

    monkeypatch.setattr(epa_gw, "prepare_coordinates", prepare)

    result = await epa_gw.read_data(
        (51.0, 49.0, 18.0, 16.0),
        ("2024-01-01", "2024-01-02"),
        ["groundwater quantity"],
        10,
    )

    assert result.iloc[0, 0] == 450.0


@pytest.mark.asyncio
async def test_epa_read_data_applies_groundwater_policy(monkeypatch):
    downloaded = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-01"] * 3),
            "groundwater level [m]": [99.0, 97.0, 0.0],
            "groundwater depth [m b.g.l]": [1.0, 3.0, 100.0],
            "id": ["a", "b", "c"],
            "lat": [50.0, 50.1, 50.2],
            "lon": [17.0, 17.1, 17.2],
        }
    )
    monkeypatch.setattr(
        epa_gw, "fetch_all_data", AsyncMock(return_value=[downloaded])
    )
    monkeypatch.setattr(
        epa_gw,
        "prepare_coordinates",
        lambda coordinates, **_kwargs: coordinates.assign(S2CELL="cell"),
    )

    result = await epa_gw.read_data(
        (51.0, 49.0, 18.0, 16.0),
        ("2024-01-01", "2024-01-02"),
        ["groundwater quantity"],
        10,
        within_source_aggregation_methods={
            "default": "mean",
            "groundwater quantity": "median",
        },
    )

    assert result.iloc[0, 0] == 300.0


@pytest.mark.asyncio
async def test_gios_groundwater_link_extractors(monkeypatch):
    main_response = MagicMock()
    main_response.text = (
        '<a href="/wyniki-badan/a.html">A</a>'
        '<a href="/wyniki-badan/a.html">A duplicate</a>'
    )
    xlsx_response = MagicMock()
    xlsx_response.text = (
        '<a href="/files/data.xlsx">Data / 2024</a>'
        '<a href="/files/data.xlsx">Duplicate</a>'
    )
    client = SimpleNamespace(
        get=AsyncMock(side_effect=[main_response, xlsx_response])
    )

    pages = await gios_gw.find_subpage_links("https://example.test/main", client)
    files = await gios_gw.find_xlsx_links(pages[0], client)

    assert pages == ["https://example.test/wyniki-badan/a.html"]
    assert files == [("https://example.test/files/data.xlsx", "Data - 2024")]


@pytest.mark.asyncio
async def test_gios_groundwater_fails_before_network_without_xlsx_reader(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(gios_gw.importlib.util, "find_spec", lambda _name: None)
    monkeypatch.setattr(gios_gw.httpx, "AsyncClient", client)

    with pytest.raises(RuntimeError, match="openpyxl"):
        await gios_gw.read_data(
            (55.0, 49.0, 24.0, 14.0),
            ("2024-01-01", "2024-01-02"),
            ["groundwater quality"],
            10,
        )

    client.assert_not_called()


@pytest.mark.asyncio
async def test_gios_groundwater_deduplicates_files_across_pages(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(gios_gw, "_require_excel_reader", lambda: None)
    monkeypatch.setattr(gios_gw.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(
        gios_gw,
        "find_subpage_links",
        AsyncMock(return_value=["page-a", "page-b"]),
    )
    monkeypatch.setattr(
        gios_gw,
        "find_xlsx_links",
        AsyncMock(return_value=[("same.xlsx", "Same")]),
    )
    process = AsyncMock(return_value=pd.DataFrame())
    monkeypatch.setattr(gios_gw, "process_xlsx", process)

    result = await gios_gw.read_data(
        (55.0, 49.0, 24.0, 14.0),
        ("2024-01-01", "2024-01-02"),
        ["groundwater quality"],
        10,
    )

    assert result.empty
    process.assert_awaited_once()


@pytest.mark.asyncio
async def test_gios_groundwater_link_extractor_handles_request_error():
    client = SimpleNamespace(
        get=AsyncMock(side_effect=httpx.RequestError("offline"))
    )

    assert await gios_gw.find_subpage_links("https://example.test", client) == []


def test_gios_groundwater_standardizes_coordinates_numbers_and_dates(monkeypatch):
    monkeypatch.setattr(
        gios_gw.transformer,
        "transform",
        lambda _x, _y: ([17.0], [50.0]),
    )
    frame = pd.DataFrame(
        {
            "PUWG 1992 X": [500000],
            "PUWG 1992 Y": [300000],
            "id": ["7"],
            "date": ["02.01.2024"],
            "Depth": ["<2,5"],
        }
    )
    schema = {
        "id": "int",
        "date": "datetime",
        "lat": "float",
        "lon": "float",
        "Depth": "float",
    }

    result = gios_gw.standardize_dataframe(frame, schema)

    assert result.loc[0, "id"] == 7
    assert result.loc[0, "date"] == pd.Timestamp("2024-01-02")
    assert result.loc[0, "Depth"] == 2.5
    assert result.loc[0, "lat"] == 50.0
    assert result.loc[0, "lon"] == 17.0


def test_gios_groundwater_filters_pages_to_requested_years():
    links = [
        "https://example.test/wyniki-badan-2004-2007.html",
        "https://example.test/wyniki-badan-2023.html",
        "https://example.test/wyniki-badan-2024.html",
        "https://example.test/undated.html",
    ]

    result = gios_gw._filter_links_by_time_range(
        links,
        ("2006-01-01", "2006-12-31"),
    )

    assert result == [links[0], links[3]]


@pytest.mark.asyncio
async def test_gios_groundwater_read_data_returns_empty_without_pages(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(gios_gw.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(
        gios_gw, "find_subpage_links", AsyncMock(return_value=[])
    )

    result = await gios_gw.read_data(
        (55.0, 49.0, 24.0, 14.0),
        ("2024-01-01", "2024-01-02"),
        ["groundwater quality"],
        10,
    )

    assert result.empty

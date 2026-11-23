from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pandas as pd
import pytest
from shapely.geometry import box, mapping

from farmwise_api.adapters.API_readers.corine import corine_read
from farmwise_api.adapters.API_readers.corine.corine_read import (
    OUTPUT_COLUMN,
    read_data,
)


def _response(payload=None, status=200):
    response = MagicMock(status_code=status)
    response.json.return_value = payload or {}
    return response


def _feature(geometry, field, code):
    return {"geometry": mapping(geometry), "properties": {field: code}}


class FakeEEA:
    """Answers count queries with len(features) and pages by offset.

    ``failures`` maps an offset to how many times its page fails first;
    ``failing_sizes`` makes every page of at least that size fail.
    """

    def __init__(self, features, failures=None, failing_sizes=None, fail_with=None):
        self.features = features
        self.failures = dict(failures or {})
        self.failing_sizes = failing_sizes
        self.fail_with = fail_with or (lambda: _response(status=500))
        self.calls = []

    async def get(self, url, params):
        self.calls.append((url, dict(params)))
        if params.get("returnCountOnly") == "true":
            return _response({"count": len(self.features)})
        offset = params["resultOffset"]
        size = params["resultRecordCount"]
        if self.failures.get(offset, 0) > 0:
            self.failures[offset] -= 1
            return self.fail_with()
        if self.failing_sizes is not None and size >= self.failing_sizes:
            return self.fail_with()
        return _response({"features": self.features[offset:offset + size]})

    def pages(self):
        return [params for _, params in self.calls if "resultOffset" in params]


@pytest.fixture
def eea(monkeypatch):
    """Install a FakeEEA as the HTTP client; returns a factory for it."""
    monkeypatch.setattr(corine_read.asyncio, "sleep", AsyncMock())

    def install(server):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=server)
        client.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr(corine_read.httpx, "AsyncClient", lambda **_: client)
        return server

    return install


@pytest.fixture
def two_cells(monkeypatch):
    monkeypatch.setattr(
        corine_read,
        "_s2_cell_polygons",
        lambda *_: {"west-cell": box(0, 0, 1, 1), "east-cell": box(1, 0, 2, 1)},
    )


@pytest.mark.asyncio
async def test_read_data_returns_dominant_categorical_class(eea, two_cells):
    server = eea(FakeEEA([
        _feature(box(0, 0, 1.4, 1), "Code_18", "211"),
        _feature(box(1.4, 0, 2, 1), "Code_18", "311"),
    ]))

    result = await read_data(
        (1, 0, 2, 0), ("2018-01-01", "2018-12-31"), ["land cover"], 8
    )

    assert isinstance(result, pd.DataFrame)
    assert result.index.name == "Timestamp"
    assert result.columns.names[1] == "S2CELL"
    assert result.shape == (365, 2)
    assert (result[(OUTPUT_COLUMN, "west-cell")] == 211).all()
    assert (result[(OUTPUT_COLUMN, "east-cell")] == 311).all()
    url, params = server.calls[-1]
    assert "CLC2018_WM/MapServer/0/query" in url
    assert params["f"] == "geojson"
    assert params["outFields"] == "Code_18"


@pytest.mark.asyncio
async def test_read_data_uses_latest_snapshot_not_later_than_request(eea, monkeypatch):
    monkeypatch.setattr(corine_read, "_s2_cell_polygons", lambda *_: {"cell": box(0, 0, 1, 1)})
    server = eea(FakeEEA([_feature(box(0, 0, 1, 1), "Code_12", 211)]))

    await read_data((1, 0, 1, 0), ("2017-01-01", "2017-01-02"), ["land cover"], 8)

    assert all("CLC2012_WM/MapServer/0/query" in url for url, _ in server.calls)


@pytest.mark.asyncio
async def test_pages_are_requested_by_offset_in_a_stable_order(eea, two_cells):
    """The count comes first; pages are then independent and ordered."""
    features = [_feature(box(0, 0, 1, 1), "Code_18", 211)] * 2500
    server = eea(FakeEEA(features))

    await read_data((1, 0, 2, 0), ("2018-01-01", "2018-01-02"), ["land cover"], 8)

    assert server.calls[0][1]["returnCountOnly"] == "true"
    pages = server.pages()
    assert sorted((p["resultOffset"], p["resultRecordCount"]) for p in pages) == [
        (0, 1000), (1000, 1000), (2000, 500),
    ]
    assert all(p["orderByFields"] == "OBJECTID" for p in pages)
    # Geometry is simplified on the server to the scale of the cells.
    assert all(0 < p["maxAllowableOffset"] <= 0.01 for p in pages)


@pytest.mark.asyncio
async def test_read_data_retries_a_page_the_server_fails_once(eea, two_cells):
    """A 500 on one page no longer throws away the whole source."""
    server = eea(FakeEEA(
        [_feature(box(0, 0, 2, 1), "Code_18", "211")], failures={0: 1}
    ))

    result = await read_data(
        (1, 0, 2, 0), ("2018-01-01", "2018-01-31"), ["land cover"], 8
    )

    assert len(server.pages()) == 2
    assert (result[(OUTPUT_COLUMN, "west-cell")] == 211).all()
    corine_read.asyncio.sleep.assert_awaited_once()


@pytest.mark.asyncio
async def test_arcgis_error_body_with_500_is_retried(eea, two_cells):
    """ArcGIS reports its own failures as HTTP 200 with an error body."""
    server = eea(FakeEEA(
        [_feature(box(0, 0, 2, 1), "Code_18", 211)],
        failures={0: 2},
        fail_with=lambda: _response({"error": {"code": 500, "message": "Error"}}),
    ))

    result = await read_data(
        (1, 0, 2, 0), ("2018-01-01", "2018-01-02"), ["land cover"], 8
    )

    assert len(server.pages()) == 3
    assert not result.empty


@pytest.mark.asyncio
async def test_arcgis_error_body_that_is_not_transient_fails_at_once(eea, two_cells):
    eea(FakeEEA(
        [_feature(box(0, 0, 2, 1), "Code_18", 211)],
        failures={0: 1},
        fail_with=lambda: _response({"error": {"code": 400, "message": "Invalid"}}),
    ))

    with pytest.raises(RuntimeError, match="CORINE query failed"):
        await read_data(
            (1, 0, 2, 0), ("2018-01-01", "2018-01-02"), ["land cover"], 8
        )


@pytest.mark.asyncio
async def test_page_that_keeps_failing_is_split_in_halves(eea, two_cells):
    """The server fails heavy pages; smaller pieces of the same range succeed."""
    features = (
        [_feature(box(0, 0, 1, 1), "Code_18", 211)] * 600
        + [_feature(box(1, 0, 2, 1), "Code_18", 311)] * 400
    )
    server = eea(FakeEEA(features, failing_sizes=1000))

    result = await read_data(
        (1, 0, 2, 0), ("2018-01-01", "2018-01-02"), ["land cover"], 8
    )

    served = {
        (p["resultOffset"], p["resultRecordCount"]) for p in server.pages()
    } - {(0, 1000)}
    assert served == {(0, 500), (500, 500)}
    assert (result[(OUTPUT_COLUMN, "west-cell")] == 211).all()
    assert (result[(OUTPUT_COLUMN, "east-cell")] == 311).all()


@pytest.mark.asyncio
async def test_timeouts_are_retried(eea, two_cells):
    calls = {"n": 0}
    server = FakeEEA([_feature(box(0, 0, 2, 1), "Code_18", 211)])
    real_get = server.get

    async def flaky_get(url, params):
        if "resultOffset" in params and calls["n"] == 0:
            calls["n"] += 1
            raise httpx.ReadTimeout("slow page")
        return await real_get(url, params)

    server.get = flaky_get
    eea(server)

    result = await read_data(
        (1, 0, 2, 0), ("2018-01-01", "2018-01-02"), ["land cover"], 8
    )

    assert not result.empty


def test_areas_from_several_pages_are_added_up():
    cells = corine_read._CellAreas({"a": box(0, 0, 1, 1), "b": box(1, 0, 2, 1)})
    first_page = cells.measure(
        [
            _feature(box(0, 0, 0.7, 1), "Code_18", 211),
            _feature(box(1, 0, 1.3, 1), "Code_18", 112),
        ],
        "Code_18",
    )
    # 311 has the largest single polygon in "b", but 112 has more in total
    # once the second page is added.
    second_page = cells.measure(
        [_feature(box(1.3, 0, 1.6, 1), "Code_18", 112),
         _feature(box(1.6, 0, 2, 1), "Code_18", 311)],
        "Code_18",
    )

    assert cells.dominant([first_page, second_page]) == {"a": 211, "b": 112}


def test_exact_area_tie_goes_to_the_smallest_code():
    cells = corine_read._CellAreas({"a": box(0, 0, 1, 1)})
    partial = pd.Series(
        [5.0, 5.0], index=pd.MultiIndex.from_tuples([(0, 312), (0, 211)])
    )

    assert cells.dominant([partial]) == {"a": 211}

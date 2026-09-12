"""Met Éireann daily rainfall, read from the official annual grids.

This adapter used to download one archive per station and stitch them
together. It now reads Met Éireann's published annual rainfall grid
(``IRL_DLY_RR_<year>_grid.csv.gz``), which is projected in Irish Grid (TM65,
EPSG:29902), stores one column per day named ``X<YYYYMMDD>``, and publishes
values in tenths of a millimetre.
"""

import gzip
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from farmwise_api.adapters.API_readers.irish_meteo import irish_ms_daily as daily

# TM65 eastings/northings for real places, so the bounding-box filter is
# exercised against coordinates the adapter would actually meet.
DUBLIN = (315920.0, 234694.1)      # 53.35 N, 6.26 W
CORK = (167698.4, 72025.4)         # 51.90 N, 8.47 W
DONEGAL = (84574.8, 407297.8)      # 54.90 N, 9.80 W - outside the test bbox

# A bounding box around Dublin only (N, S, E, W).
DUBLIN_BBOX = (53.6, 53.1, -6.0, -6.5)


def _grid_file(tmp_path, rows, columns):
    """Write a gzipped annual grid in Met Éireann's published layout."""
    frame = pd.DataFrame(rows, columns=columns)
    path = Path(tmp_path) / "IRL_DLY_RR_2018_grid.csv.gz"
    with gzip.open(path, "wt", newline="") as handle:
        frame.to_csv(handle, index=False)
    return path


def test_grid_subset_selects_the_bounding_box_and_converts_units():
    """Only cells inside the box survive, and tenths of a mm become mm."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = _grid_file(
            tmp,
            [
                [DUBLIN[0], DUBLIN[1], 123, 0],
                [CORK[0], CORK[1], 250, 40],
                [DONEGAL[0], DONEGAL[1], 999, 10],
            ],
            ["east", "north", "X20180101", "X20180102"],
        )
        dates = pd.to_datetime(["2018-01-01", "2018-01-02"])

        frame = daily._read_grid_subset(path, dates, DUBLIN_BBOX)

    assert not frame.empty
    assert set(frame.columns) >= {"lat", "lon", "Timestamp", "precipitation [mm]"}

    # Cork and Donegal are outside the requested box.
    assert frame["lat"].between(53.1, 53.6).all()
    assert frame["lon"].between(-6.5, -6.0).all()

    # 123 tenths of a millimetre is 12.3 mm.
    first_day = frame[frame["Timestamp"] == pd.Timestamp("2018-01-01").date()]
    assert first_day["precipitation [mm]"].iloc[0] == pytest.approx(12.3)

    # A published zero stays a zero rather than being dropped as falsy.
    second_day = frame[frame["Timestamp"] == pd.Timestamp("2018-01-02").date()]
    assert second_day["precipitation [mm]"].iloc[0] == pytest.approx(0.0)


def test_grid_subset_reads_only_the_requested_days():
    """A year holds 365 day columns; only the requested ones are melted."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = _grid_file(
            tmp,
            [[DUBLIN[0], DUBLIN[1], 10, 20, 30]],
            ["east", "north", "X20180101", "X20180102", "X20180103"],
        )
        dates = pd.to_datetime(["2018-01-02"])

        frame = daily._read_grid_subset(path, dates, DUBLIN_BBOX)

    assert list(frame["Timestamp"].unique()) == [
        pd.Timestamp("2018-01-02").date()
    ]
    assert frame["precipitation [mm]"].iloc[0] == pytest.approx(2.0)


def test_grid_subset_returns_an_empty_frame_outside_ireland():
    """A request that meets no grid cell must not raise."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = _grid_file(
            tmp,
            [[DONEGAL[0], DONEGAL[1], 50]],
            ["east", "north", "X20180101"],
        )

        frame = daily._read_grid_subset(
            path, pd.to_datetime(["2018-01-01"]), DUBLIN_BBOX
        )

    assert frame.empty
    assert list(frame.columns) == [
        "lat", "lon", "Timestamp", "precipitation [mm]"
    ]


def test_missing_values_are_dropped_not_zero_filled():
    """An absent reading must not be read as no rainfall."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = _grid_file(
            tmp,
            [[DUBLIN[0], DUBLIN[1], "", 55]],
            ["east", "north", "X20180101", "X20180102"],
        )

        frame = daily._read_grid_subset(
            path, pd.to_datetime(["2018-01-01", "2018-01-02"]), DUBLIN_BBOX
        )

    assert set(frame["Timestamp"]) == {pd.Timestamp("2018-01-02").date()}
    assert frame["precipitation [mm]"].iloc[0] == pytest.approx(5.5)


@pytest.mark.asyncio
async def test_download_grid_reuses_the_cached_annual_file(tmp_path, monkeypatch):
    """The annual grid is large; it must be fetched once and then reused."""
    cached = tmp_path / "IRL_DLY_RR_2018_grid.csv.gz"
    cached.write_bytes(b"already here")
    monkeypatch.setattr(daily, "adapter_cache", lambda *_parts: tmp_path)

    client = SimpleNamespace(
        stream=AsyncMock(side_effect=AssertionError("must not download again"))
    )

    path = await daily._download_grid(client, 2018)

    assert path == cached
    client.stream.assert_not_called()


@pytest.mark.asyncio
async def test_read_data_spans_every_requested_year(monkeypatch, tmp_path):
    """A request crossing a year boundary reads one grid per year."""
    requested_years = []

    async def fake_download(_client, year):
        requested_years.append(year)
        return tmp_path / f"IRL_DLY_RR_{year}_grid.csv.gz"

    def fake_subset(_path, dates, _spatial_range):
        return pd.DataFrame({
            "lat": [53.35] * len(dates),
            "lon": [-6.26] * len(dates),
            "Timestamp": [d.date() for d in dates],
            "precipitation [mm]": [1.0] * len(dates),
        })

    monkeypatch.setattr(daily, "_download_grid", fake_download)
    monkeypatch.setattr(daily, "_read_grid_subset", fake_subset)
    monkeypatch.setattr(
        daily, "prepare_coordinates",
        lambda frame, spatial_range, level: frame.assign(
            S2CELL=["cell-1"] * len(frame)
        ),
    )

    result = await daily.read_data(
        DUBLIN_BBOX, ("2017-12-30", "2018-01-02"), ["precipitation"], 10
    )

    assert requested_years == [2017, 2018], (
        "every year the request spans must be read"
    )
    assert not result.empty
    assert "S2CELL" in result.columns.names


@pytest.mark.asyncio
async def test_read_data_rejects_a_reversed_time_range():
    with pytest.raises(ValueError, match="must not be after"):
        await daily.read_data(
            DUBLIN_BBOX, ("2018-06-02", "2018-06-01"), ["precipitation"], 10
        )

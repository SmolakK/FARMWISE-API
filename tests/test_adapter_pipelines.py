from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from farmwise_api.adapters.API_readers.EuroCropV2 import EuroCropV2_read
from farmwise_api.adapters.API_readers.IFSGRID import IFSGRID_read
from farmwise_api.adapters.API_readers.correctiv import correctiv_read


@pytest.mark.asyncio
async def test_eurocrop_read_data_returns_empty_when_bbox_has_no_points(monkeypatch):
    monkeypatch.setattr(EuroCropV2_read, "adapter_data", lambda *_args: "points.csv")
    monkeypatch.setattr(
        EuroCropV2_read, "extract_data_by_bbox", lambda *_args: pd.DataFrame()
    )

    result = await EuroCropV2_read.read_data(
        (51.0, 49.0, 18.0, 16.0),
        ("2024-01-01", "2024-01-02"),
        ["land cover"],
        10,
    )

    assert result.empty


@pytest.mark.asyncio
async def test_eurocrop_read_data_runs_transformation_pipeline(monkeypatch):
    extracted = pd.DataFrame({"lat": [50.0], "lon": [17.0], "c2024": [2]})
    aggregated = pd.DataFrame(
        {"c2024": [2]}, index=pd.Index(["cell"], name="S2CELL")
    )
    melted = pd.DataFrame(
        [[2]],
        index=pd.to_datetime(["2024-01-01"]),
        columns=pd.MultiIndex.from_tuples([("c", "cell")]),
    )
    monkeypatch.setattr(EuroCropV2_read, "adapter_data", lambda *_args: "points.csv")
    monkeypatch.setattr(
        EuroCropV2_read, "extract_data_by_bbox", lambda *_args: extracted
    )
    monkeypatch.setattr(EuroCropV2_read, "extract_years", lambda *_args: extracted)
    monkeypatch.setattr(
        EuroCropV2_read, "data_agregation", lambda *_args: aggregated
    )
    melt = MagicMock(return_value=melted)
    monkeypatch.setattr(EuroCropV2_read, "data_melting", melt)

    result = await EuroCropV2_read.read_data(
        (51.0, 49.0, 18.0, 16.0),
        ("2024-01-01", "2024-01-02"),
        ["land cover"],
        10,
    )

    assert result.columns.get_level_values(0).tolist() == [
        "Original cultivation code in the annual GSA layer"
    ]
    melt.assert_called_once_with(aggregated, ("2024-01-01", "2024-01-02"))


@pytest.mark.asyncio
async def test_correctiv_read_data_runs_transformation_pipeline(monkeypatch):
    source = pd.DataFrame(
        {
            "min_gwl": [1.0],
            "mean_gwl": [2.0],
            "max_gwl": [3.0],
            "lat": [50.0],
            "lon": [17.0],
            "date": pd.to_datetime(["2024-01-01"]),
        }
    )
    prepared = source.assign(S2CELL="cell")
    daily = prepared[
        ["min_gwl", "mean_gwl", "max_gwl", "S2CELL", "date"]
    ].copy()
    monkeypatch.setattr(correctiv_read, "adapter_data", lambda *_args: "data.parquet")
    monkeypatch.setattr(correctiv_read, "spatial_extraction", lambda *_args: source)
    monkeypatch.setattr(correctiv_read, "time_extraction_wide", lambda data, _range: data)
    monkeypatch.setattr(correctiv_read, "cols_extraction", lambda data: data)
    monkeypatch.setattr(
        correctiv_read, "prepare_coordinates", lambda *_args: prepared
    )
    monkeypatch.setattr(correctiv_read, "data_melting", lambda _data: daily)
    monkeypatch.setattr(correctiv_read, "time_extraction", lambda data, _range: data)

    result = await correctiv_read.read_data(
        (51.0, 49.0, 18.0, 16.0),
        ("2024-01-01", "2024-01-02"),
        ["groundwater quantity"],
        10,
    )

    assert result.loc[pd.Timestamp("2024-01-01"), (
        "Mean Groundwater Depth [a.s.l]",
        "cell",
    )] == 2.0


@pytest.mark.asyncio
async def test_ifsgrid_read_data_returns_none_without_temporal_overlap(monkeypatch):
    monkeypatch.setattr(IFSGRID_read, "check_overlap", lambda _range: (None, None))

    result = await IFSGRID_read.read_data(
        (51.0, 49.0, 18.0, 16.0),
        ("2018-01-01", "2019-01-01"),
        ["land cover"],
        10,
    )

    assert result is None


@pytest.mark.asyncio
async def test_ifsgrid_read_data_returns_none_without_spatial_data(monkeypatch):
    monkeypatch.setattr(
        IFSGRID_read,
        "check_overlap",
        lambda _range: (date(2024, 1, 1), date(2024, 1, 2)),
    )
    monkeypatch.setattr(IFSGRID_read, "stack_values", lambda *_args: pd.DataFrame())

    result = await IFSGRID_read.read_data(
        (51.0, 49.0, 18.0, 16.0),
        ("2024-01-01", "2024-01-02"),
        ["land cover"],
        10,
    )

    assert result is None


@pytest.mark.asyncio
async def test_ifsgrid_read_data_maps_columns(monkeypatch):
    monkeypatch.setattr(
        IFSGRID_read,
        "check_overlap",
        lambda _range: (date(2024, 1, 1), date(2024, 1, 2)),
    )
    monkeypatch.setattr(
        IFSGRID_read,
        "stack_values",
        lambda *_args: pd.DataFrame({"lat": [50.0], "lon": [17.0], "UAA": [2]}),
    )
    monkeypatch.setattr(
        IFSGRID_read,
        "aggregate_spatial",
        lambda *_args: pd.DataFrame({"S2CELL": ["cell"], "UAA": [2]}),
    )
    expanded = pd.DataFrame(
        [[2.0]],
        index=pd.to_datetime(["2024-01-01"]),
        columns=pd.MultiIndex.from_tuples([("UAA", "cell")]),
    )
    monkeypatch.setattr(IFSGRID_read, "expand_time_dimension", lambda *_args: expanded)

    result = await IFSGRID_read.read_data(
        (51.0, 49.0, 18.0, 16.0),
        ("2024-01-01", "2024-01-02"),
        ["land cover"],
        10,
    )

    assert result.columns.tolist() == [
        ("Total utilised agricultural area", "cell")
    ]

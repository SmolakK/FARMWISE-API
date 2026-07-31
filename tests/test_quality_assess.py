import json

import pandas as pd
import pytest

from core import quality_assess


def _quality_frame():
    columns = pd.MultiIndex.from_tuples(
        [
            ("Temperature [C]", "cell-1"),
            ("Precipitation [mm]", "cell-1"),
        ]
    )
    return pd.DataFrame(
        [
            [10.0, 1.0],
            [None, -1.0],
            [100.0, 600.0],
        ],
        index=pd.to_datetime(
            ["2024-01-01", "2024-01-02", "2024-01-03"]
        ),
        columns=columns,
    )


def test_bbox_intersection():
    assert quality_assess.bbox_intersects(
        (55, 49, 24, 14), (52, 50, 20, 16)
    ) == (True, (52, 50, 20, 16))
    assert quality_assess.bbox_intersects(
        (55, 49, 24, 14), (45, 40, 10, 5)
    ) == (False, None)


def test_assess_data_quality_reports_completeness_and_implausible_values(
    monkeypatch,
):
    monkeypatch.setattr(
        quality_assess,
        "get_s2_cells",
        lambda _bbox, _level: ["cell-1", "cell-2"],
    )
    frame = _quality_frame()
    original = frame.copy(deep=True)

    report = quality_assess.assess_data_quality(
        frame,
        {
            "api_name": "mock",
            "source": "provider.mock",
            "columns": ["Temperature [C]", "Precipitation [mm]"],
        },
        (
            (55, 49, 24, 14),
            ("2020-01-01", "2030-01-01"),
            ["temperature", "precipitation"],
        ),
        {
            "bbox": (52, 50, 20, 16),
            "level": 10,
            "time_from": "2024-01-01",
            "time_to": "2024-01-03",
            "factors": ["temperature", "precipitation"],
        },
    )

    pd.testing.assert_frame_equal(frame, original)
    assert report["S2_completeness"] == 0.5
    assert report["total_missing_values"] == pytest.approx(1 / 6)
    assert report["missing_days"] == pytest.approx(1 / 3)
    assert report["factor_missing_value_rates"]["Temperature [C]"] == pytest.approx(
        1 / 3
    )
    assert report["data_delay"] == 0
    assert report["data_cutshort"] == 0
    assert report["factors_returned_completeness"] == 1
    assert report["implausible_value_rates"]["Temperature [C]"] == 0.5
    assert report["implausible_value_rates"]["Precipitation [mm]"] == pytest.approx(
        2 / 3
    )


def test_assess_data_quality_handles_no_intersection_or_data(monkeypatch):
    monkeypatch.setattr(
        quality_assess,
        "get_s2_cells",
        lambda _bbox, _level: pytest.fail("coverer should not be called"),
    )

    report = quality_assess.assess_data_quality(
        pd.DataFrame(),
        {"api_name": "mock", "columns": []},
        ((55, 49, 24, 14), ("2020-01-01", "2030-01-01"), ["temperature"]),
        {
            "bbox": (45, 40, 10, 5),
            "level": 10,
            "time_from": "2024-01-01",
            "time_to": "2024-01-03",
            "factors": ["temperature"],
        },
    )

    assert report["S2_completeness"] is None
    assert report["total_missing_values"] is None
    assert report["error_values"] is None


def test_persist_quality_report_writes_standard_json(tmp_path):
    path = quality_assess.persist_quality_report(
        {"api_name": "mock", "error_values": None},
        output_dir=tmp_path,
        request_id="request-1",
        source="provider/mock",
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert path.parent == tmp_path
    assert payload["request_id"] == "request-1"
    assert payload["api_name"] == "mock"


def test_s2_covering_is_cached_between_source_reports(monkeypatch):
    calls = []
    quality_assess._get_s2_cells_cached.cache_clear()
    monkeypatch.setattr(
        quality_assess,
        "get_s2_cells",
        lambda bbox, level: calls.append((bbox, level)) or ["cell-1"],
    )
    arguments = (
        _quality_frame(),
        {
            "api_name": "mock",
            "columns": ["Temperature [C]", "Precipitation [mm]"],
        },
        (
            (55, 49, 24, 14),
            ("2020-01-01", "2030-01-01"),
            ["temperature", "precipitation"],
        ),
        {
            "bbox": (52, 50, 20, 16),
            "level": 10,
            "time_from": "2024-01-01",
            "time_to": "2024-01-03",
            "factors": ["temperature", "precipitation"],
        },
    )

    quality_assess.assess_data_quality(*arguments)
    quality_assess.assess_data_quality(*arguments)

    assert calls == [((52, 50, 20, 16), 10)]
    quality_assess._get_s2_cells_cached.cache_clear()


def test_long_expected_period_uses_counts_for_missing_rates(monkeypatch):
    monkeypatch.setattr(
        quality_assess,
        "_get_s2_cells_cached",
        lambda _bbox, _level: ("cell-1",),
    )
    frame = pd.DataFrame(
        [[1.0], [2.0]],
        index=pd.to_datetime(["2000-01-01", "2000-01-02"]),
        columns=pd.MultiIndex.from_tuples([("Temperature [C]", "cell-1")]),
    )

    report = quality_assess.assess_data_quality(
        frame,
        {"api_name": "mock", "columns": ["Temperature [C]"]},
        (
            (55, 49, 24, 14),
            ("1900-01-01", "2100-12-31"),
            ["temperature"],
        ),
        {
            "bbox": (52, 50, 20, 16),
            "level": 10,
            "time_from": "1900-01-01",
            "time_to": "2100-12-31",
            "factors": ["temperature"],
        },
    )

    expected_days = (
        pd.Timestamp("2100-12-31") - pd.Timestamp("1900-01-01")
    ).days + 1
    assert report["total_missing_values"] == pytest.approx(
        1 - 2 / expected_days
    )
    assert report["missing_days"] == pytest.approx(
        1 - 2 / expected_days
    )

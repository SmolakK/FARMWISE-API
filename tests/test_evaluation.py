import math

import pandas as pd
import pytest

from evaluation import collect_cross_source as live_collector
from evaluation.collect_cross_source import (
    separate_frame_to_observations,
    validate_private_output,
)
from evaluation.coverage_precheck import benchmark_coverage_precheck
from evaluation.cross_source_agreement import (
    compute_agreement_metrics,
    validate_observations,
)
from evaluation.quality_smoke import generate_quality_control_report
from evaluation.scaling import measure_scaling_case


def test_coverage_benchmark_counts_avoided_requests_without_waiting():
    source_ranges = {
        "temperature.local": [
            (55, 49, 24, 14),
            ("2020-01-01", "2030-01-01"),
            ["temperature"],
        ],
        "soil.remote": [
            (45, 40, 10, 5),
            ("1990-01-01", "2000-01-01"),
            ["soil"],
        ],
    }
    scenarios = [
        {
            "scenario": "one",
            "country": "Poland",
            "bounding_box": (55, 49, 24, 14),
            "level": 10,
            "time_from": "2024-01-01",
            "time_to": "2024-01-02",
            "factors": ["temperature"],
        }
    ]

    result = benchmark_coverage_precheck(
        scenarios,
        source_ranges=source_ranges,
        execute_waits=False,
    )

    assert result[0]["candidate_sources"] == 2
    assert result[0]["dispatched_sources"] == 1
    assert result[0]["requests_avoided"] == 1
    assert result[0]["wall_seconds_saved"] > 0


def test_scaling_case_records_latency_memory_and_problem_size():
    result = measure_scaling_case(
        bounding_box=(51.05, 50.95, 17.05, 16.95),
        level=6,
        factor_count=1,
        repeats=1,
        days=2,
    )

    assert result["cell_count"] > 0
    assert result["value_count"] == result["cell_count"] * 4
    assert result["latency_seconds"] > 0
    assert result["peak_memory_mb"] > 0


def test_cross_source_metrics_align_by_timestamp_cell_and_variable():
    observations = pd.DataFrame(
        [
            ["2024-01-01", "cell", "temperature", "ERA5", 1.0],
            ["2024-01-02", "cell", "temperature", "ERA5", 2.0],
            ["2024-01-01", "cell", "temperature", "DWD", 2.0],
            ["2024-01-02", "cell", "temperature", "DWD", 4.0],
            ["2024-01-03", "cell", "temperature", "DWD", 100.0],
        ],
        columns=["timestamp", "cell", "variable", "source", "value"],
    )

    metrics, differences = compute_agreement_metrics(observations)

    assert len(differences) == 2
    assert metrics.loc[0, "n"] == 2
    assert metrics.loc[0, "bias"] == 1.5
    assert metrics.loc[0, "mae"] == 1.5
    assert metrics.loc[0, "rmse"] == pytest.approx(math.sqrt(2.5))
    assert metrics.loc[0, "pearson_r"] == pytest.approx(1)


def test_cross_source_input_requires_canonical_columns():
    with pytest.raises(ValueError, match="missing columns"):
        validate_observations(pd.DataFrame({"value": [1]}))


def test_separate_frame_conversion_extracts_source_and_logical_variable():
    columns = pd.MultiIndex.from_tuples(
        [
            ("Temperature [C] (cds_single_levels)", "cell-1"),
            ("Precipitation [mm] (wetterdienst_dwd)", "cell-1"),
        ]
    )
    frame = pd.DataFrame(
        [[5.0, 2.0]],
        index=pd.to_datetime(["2024-01-01"]),
        columns=columns,
    )

    result = separate_frame_to_observations(frame)

    assert set(result["source"]) == {"ERA5", "DWD"}
    assert set(result["variable"]) == {"temperature", "precipitation"}


def test_live_imgw_output_is_rejected_inside_repository(monkeypatch, tmp_path):
    monkeypatch.setattr(live_collector, "PROJECT_ROOT", tmp_path)
    observations = pd.DataFrame({"source": ["IMGW"], "value": [1.0]})

    with pytest.raises(PermissionError, match="outside the repository"):
        validate_private_output(tmp_path / "evaluation" / "live.csv", observations)


def test_non_imgw_live_output_may_remain_in_repository(monkeypatch, tmp_path):
    monkeypatch.setattr(live_collector, "PROJECT_ROOT", tmp_path)
    observations = pd.DataFrame({"source": ["ERA5"], "value": [1.0]})

    assert validate_private_output(tmp_path / "evaluation" / "live.csv", observations) is None


def test_quality_control_detects_implausible_value_across_multiple_cells():
    report = generate_quality_control_report()

    assert report["S2_completeness"] == 1
    assert report["implausible_value_rates"]["Temperature [C]"] > 0

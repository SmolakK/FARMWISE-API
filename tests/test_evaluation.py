import json
import math
from types import SimpleNamespace

import pandas as pd
import pytest

from evaluation import collect_cross_source as live_collector
from evaluation import collect_empirical as empirical_collector
from evaluation import run_all as empirical_runner
from evaluation.collect_cross_source import (
    separate_frame_to_observations,
    validate_private_output,
)
from evaluation.coverage_precheck import benchmark_coverage_precheck
from evaluation.cross_source_agreement import (
    compute_agreement_metrics,
    validate_observations,
)
from evaluation.empirical import (
    empirical_coverage_records,
    empirical_live_scaling_records,
    load_empirical_observations,
    load_empirical_quality_reports,
    load_empirical_runs,
)
from evaluation.quality_smoke import generate_quality_control_report
from evaluation.plots import plot_scaling
from evaluation import scaling
from evaluation.scaling import (
    benchmark_controlled_scaling,
    measure_controlled_scaling_case,
)


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


def test_coverage_benchmark_can_report_progress(capsys):
    benchmark_coverage_precheck(
        [
            {
                "scenario": "visible-progress",
                "country": "Poland",
                "bounding_box": (55, 49, 24, 14),
                "level": 10,
                "time_from": "2024-01-01",
                "time_to": "2024-01-02",
                "factors": ["temperature"],
            }
        ],
        source_ranges={},
        execute_waits=False,
        show_progress=True,
    )

    assert "Coverage pre-check" in capsys.readouterr().out


def test_controlled_scaling_case_records_latency_memory_and_problem_size():
    result = measure_controlled_scaling_case(
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
    assert result["measurement_mode"] == "controlled-generated-workload"


def test_scaling_benchmark_can_report_case_progress(monkeypatch, capsys):
    monkeypatch.setattr(
        scaling,
        "measure_controlled_scaling_case",
        lambda **_kwargs: {
            "level": 10,
            "factor_count": 1,
            "bbox_area_degrees2": 1.0,
            "cell_count": 1,
            "value_count": 1,
            "latency_seconds": 0.1,
            "peak_memory_mb": 0.1,
        },
    )

    records = benchmark_controlled_scaling(repeats=1, show_progress=True)

    assert len(records) == 17
    assert "Controlled scaling" in capsys.readouterr().out


def test_live_scaling_plot_renders_latency_and_memory_iqr(tmp_path):
    rows = []
    for dimension in ("S2 level", "Bounding-box area", "Factor count"):
        for value in (0.0, 1.0):
            rows.append(
                {
                    "dimension": dimension,
                    "normalized_scale": value,
                    "latency_seconds": 1.0 + value,
                    "latency_p25_seconds": 0.9 + value,
                    "latency_p75_seconds": 1.1 + value,
                    "peak_memory_mb": 2.0 + value,
                    "peak_memory_p25_mb": 1.8 + value,
                    "peak_memory_p75_mb": 2.2 + value,
                }
            )

    output = plot_scaling(
        pd.DataFrame(rows),
        tmp_path / "live-scaling.png",
        title="Live scaling",
    )

    assert output.is_file()
    assert output.stat().st_size > 0


@pytest.mark.asyncio
async def test_empirical_collector_separates_coverage_and_live_scaling(
    monkeypatch, tmp_path
):
    scaling_cases = [
        {
            "scenario": f"case-{number}",
            "country": "Germany",
            "dimension": dimension,
            "input_value": number,
            "bounding_box": (51.1, 50.9, 10.1, 9.9),
            "level": 10,
            "time_from": "2024-01-01",
            "time_to": "2024-01-02",
            "factors": ["temperature"],
        }
        for number, dimension in enumerate(
            ("S2 level", "Bounding-box area", "Factor count"), start=1
        )
    ]
    separate_api_values = []

    async def fake_read_data(**kwargs):
        separate_api_values.append(kwargs["separate_api"])
        factor = (
            "Temperature [C] (fake_source)"
            if kwargs["separate_api"]
            else "Temperature [C]"
        )
        frame = pd.DataFrame(
            [[1.0]],
            index=pd.to_datetime(["2024-01-01"]),
            columns=pd.MultiIndex.from_tuples([(factor, "cell")]),
        )
        return {
            "data": frame,
            "metadata": {
                "coverage_precheck": {
                    "candidate_sources": 1,
                    "dispatched_sources": 1,
                    "requests_avoided": 0,
                    "precheck_seconds": 0.01,
                    "sources": [
                        {"source": "fake.source", "dispatched": True}
                    ],
                },
                "dispatch": [
                    {
                        "source": "fake.source",
                        "status": "success",
                        "wall_seconds": 0.02,
                    }
                ],
                "quality_reports": [],
            },
        }

    monkeypatch.setattr(empirical_collector, "read_data", fake_read_data)
    monkeypatch.setattr(
        empirical_collector,
        "plan_source_dispatch",
        lambda *_args, **_kwargs: [
            {"source": "fake.source", "dispatched": True}
        ],
    )
    monkeypatch.setattr(
        empirical_collector, "LIVE_SCALING_SCENARIOS", scaling_cases
    )
    monkeypatch.setattr(empirical_collector, "PROJECT_ROOT", tmp_path / "repo")
    output_dir = tmp_path / "cache"

    result = await empirical_collector.collect(
        SimpleNamespace(
            scenario=["poland-temperature"],
            output_dir=output_dir,
            skip_live_scaling=False,
            live_scaling_repeats=1,
            timeout=1,
            fail_fast=True,
            no_progress=True,
        )
    )

    payload = json.loads(result["runs"].read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert [run["run_kind"] for run in payload["runs"]].count("coverage") == 1
    assert [run["run_kind"] for run in payload["runs"]].count("live-scaling") == 3
    assert separate_api_values.count(True) == 1
    assert separate_api_values.count(False) == 3
    assert all(
        isinstance(run["peak_traced_memory_mb"], float)
        for run in payload["runs"]
    )


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


def test_empirical_coverage_uses_only_observed_source_latencies():
    payload = {
        "runs": [
            {
                "request": {
                    "scenario": "first",
                    "country": "Poland",
                    "level": 10,
                    "factors": ["temperature"],
                    "time_from": "2024-01-01",
                    "time_to": "2024-01-02",
                },
                "request_wall_seconds": 0.7,
                "status": "success",
                "coverage_precheck": {
                    "candidate_sources": 2,
                    "dispatched_sources": 1,
                    "precheck_seconds": 0.01,
                    "sources": [
                        {"source": "source.a", "dispatched": True},
                        {"source": "source.b", "dispatched": False},
                    ],
                },
                "dispatch": [
                    {"source": "source.a", "wall_seconds": 0.4}
                ],
            },
            {
                "request": {
                    "scenario": "second",
                    "country": "Germany",
                    "level": 10,
                    "factors": ["temperature"],
                    "time_from": "2024-01-01",
                    "time_to": "2024-01-02",
                },
                "request_wall_seconds": 0.5,
                "status": "success",
                "coverage_precheck": {
                    "candidate_sources": 2,
                    "dispatched_sources": 1,
                    "precheck_seconds": 0.01,
                    "sources": [
                        {"source": "source.a", "dispatched": False},
                        {"source": "source.b", "dispatched": True},
                    ],
                },
                "dispatch": [
                    {"source": "source.b", "wall_seconds": 0.2}
                ],
            },
        ]
    }

    records = empirical_coverage_records(payload)

    assert records[0]["wall_seconds_saved"] == pytest.approx(0.2)
    assert records[0]["avoided_latency_coverage_rate"] == 1.0
    assert records[0]["latency_mode"] == "empirical-observed-lower-bound"


def test_empirical_inputs_reject_synthetic_fallbacks(tmp_path):
    runs_path = tmp_path / "runs.json"
    runs_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "mode": "offline-smoke-test",
                "runs": [{"scenario": "fake"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="empirical-live"):
        load_empirical_runs(runs_path)

    observations_path = tmp_path / "observations.csv"
    pd.DataFrame(
        [
            ["2024-01-01", "cell", "temperature", "ERA5", 1.0],
            [
                "2024-01-01",
                "cell",
                "temperature",
                "synthetic.station",
                1.1,
            ],
        ],
        columns=["timestamp", "cell", "variable", "source", "value"],
    ).to_csv(observations_path, index=False)
    with pytest.raises(ValueError, match="Synthetic sources"):
        load_empirical_observations(observations_path)

    quality_dir = tmp_path / "quality"
    quality_dir.mkdir()
    (quality_dir / "report.json").write_text(
        json.dumps(
            {
                "source": "evaluation.synthetic_quality_source",
                "evaluation_mode": "synthetic-control",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not empirical"):
        load_empirical_quality_reports(quality_dir)


def test_empirical_runner_consumes_live_artifacts_without_fallback(
    monkeypatch, tmp_path
):
    runs_path = tmp_path / "runs.json"
    runs_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "mode": "empirical-live",
                "collected_at": "2026-08-10T10:00:00+00:00",
                "runs": [
                    {
                        "request": {
                            "scenario": "live",
                            "country": "Germany",
                            "level": 10,
                            "factors": ["temperature"],
                            "time_from": "2024-01-01",
                            "time_to": "2024-01-02",
                        },
                        "status": "success",
                        "request_wall_seconds": 0.5,
                        "coverage_precheck": {
                            "candidate_sources": 1,
                            "dispatched_sources": 1,
                            "precheck_seconds": 0.01,
                            "sources": [
                                {"source": "source.live", "dispatched": True}
                            ],
                        },
                        "dispatch": [
                            {"source": "source.live", "wall_seconds": 0.4}
                        ],
                    },
                    {
                        "request": {
                            "scenario": "live-level-10",
                            "country": "Germany",
                            "dimension": "S2 level",
                            "input_value": 10,
                            "bounding_box": [51.5, 50.5, 10.5, 9.5],
                            "level": 10,
                            "factors": ["temperature"],
                            "time_from": "2024-01-01",
                            "time_to": "2024-01-02",
                        },
                        "run_kind": "live-scaling",
                        "repeat": 1,
                        "status": "success",
                        "request_wall_seconds": 0.6,
                        "peak_traced_memory_mb": 2.0,
                        "returned_cell_count": 4,
                        "non_null_value_count": 8,
                        "coverage_precheck": {
                            "candidate_sources": 1,
                            "dispatched_sources": 1,
                            "precheck_seconds": 0.01,
                            "sources": [
                                {"source": "source.live", "dispatched": True}
                            ],
                        },
                        "dispatch": [
                            {
                                "source": "source.live",
                                "status": "success",
                                "wall_seconds": 0.5,
                            }
                        ],
                    },
                    {
                        "request": {
                            "scenario": "live-area-1",
                            "country": "Germany",
                            "dimension": "Bounding-box area",
                            "input_value": 1.0,
                            "bounding_box": [51.5, 50.5, 10.5, 9.5],
                            "level": 10,
                            "factors": ["temperature"],
                            "time_from": "2024-01-01",
                            "time_to": "2024-01-02",
                        },
                        "run_kind": "live-scaling",
                        "status": "success",
                        "request_wall_seconds": 0.7,
                        "peak_traced_memory_mb": 2.1,
                        "returned_cell_count": 4,
                        "non_null_value_count": 8,
                        "dispatch": [
                            {"status": "success", "wall_seconds": 0.6}
                        ],
                    },
                    {
                        "request": {
                            "scenario": "live-factors-1",
                            "country": "Germany",
                            "dimension": "Factor count",
                            "input_value": 1,
                            "bounding_box": [51.5, 50.5, 10.5, 9.5],
                            "level": 10,
                            "factors": ["temperature"],
                            "time_from": "2024-01-01",
                            "time_to": "2024-01-02",
                        },
                        "run_kind": "live-scaling",
                        "status": "success",
                        "request_wall_seconds": 0.8,
                        "peak_traced_memory_mb": 2.2,
                        "returned_cell_count": 4,
                        "non_null_value_count": 8,
                        "dispatch": [
                            {"status": "success", "wall_seconds": 0.7}
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    observations_path = tmp_path / "observations.csv"
    pd.DataFrame(
        [
            ["2024-01-01", "cell", "temperature", "ERA5", 1.0],
            ["2024-01-01", "cell", "temperature", "DWD", 1.2],
            ["2024-01-02", "cell", "temperature", "ERA5", 2.0],
            ["2024-01-02", "cell", "temperature", "DWD", 2.1],
        ],
        columns=["timestamp", "cell", "variable", "source", "value"],
    ).to_csv(observations_path, index=False)
    quality_dir = tmp_path / "quality"
    quality_dir.mkdir()
    (quality_dir / "live.json").write_text(
        json.dumps(
            {
                "source": "source.live",
                "request_id": "request-live",
                "created_at": "2026-08-10T10:00:00+00:00",
                "S2_completeness": 1.0,
                "total_missing_values": 0.0,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        empirical_runner,
        "benchmark_controlled_scaling",
        lambda **_kwargs: [
            {
                "dimension": "S2 level",
                "input_value": 10,
                "latency_seconds": 0.1,
                "peak_memory_mb": 1.0,
                "normalized_scale": 0.0,
            }
        ],
    )

    def fake_figures(*, figure_dir, **_kwargs):
        paths = [figure_dir / f"figure-{number}.png" for number in range(4)]
        for path in paths:
            path.write_bytes(b"figure")
        return paths

    monkeypatch.setattr(empirical_runner, "generate_all_figures", fake_figures)

    manifest = empirical_runner.run_all(
        runs_path=runs_path,
        observations_path=observations_path,
        quality_reports_dir=quality_dir,
        output_dir=tmp_path / "results",
        controlled_scaling_repeats=1,
    )

    assert manifest["mode"] == "empirical-live-with-controlled-supplement"
    assert manifest["live_scaling_cases"] == 3
    assert manifest["agreement_observations"] == 2
    assert manifest["quality_reports"] == 1

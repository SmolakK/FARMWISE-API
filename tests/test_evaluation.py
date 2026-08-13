import json

import pandas as pd
import pytest

from evaluation import collect_cross_source as live_collector
from evaluation import collect_empirical as empirical_collector
from evaluation import run_all as empirical_runner
from evaluation.collect_cross_source import (
    separate_frame_to_observations,
    validate_private_output,
)


@pytest.mark.asyncio
async def test_empirical_collector_collects_all_scenario_groups(
    monkeypatch, tmp_path
):
    base_case = {
        "scenario": "coverage-case",
        "country": "Germany",
        "bounding_box": (51.1, 50.9, 10.1, 9.9),
        "level": 10,
        "time_from": "2024-01-01",
        "time_to": "2024-01-02",
        "factors": ["temperature"],
    }
    cross_case = {**base_case, "scenario": "cross-case"}
    scaling_cases = [
        {
            **base_case,
            "scenario": f"scaling-{number}",
            "dimension": dimension,
            "input_value": number,
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

    result = await empirical_collector.collect(
        scenarios=[base_case],
        scaling_scenarios=scaling_cases,
        cross_scenarios=[cross_case],
        scaling_repeats=1,
        output_dir=tmp_path / "empirical-input",
        timeout=1,
    )

    payload = json.loads(result["runs"].read_text(encoding="utf-8"))
    run_kinds = [run["run_kind"] for run in payload["runs"]]
    assert run_kinds.count("coverage") == 1
    assert run_kinds.count("cross-source") == 1
    assert run_kinds.count("live-scaling") == 3
    assert separate_api_values.count(True) == 2
    assert separate_api_values.count(False) == 3
    assert all(
        isinstance(run["peak_traced_memory_mb"], float)
        for run in payload["runs"]
    )

    observations = pd.read_csv(result["observations"])
    assert set(observations["scenario"]) == {"cross-case"}


def test_separate_frame_conversion_extracts_source_and_logical_variable():
    frame = pd.DataFrame(
        [[5.0, 2.0]],
        index=pd.to_datetime(["2024-01-01"]),
        columns=pd.MultiIndex.from_tuples(
            [
                ("Temperature [C] (cds_single_levels)", "cell-1"),
                ("Precipitation [mm] (wetterdienst_dwd)", "cell-1"),
            ]
        ),
    )

    result = separate_frame_to_observations(frame)

    assert set(result["source"]) == {"ERA5", "DWD"}
    assert set(result["variable"]) == {"temperature", "precipitation"}


def test_live_imgw_output_is_rejected_inside_repository(monkeypatch, tmp_path):
    monkeypatch.setattr(live_collector, "PROJECT_ROOT", tmp_path)
    observations = pd.DataFrame({"source": ["IMGW"], "value": [1.0]})

    with pytest.raises(PermissionError, match="outside the repository"):
        validate_private_output(
            tmp_path / "evaluation" / "live.csv", observations
        )


def test_non_imgw_live_output_may_remain_in_repository(monkeypatch, tmp_path):
    monkeypatch.setattr(live_collector, "PROJECT_ROOT", tmp_path)
    observations = pd.DataFrame({"source": ["ERA5"], "value": [1.0]})

    assert (
        validate_private_output(
            tmp_path / "evaluation" / "live.csv", observations
        )
        is None
    )


def test_run_all_only_runs_empirical_collection(monkeypatch):
    expected = {"request_count": 48, "observation_count": 120}

    async def fake_collect():
        return expected

    monkeypatch.setattr(empirical_runner, "collect", fake_collect)

    assert empirical_runner.run_all() == expected

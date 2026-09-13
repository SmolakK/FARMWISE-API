import json
import os

import pandas as pd
import pytest

from evaluation import collect_cross_source as live_collector
from evaluation import collect_empirical as empirical_collector
from evaluation import run_all as empirical_runner
from evaluation.collect_cross_source import (
    separate_frame_to_observations,
    summarise_source_comparison,
    validate_private_output,
)
from evaluation.scenarios import CROSS_SOURCE_SCENARIOS
from farmwise_api.core import main_call
from farmwise_api.core.utils.access_policy import IMGW_RESEARCH_USE_ENV

BASE_CASE = {
    "scenario": "coverage-case",
    "country": "Germany",
    "bounding_box": (51.1, 50.9, 10.1, 9.9),
    "level": 10,
    "time_from": "2024-01-01",
    "time_to": "2024-01-02",
    "factors": ["temperature"],
}


def _fake_result(separate_api, planned):
    factor = "Temperature [C] (fake_source)" if separate_api else "Temperature [C]"
    frame = pd.DataFrame(
        [[1.0, 2.0], [3.0, None]],
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
        columns=pd.MultiIndex.from_tuples([(factor, "cell-1"), (factor, "cell-2")]),
    )
    return {
        "data": frame,
        "metadata": {
            "coverage_precheck": {
                "candidate_sources": len(planned),
                "dispatched_sources": sum(d["dispatched"] for d in planned),
                "precheck_seconds": 0.001,
                "sources": planned,
            },
            "dispatch": [
                {"source": d["source"], "status": "success", "wall_seconds": 0.02}
                for d in planned if d["dispatched"]
            ],
            "quality_assessment": {"enabled": False},
            "quality_reports": [],
        },
    }


def _decision(source, *, spatial=True, temporal=True, factors=("temperature",), disabled=None):
    return {
        "source": source,
        "spatial_overlap": spatial,
        "temporal_overlap": temporal,
        "factor_overlap": list(factors),
        "disabled_reason": disabled,
        "dispatched": bool(not disabled and spatial and temporal and factors),
    }


FAKE_PLAN = [
    _decision("fake.inside"),
    _decision("fake.elsewhere", spatial=False),
    _decision("fake.other_factor", factors=()),
    _decision("fake.disabled", disabled="licence"),
]


@pytest.mark.asyncio
async def test_collector_runs_every_experiment_and_excludes_warmups(monkeypatch, tmp_path):
    calls = []

    async def fake_read_data(**kwargs):
        planned = main_call.plan_source_dispatch(
            kwargs["bounding_box"], kwargs["time_from"], kwargs["time_to"], kwargs["factors"],
        )
        calls.append({**kwargs, "dispatched": [d["source"] for d in planned if d["dispatched"]]})
        return _fake_result(kwargs["separate_api"], planned)

    def fake_plan(*_args, **_kwargs):
        return [dict(d) for d in FAKE_PLAN]

    monkeypatch.setattr(main_call, "plan_source_dispatch", fake_plan)
    monkeypatch.setattr(empirical_collector, "plan_source_dispatch", lambda *a, **k: [dict(d) for d in FAKE_PLAN])
    monkeypatch.setattr(empirical_collector, "read_data", fake_read_data)

    scaling = [
        {**BASE_CASE, "scenario": f"scaling-{n}", "dimension": "S2 level", "input_value": n, "level": n}
        for n in (8, 10)
    ]
    result = await empirical_collector.collect(
        coverage_scenarios=[BASE_CASE],
        cross_scenarios=[{**BASE_CASE, "scenario": "cross-case", "region": "r", "period": "January"}],
        quality_scenario={**BASE_CASE, "scenario": "quality-case"},
        scaling_scenarios=scaling,
        coverage_repeats=2, coverage_warmups=1,
        quality_repeats=2, quality_warmups=1,
        scaling_repeats=3, scaling_warmups=1,
        output_root=tmp_path, collection_id="test-collection", timeout=1,
        rss_interval=0.001,
    )

    payload = json.loads(result["runs"].read_text(encoding="utf-8"))
    runs = payload["runs"]
    by_experiment = pd.Series([r["experiment"] for r in runs]).value_counts().to_dict()
    assert by_experiment == {"coverage": 4, "cross-source": 1, "quality-overhead": 4, "scaling": 6}
    # Warm-ups: one per coverage mode, one per quality mode, one per scaling scenario.
    assert len(payload["warmup_runs"]) == 2 + 2 + 2
    assert all(r["repeat"] >= 1 for r in runs)
    assert len(calls) == len(runs) + len(payload["warmup_runs"])

    scaling_runs = [r for r in runs if r["experiment"] == "scaling"]
    assert all(r["settings"]["assess_quality"] is False for r in scaling_runs)
    assert all(r["settings"]["persist_quality_reports"] is False for r in scaling_runs)
    assert all(r["settings"]["separate_api"] is False for r in scaling_runs)
    assert sorted({r["repeat"] for r in scaling_runs}) == [1, 2, 3]

    quality_modes = {r["mode"]: r["settings"]["assess_quality"]
                     for r in runs if r["experiment"] == "quality-overhead"}
    assert quality_modes == {"off": False, "on": True}

    coverage = [r for r in runs if r["experiment"] == "coverage"]
    assert {r["mode"] for r in coverage} == {"precheck", "factor-only"}
    assert all(r["settings"]["assess_quality"] is False for r in coverage)
    # The baseline dispatches the out-of-coverage source; disabled and
    # non-matching sources stay excluded in both modes.
    assert {tuple(c["dispatched"]) for c in calls if c["separate_api"]} == {
        ("fake.inside",), ("fake.inside", "fake.elsewhere"),
    }
    # The factor-only swap is undone after every baseline run.
    assert main_call.plan_source_dispatch is fake_plan

    record = scaling_runs[0]
    workload = record["workload"]
    assert workload["requested_s2_cells"] > 0
    assert workload["returned_s2_cells"] == 2
    assert workload["returned_values"] == 3
    assert workload["duration_days"] == 2
    assert workload["requested_factors"] == 1
    assert workload["area_km2"] > 0
    assert record["planned_coverage"]["requests_avoided_vs_factor_only"] == 1
    assert record["source_wall_seconds"] == {"fake.inside": 0.02}
    assert isinstance(record["memory"]["peak_traced_memory_mb"], float)

    manifest = json.loads(result["manifest"].read_text(encoding="utf-8"))
    assert manifest["evaluation_config"]["scaling"]["repeats"] == 3
    assert manifest["evaluation_config"]["random_seed"] == 42
    assert "commit_sha" in manifest["git"]
    assert len(manifest["execution_order"]) == len(calls)

    observations = pd.read_csv(result["observations"])
    assert set(observations["scenario"]) == {"cross-case"}
    assert set(observations["period"]) == {"January"}


@pytest.mark.asyncio
async def test_collector_never_overwrites_a_frozen_collection(tmp_path):
    (tmp_path / "frozen").mkdir()
    (tmp_path / "frozen" / "empirical_runs.json").write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError, match="never overwritten"):
        await empirical_collector.collect(output_root=tmp_path, collection_id="frozen")


def test_separate_frame_conversion_extracts_source_and_logical_variable():
    frame = pd.DataFrame(
        [[5.0, 2.0, 1.5]],
        index=pd.to_datetime(["2024-01-01"]),
        columns=pd.MultiIndex.from_tuples(
            [
                ("Temperature [C] (cds_single_levels)", "cell-1"),
                ("Precipitation [mm] (wetterdienst_dwd)", "cell-1"),
                ("precipitation [mm] (irish_ms_daily)", "cell-1"),
            ]
        ),
    )

    result = separate_frame_to_observations(frame)

    assert set(result["source"]) == {"ERA5", "DWD", "Met Éireann"}
    assert set(result["variable"]) == {"temperature", "precipitation"}


def test_poland_cross_source_scenarios_require_imgw_and_era5():
    poland = [s for s in CROSS_SOURCE_SCENARIOS if s["region"] == "poland-imgw-era5"]

    assert [s["period"] for s in poland] == ["January", "April", "July", "October"]
    for scenario in poland:
        assert scenario["country"] == "Poland"
        assert scenario["required_sources"] == ["IMGW", "ERA5"]
        assert scenario["factors"] == ["temperature", "precipitation"]


def test_cross_source_summary_requires_both_sources_and_shared_keys():
    observations = pd.DataFrame(
        [
            {"timestamp": "2018-01-01", "cell": "cell-1", "variable": "temperature",
             "source": "IMGW", "value": 1.0},
            {"timestamp": "2018-01-01", "cell": "cell-1", "variable": "temperature",
             "source": "ERA5", "value": 2.0},
        ]
    )

    summary = summarise_source_comparison(observations, required_sources=["IMGW", "ERA5"])

    assert summary["comparison_ready"] is True
    assert summary["missing_sources"] == []
    assert summary["overlapping_observation_keys"] == 1

    missing_imgw = summarise_source_comparison(
        observations[observations["source"] == "ERA5"],
        required_sources=["IMGW", "ERA5"],
    )
    assert missing_imgw["comparison_ready"] is False
    assert missing_imgw["missing_sources"] == ["IMGW"]


def test_live_imgw_output_is_rejected_inside_package(monkeypatch, tmp_path):
    monkeypatch.setattr(live_collector, "PACKAGE_ROOT", tmp_path / "farmwise_api")
    observations = pd.DataFrame({"source": ["IMGW"], "value": [1.0]})

    with pytest.raises(PermissionError, match="distributable"):
        validate_private_output(tmp_path / "farmwise_api" / "data" / "live.csv", observations)


def test_live_imgw_evaluation_output_may_remain_outside_package(monkeypatch, tmp_path):
    monkeypatch.setattr(live_collector, "PACKAGE_ROOT", tmp_path / "farmwise_api")
    observations = pd.DataFrame({"source": ["IMGW"], "value": [1.0]})

    assert validate_private_output(tmp_path / "evaluation" / "live.csv", observations) is None


def test_non_imgw_live_output_may_remain_in_repository(monkeypatch, tmp_path):
    monkeypatch.setattr(live_collector, "PACKAGE_ROOT", tmp_path / "farmwise_api")
    observations = pd.DataFrame({"source": ["ERA5"], "value": [1.0]})

    assert validate_private_output(tmp_path / "evaluation" / "live.csv", observations) is None


def test_run_all_only_runs_empirical_collection(monkeypatch):
    expected = {"request_count": 48, "observation_count": 120}

    async def fake_collect():
        return expected

    monkeypatch.setattr(empirical_runner, "collect", fake_collect)

    assert empirical_runner.run_all() == expected


def _record_acknowledgement_during_collection(monkeypatch, tmp_path, observed):
    """Patch ``main`` dependencies and capture the gate state while collecting."""
    expected = {
        "request_count": 1, "warmup_count": 0, "observation_count": 2,
        "collection_dir": tmp_path,
    }

    def fake_run(coroutine):
        coroutine.close()
        observed["during"] = os.environ.get(IMGW_RESEARCH_USE_ENV)
        return expected

    monkeypatch.setattr(empirical_collector.asyncio, "run", fake_run)
    monkeypatch.setattr(empirical_collector, "OUTPUT_ROOT", tmp_path)


def test_collect_empirical_main_enables_file_level_imgw_opt_in(monkeypatch, tmp_path):
    observed = {}
    monkeypatch.delenv(IMGW_RESEARCH_USE_ENV, raising=False)
    monkeypatch.setattr(empirical_collector, "INCLUDE_IMGW_RESEARCH", True)
    _record_acknowledgement_during_collection(monkeypatch, tmp_path, observed)

    empirical_collector.main()

    assert observed["during"] == "1"
    assert IMGW_RESEARCH_USE_ENV not in os.environ


def test_collect_empirical_main_restores_a_pre_existing_acknowledgement(monkeypatch, tmp_path):
    observed = {}
    monkeypatch.setenv(IMGW_RESEARCH_USE_ENV, "yes")
    monkeypatch.setattr(empirical_collector, "INCLUDE_IMGW_RESEARCH", True)
    _record_acknowledgement_during_collection(monkeypatch, tmp_path, observed)

    empirical_collector.main()

    assert observed["during"] == "1"
    assert os.environ[IMGW_RESEARCH_USE_ENV] == "yes"


def test_collect_empirical_main_leaves_imgw_disabled_without_opt_in(monkeypatch, tmp_path):
    observed = {}
    monkeypatch.delenv(IMGW_RESEARCH_USE_ENV, raising=False)
    monkeypatch.setattr(empirical_collector, "INCLUDE_IMGW_RESEARCH", False)
    _record_acknowledgement_during_collection(monkeypatch, tmp_path, observed)

    empirical_collector.main()

    assert observed["during"] is None
    assert IMGW_RESEARCH_USE_ENV not in os.environ

"""Experimental-design guarantees and helper behaviour of the evaluation layer."""

from datetime import date
import math

import numpy as np
import pandas as pd
import pytest

from evaluation import analysis, measurement, scenarios
from evaluation.collect_empirical import build_work_plan
from evaluation.coverage_baseline import coverage_counts, factor_only_routing
from evaluation.workload import (
    bbox_area_km2,
    duration_days,
    request_workload,
    requested_s2_cell_count,
    result_workload,
    source_timings,
)
from farmwise_api.core import main_call


# ---------------------------------------------------------------------------
# Scenario design
# ---------------------------------------------------------------------------

def test_scaling_has_no_factor_count_sweep_and_uses_one_fixed_factor_set():
    dimensions = {s["dimension"] for s in scenarios.LIVE_SCALING_SCENARIOS}
    assert dimensions == {"S2 level", "Spatial extent", "Temporal extent"}
    assert all(
        s["factors"] == ["temperature", "precipitation"]
        for s in scenarios.LIVE_SCALING_SCENARIOS
    )


@pytest.mark.parametrize(
    "dimension, varying",
    [
        ("S2 level", "level"),
        ("Spatial extent", "bounding_box"),
        ("Temporal extent", "time_to"),
    ],
)
def test_each_scaling_sweep_changes_exactly_one_request_parameter(dimension, varying):
    sweep = [s for s in scenarios.LIVE_SCALING_SCENARIOS if s["dimension"] == dimension]
    assert len(sweep) == 4
    fixed = {"level", "bounding_box", "time_from", "time_to", "factors", "country"} - {varying}
    for key in fixed:
        assert len({repr(s[key]) for s in sweep}) == 1, key
    assert len({repr(s[varying]) for s in sweep}) == 4


def test_every_sweep_includes_the_shared_base_request():
    base = {
        "level": scenarios.SCALING_BASE_LEVEL,
        "bounding_box": scenarios.centred_bounding_box(scenarios.SCALING_BASE_WIDTH_DEG),
        "time_to": scenarios.inclusive_end_date(
            scenarios.SCALING_TIME_FROM, scenarios.SCALING_BASE_DURATION_DAYS
        ),
    }
    for dimension in scenarios.SCALING_DIMENSIONS:
        sweep = [s for s in scenarios.LIVE_SCALING_SCENARIOS if s["dimension"] == dimension]
        assert any(all(s[k] == v for k, v in base.items()) for s in sweep), dimension


def test_temporal_sweep_spans_the_stated_inclusive_days():
    sweep = [s for s in scenarios.LIVE_SCALING_SCENARIOS if s["dimension"] == "Temporal extent"]
    assert [duration_days(s["time_from"], s["time_to"]) for s in sweep] == [1, 7, 30, 90]
    assert [s["input_value"] for s in sweep] == [1, 7, 30, 90]


def test_cross_source_covers_four_seasons_for_every_region():
    by_region = {}
    for s in scenarios.CROSS_SOURCE_SCENARIOS:
        by_region.setdefault(s["region"], []).append(s["period"])
        start, end = date.fromisoformat(s["time_from"]), date.fromisoformat(s["time_to"])
        assert start.day == 1 and (end.month, end.year) == (start.month, start.year)
        assert len(s["required_sources"]) == 2 and "ERA5" in s["required_sources"]
    assert set(by_region) == {
        "germany-meteo", "austria-meteo", "ireland-precipitation", "poland-imgw-era5",
    }
    assert all(p == ["January", "April", "July", "October"] for p in by_region.values())


def test_repetition_and_warmup_settings():
    assert scenarios.SCALING_REPEATS == 10
    assert scenarios.SCALING_WARMUPS == 1
    assert scenarios.RANDOM_SEED == 42


def test_work_plan_is_reproducible_and_places_warmups_first():
    first = build_work_plan()
    second = build_work_plan()
    assert [(i.experiment, i.request["scenario"], i.mode, i.repeat) for i in first] == [
        (i.experiment, i.request["scenario"], i.mode, i.repeat) for i in second
    ]
    scaling = [i for i in first if i.experiment == "scaling"]
    warmups = [i for i in scaling if i.warmup]
    assert len(warmups) == len(scenarios.LIVE_SCALING_SCENARIOS)
    assert scaling[: len(warmups)] == warmups
    assert len(scaling) - len(warmups) == 10 * len(scenarios.LIVE_SCALING_SCENARIOS)
    # Measured runs are interleaved, not grouped by scenario.
    measured = [i.request["scenario"] for i in scaling if not i.warmup]
    assert measured[:10] != [measured[0]] * 10
    assert all(not i.assess_quality and not i.persist_quality_reports for i in scaling)


def test_work_plan_rejects_zero_repeats():
    with pytest.raises(ValueError, match="scaling_repeats"):
        build_work_plan(scaling_repeats=0)


def test_evaluation_config_is_json_serialisable():
    import json

    json.dumps(scenarios.evaluation_config())


# ---------------------------------------------------------------------------
# Workload
# ---------------------------------------------------------------------------

def test_bbox_area_matches_spherical_formula_and_shrinks_poleward():
    one_degree_at_equator = bbox_area_km2((0.5, -0.5, 0.5, -0.5))
    assert one_degree_at_equator == pytest.approx((math.pi / 180 * 6371.0088) ** 2, rel=1e-4)
    assert bbox_area_km2((51.5, 50.5, 10.5, 9.5)) < one_degree_at_equator


def test_requested_cells_grow_with_level_and_extent():
    box = (51.5, 50.5, 10.5, 9.5)
    counts = [requested_s2_cell_count(box, level) for level in (6, 8, 10)]
    assert counts == sorted(counts) and counts[0] >= 1
    small = requested_s2_cell_count(scenarios.centred_bounding_box(0.25), 10)
    large = requested_s2_cell_count(scenarios.centred_bounding_box(2.0), 10)
    assert large > small


def test_request_and_result_workload():
    workload = request_workload(scenarios.LIVE_SCALING_SCENARIOS[0])
    assert set(workload) >= {
        "area_km2", "requested_s2_cells", "duration_days", "requested_factors",
        "width_deg", "height_deg",
    }
    frame = pd.DataFrame(
        [[1.0, np.nan], [2.0, 3.0]],
        columns=pd.MultiIndex.from_tuples([("T", "a"), ("T", "b")]),
    )
    assert result_workload(frame) == {
        "returned_rows": 2, "returned_columns": 2, "returned_s2_cells": 2,
        "returned_factors": 1, "returned_values": 3,
    }
    assert result_workload(None)["returned_values"] == 0


def test_source_timings_counts_outcomes():
    timings = source_timings([
        {"source": "a", "status": "success", "wall_seconds": 1.0},
        {"source": "b", "status": "empty", "wall_seconds": 3.0},
    ])
    assert timings["dispatch_status_counts"] == {"success": 1, "empty": 1}
    assert timings["dispatch_seconds_max"] == 3.0


# ---------------------------------------------------------------------------
# Measurement and provenance
# ---------------------------------------------------------------------------

def test_memory_monitor_records_peak_rss_from_the_probe():
    readings = iter([100 * measurement.MB, 150 * measurement.MB, 120 * measurement.MB])
    last = {"value": 100 * measurement.MB}

    def probe():
        last["value"] = next(readings, last["value"])
        return last["value"]

    with measurement.MemoryMonitor(interval_seconds=0.001, rss_probe=probe) as monitor:
        blob = [0] * 100_000
        del blob
    result = monitor.result
    assert result["peak_rss_mb"] == pytest.approx(150)
    assert result["rss_before_mb"] == pytest.approx(100)
    assert result["peak_rss_increase_mb"] == pytest.approx(50)
    assert result["peak_traced_memory_mb"] > 0
    assert result["rss_backend"] == "psutil"


def test_memory_monitor_without_rss_backend_keeps_tracemalloc():
    with measurement.MemoryMonitor(rss_probe=lambda: None) as monitor:
        pass
    assert monitor.result["peak_rss_mb"] is None
    assert monitor.result["rss_backend"] is None
    assert monitor.result["peak_traced_memory_mb"] >= 0


def test_provenance_records_environment_without_private_details():
    record = measurement.provenance({"random_seed": 7})
    assert record["evaluation_config"] == {"random_seed": 7}
    assert record["software"]["python_version"]
    assert record["software"]["lockfile"] == "requirements-lock.txt"
    assert "installed_distributions" in record["software"]
    assert {"os", "cpu_logical_cores", "total_ram_gb"} <= set(record["hardware"])
    text = repr(record).lower()
    assert "node" not in record["hardware"] and "hostname" not in text


def test_git_metadata_tolerates_missing_git(monkeypatch):
    monkeypatch.setattr(measurement, "_git", lambda *args: None)
    assert measurement.git_metadata() == {
        "commit_sha": None, "branch": None,
        "tracked_changes_uncommitted": None, "uncommitted_tracked_paths": None,
    }


def test_git_metadata_keeps_the_first_character_of_changed_paths(monkeypatch):
    outputs = {"status": " M evaluation/a.py\nM  evaluation/b.py\n", "rev-parse": "abc\n"}
    monkeypatch.setattr(measurement, "_git", lambda *args: outputs[args[0]])
    assert measurement.git_metadata()["uncommitted_tracked_paths"] == [
        "evaluation/a.py", "evaluation/b.py",
    ]


# ---------------------------------------------------------------------------
# Coverage baseline
# ---------------------------------------------------------------------------

PLAN = [
    {"source": "inside", "spatial_overlap": True, "temporal_overlap": True,
     "factor_overlap": ["temperature"], "disabled_reason": None, "dispatched": True},
    {"source": "elsewhere", "spatial_overlap": False, "temporal_overlap": True,
     "factor_overlap": ["temperature"], "disabled_reason": None, "dispatched": False},
    {"source": "too-old", "spatial_overlap": True, "temporal_overlap": False,
     "factor_overlap": ["temperature"], "disabled_reason": None, "dispatched": False},
    {"source": "wrong-factor", "spatial_overlap": True, "temporal_overlap": True,
     "factor_overlap": [], "disabled_reason": None, "dispatched": False},
    {"source": "licensed-out", "spatial_overlap": True, "temporal_overlap": True,
     "factor_overlap": ["temperature"], "disabled_reason": "licence", "dispatched": False},
]


def test_coverage_counts_measure_avoidance_against_factor_only_routing():
    counts = coverage_counts(PLAN)
    assert counts == {
        "configured_sources": 5, "enabled_sources": 4, "factor_eligible_sources": 3,
        "precheck_dispatched_sources": 1, "requests_avoided_vs_factor_only": 2,
        "rejected_spatial": 1, "rejected_temporal": 1,
    }


def test_factor_only_routing_ignores_coverage_but_keeps_disabled_sources_out(monkeypatch):
    monkeypatch.setattr(main_call, "plan_source_dispatch", lambda *a, **k: [dict(d) for d in PLAN])
    original = main_call.plan_source_dispatch

    with factor_only_routing():
        dispatched = [d["source"] for d in main_call.plan_source_dispatch() if d["dispatched"]]
    assert dispatched == ["inside", "elsewhere", "too-old"]
    assert main_call.plan_source_dispatch is original


def test_factor_only_routing_restores_the_planner_after_an_error(monkeypatch):
    original = main_call.plan_source_dispatch
    with pytest.raises(RuntimeError):
        with factor_only_routing():
            raise RuntimeError("boom")
    assert main_call.plan_source_dispatch is original


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def test_robust_stats_report_median_iqr_and_a_bracketing_ci():
    values = [1, 2, 3, 4, 100]
    stats = analysis.robust_stats(values)
    assert stats["median"] == 3
    assert stats["q1"] == 2 and stats["q3"] == 4 and stats["iqr"] == 2
    assert stats["median_ci_low"] <= stats["median"] <= stats["median_ci_high"]
    assert stats["mean"] == pytest.approx(22)
    assert analysis.robust_stats(values) == stats  # fixed bootstrap seed


def test_scaling_summary_and_fit_use_successful_runs_only():
    runs = pd.DataFrame({
        "experiment": ["scaling"] * 6,
        "dimension": ["S2 level"] * 6,
        "input_value": [8, 8, 10, 10, 12, 12],
        "status": ["success", "error", "success", "success", "success", "success"],
        "request_wall_seconds": [1.0, 999.0, 10.0, 10.0, 100.0, 100.0],
        "requested_s2_cells": [10, 10, 100, 100, 1000, 1000],
        "returned_s2_cells": [9, 0, 90, 90, 900, 900],
        "returned_values": [1, 0, 2, 2, 3, 3],
        "area_km2": [1.0] * 6, "duration_days": [7] * 6, "requested_factors": [2] * 6,
    })
    summary = analysis.scaling_summary(runs)
    level8 = summary[summary["input_value"] == 8].iloc[0]
    assert level8["n"] == 1 and level8["median"] == 1.0 and level8["failed_runs"] == 1
    fit = analysis.scaling_fit(runs, "S2 level", x="requested_s2_cells")
    assert fit["slope"] == pytest.approx(1.0)


def _observations(values_a, values_b, variable, source_a="DWD", source_b="ERA5"):
    rows = []
    for day, (a, b) in enumerate(zip(values_a, values_b), start=1):
        for source, value in ((source_a, a), (source_b, b)):
            rows.append({"scenario": "s", "region": "r", "period": "July",
                         "timestamp": pd.Timestamp(2018, 7, day), "cell": "c",
                         "variable": variable, "source": source, "value": value})
    return pd.DataFrame(rows)


def test_pairs_are_strict_and_oriented_against_era5():
    obs = _observations([1.0, 2.0], [0.5, 1.5], "temperature", source_a="ERA5", source_b="DWD")
    lonely = obs.iloc[[0]].assign(timestamp=pd.Timestamp(2018, 7, 9))
    pairs = analysis.pair_observations(pd.concat([obs, lonely]))
    assert len(pairs) == 2
    assert set(pairs["source_b"]) == {"ERA5"}
    assert pairs["difference"].tolist() == [-0.5, -0.5]


def test_agreement_metrics():
    pairs = analysis.pair_observations(
        _observations([1.0, 2.0, 3.0, 4.0], [2.0, 3.0, 4.0, 6.0], "temperature")
    )
    metrics = analysis.agreement_metrics(pairs).iloc[0]
    assert metrics["n_pairs"] == 4
    assert metrics["mean_bias"] == pytest.approx(-1.25)
    assert metrics["mae"] == pytest.approx(1.25)
    assert metrics["rmse"] == pytest.approx(math.sqrt((1 + 1 + 1 + 4) / 4))
    assert metrics["spearman_rho"] == pytest.approx(1.0)
    assert 0.9 < metrics["pearson_r"] < 1.0


def test_precipitation_wet_day_and_accumulation_agreement():
    pairs = analysis.pair_observations(
        _observations([0.0, 5.0, 2.0, 0.2], [0.1, 4.0, 0.5, 3.0], "precipitation")
    )
    result = analysis.precipitation_agreement(pairs).iloc[0]
    assert (result["both_wet"], result["wet_only_a"], result["wet_only_b"], result["both_dry"]) == (1, 1, 1, 1)
    assert result["wet_day_agreement"] == pytest.approx(0.5)
    assert result["wet_day_kappa"] == pytest.approx(0.0)
    assert result["total_a_mm"] == pytest.approx(7.2)
    assert result["total_b_mm"] == pytest.approx(7.6)


def test_coverage_effect_reports_runtime_saved_and_avoided_requests():
    runs = pd.DataFrame({
        "experiment": ["coverage"] * 6,
        "scenario": ["neg"] * 6,
        "mode": ["precheck"] * 3 + ["factor-only"] * 3,
        "request_wall_seconds": [0.1, 0.2, 0.15, 5.0, 6.0, 5.5],
        "precheck_seconds": [1e-4] * 6,
        "planned_requests_avoided_vs_factor_only": [2] * 6,
    })
    effect = analysis.coverage_effect(runs).iloc[0]
    assert effect["median_runtime_saved"] == pytest.approx(5.35)
    assert effect["saved_ci_low"] > 0
    assert effect["requests_avoided_vs_factor_only"] == 2


def test_analysis_reads_a_collection_written_by_the_collector(tmp_path):
    import json

    run = {
        "run_id": 1, "experiment": "scaling", "scenario": "s", "dimension": "S2 level",
        "input_value": 10, "mode": None, "repeat": 1, "status": "success",
        "request": {"level": 10}, "request_wall_seconds": 2.0,
        "coverage_precheck": {"precheck_seconds": 0.001},
        "dispatch": [{"source": "x.cds_single_levels", "status": "success", "wall_seconds": 1.5}],
        "dispatch_status_counts": {"success": 1},
        "workload": {"requested_s2_cells": 136, "returned_values": 10},
        "memory": {"peak_rss_mb": 512.0},
        "planned_coverage": {"requests_avoided_vs_factor_only": 0},
    }
    (tmp_path / "empirical_runs.json").write_text(json.dumps({"runs": [run]}), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps({"git": {}}), encoding="utf-8")

    collection = analysis.load_collection(tmp_path)
    row = collection["runs"].iloc[0]
    assert row["requested_s2_cells"] == 136 and row["peak_rss_mb"] == 512.0
    assert row["unproductive_dispatches"] == 0
    assert collection["dispatch"].iloc[0]["source_short"] == "cds_single_levels"

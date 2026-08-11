"""Validation and reduction helpers for live FARMWISE evaluation artifacts."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd

from evaluation.cross_source_agreement import validate_observations

def load_empirical_runs(path: Path) -> dict[str, Any]:
    """Load a collector bundle and reject synthetic or incomplete provenance."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("mode") != "empirical-live":
        raise ValueError("Dispatch bundle is not labelled empirical-live.")
    runs = payload.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ValueError("Dispatch bundle contains no live runs.")
    return payload


def load_empirical_observations(path: Path) -> pd.DataFrame:
    """Load canonical live observations and enforce usable source overlap."""
    observations = validate_observations(pd.read_csv(path))
    if observations.empty:
        raise ValueError("Empirical observation input is empty.")
    sources = set(observations["source"].astype(str))
    synthetic_sources = {
        source for source in sources if "synthetic" in source.lower()
    }
    if synthetic_sources:
        raise ValueError(
            "Synthetic sources are not accepted by the empirical runner: "
            f"{sorted(synthetic_sources)}"
        )
    if len(sources) < 2:
        raise ValueError(
            "Empirical agreement requires at least two distinct sources."
        )
    keys = ["timestamp", "cell", "variable", "source"]
    if observations.duplicated(keys, keep=False).any():
        raise ValueError(
            "Empirical observations contain duplicate source/cell/time/variable "
            "rows; resolve their provenance before agreement analysis."
        )
    return observations


def load_empirical_quality_reports(directory: Path) -> list[dict[str, Any]]:
    """Load persisted live quality reports and reject smoke-test reports."""
    if not directory.is_dir():
        raise FileNotFoundError(
            f"Quality report directory does not exist: {directory}"
        )
    reports = []
    required = {
        "source",
        "request_id",
        "created_at",
        "S2_completeness",
        "total_missing_values",
    }
    for path in sorted(directory.rglob("*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        mode = str(report.get("evaluation_mode", "")).lower()
        source = str(report.get("source", "")).lower()
        if "synthetic" in mode or "synthetic" in source:
            raise ValueError(
                f"Synthetic quality report is not empirical: {path}"
            )
        missing = required.difference(report)
        if missing:
            raise ValueError(
                f"Incomplete empirical quality report {path}: "
                f"missing {sorted(missing)}"
            )
        report["_path"] = str(path)
        reports.append(report)
    if not reports:
        raise ValueError(
            f"No persisted JSON quality reports found in {directory}."
        )
    return reports


def empirical_coverage_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Reduce live dispatch metadata to coverage and latency measurements.

    Saved time is a conservative cross-scenario estimate: for each avoided
    source, use its median observed dispatch duration from another live run.
    Sources never observed are excluded and reported through latency coverage.
    """
    durations: dict[str, list[float]] = defaultdict(list)
    for run in payload["runs"]:
        if run.get("run_kind", "coverage") != "coverage":
            continue
        for dispatch in run.get("dispatch", []):
            source = dispatch.get("source")
            duration = dispatch.get("wall_seconds")
            if source and isinstance(duration, (int, float)) and duration >= 0:
                durations[source].append(float(duration))
    medians = {
        source: median(values) for source, values in durations.items() if values
    }

    records = []
    for run in payload["runs"]:
        if run.get("run_kind", "coverage") != "coverage":
            continue
        coverage = run.get("coverage_precheck")
        request = run.get("request")
        if not isinstance(coverage, dict) or not isinstance(request, dict):
            raise ValueError(
                "Every empirical run must contain request and "
                "coverage_precheck mappings."
            )
        decisions = coverage.get("sources", [])
        avoided_sources = [
            decision["source"]
            for decision in decisions
            if not decision.get("dispatched")
        ]
        observed_avoided = [
            source for source in avoided_sources if source in medians
        ]
        saved_lower_bound = sum(medians[source] for source in observed_avoided)
        filtered_dispatch_seconds = sum(
            float(dispatch.get("wall_seconds", 0.0))
            for dispatch in run.get("dispatch", [])
        )
        precheck_seconds = float(coverage.get("precheck_seconds", 0.0))
        filtered_seconds = precheck_seconds + filtered_dispatch_seconds
        candidate_sources = int(
            coverage.get("candidate_sources", len(decisions))
        )
        dispatched_sources = int(
            coverage.get(
                "dispatched_sources",
                sum(bool(item.get("dispatched")) for item in decisions),
            )
        )
        avoided = candidate_sources - dispatched_sources
        records.append(
            {
                "scenario": request["scenario"],
                "country": request["country"],
                "level": request["level"],
                "factor_count": len(request["factors"]),
                "factors": "|".join(request["factors"]),
                "time_from": request["time_from"],
                "time_to": request["time_to"],
                "latency_mode": "empirical-observed-lower-bound",
                "candidate_sources": candidate_sources,
                "dispatched_sources": dispatched_sources,
                "requests_avoided": avoided,
                "avoidance_rate": (
                    avoided / candidate_sources if candidate_sources else 0.0
                ),
                "precheck_seconds": precheck_seconds,
                "filtered_dispatch_seconds": filtered_dispatch_seconds,
                "filtered_wall_seconds": filtered_seconds,
                "unfiltered_wall_seconds": filtered_seconds
                + saved_lower_bound,
                "wall_seconds_saved": saved_lower_bound,
                "avoided_sources_with_observed_latency": len(
                    observed_avoided
                ),
                "avoided_latency_coverage_rate": (
                    len(observed_avoided) / len(avoided_sources)
                    if avoided_sources
                    else 1.0
                ),
                "request_wall_seconds": float(
                    run.get("request_wall_seconds", 0.0)
                ),
                "request_status": run.get("status", "unknown"),
            }
        )
    return records


def empirical_live_scaling_records(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Aggregate repeated end-to-end live scaling requests by case."""
    scaling_runs = [
        run
        for run in payload["runs"]
        if run.get("run_kind") == "live-scaling"
    ]
    if not scaling_runs:
        raise ValueError(
            "The empirical bundle contains no live scaling runs. Recollect "
            "inputs with evaluation.collect_empirical."
        )

    dimensions = {
        str(run.get("request", {}).get("dimension")) for run in scaling_runs
    }
    required_dimensions = {"S2 level", "Bounding-box area", "Factor count"}
    missing_dimensions = required_dimensions.difference(dimensions)
    if missing_dimensions:
        raise ValueError(
            "Live scaling bundle is incomplete; missing dimensions: "
            f"{sorted(missing_dimensions)}. Recollect empirical inputs."
        )

    grouped: dict[tuple[str, float], list[dict[str, Any]]] = defaultdict(list)
    for run in scaling_runs:
        request = run.get("request", {})
        dimension = request.get("dimension")
        input_value = request.get("input_value")
        if dimension is None or input_value is None:
            raise ValueError(
                "A live scaling run is missing dimension or input_value."
            )
        grouped[(str(dimension), float(input_value))].append(run)

    records = []
    for (dimension, input_value), runs in grouped.items():
        successful = [run for run in runs if run.get("status") == "success"]
        if not successful:
            raise ValueError(
                f"No successful live repeats for {dimension}={input_value}."
            )
        if any(
            not isinstance(run.get("peak_traced_memory_mb"), (int, float))
            for run in successful
        ):
            raise ValueError(
                "Live scaling runs lack peak memory measurements; recollect "
                "the empirical inputs with the current collector."
            )
        latencies = pd.Series(
            [run["request_wall_seconds"] for run in successful], dtype=float
        )
        peaks = pd.Series(
            [run["peak_traced_memory_mb"] for run in successful], dtype=float
        )
        request = successful[0]["request"]
        north, south, east, west = request["bounding_box"]
        records.append(
            {
                "dimension": dimension,
                "input_value": input_value,
                "measurement_mode": "empirical-live-end-to-end",
                "level": request["level"],
                "factor_count": len(request["factors"]),
                "bbox_area_degrees2": (north - south) * (east - west),
                "repeat_count": len(runs),
                "successful_repeats": len(successful),
                "failed_repeats": len(runs) - len(successful),
                "latency_seconds": float(latencies.median()),
                "latency_p25_seconds": float(latencies.quantile(0.25)),
                "latency_p75_seconds": float(latencies.quantile(0.75)),
                "peak_memory_mb": float(peaks.median()),
                "peak_memory_p25_mb": float(peaks.quantile(0.25)),
                "peak_memory_p75_mb": float(peaks.quantile(0.75)),
                "max_peak_memory_mb": float(peaks.max()),
                "cell_count": int(
                    median(
                        float(run.get("returned_cell_count", 0))
                        for run in successful
                    )
                ),
                "value_count": int(
                    median(
                        float(run.get("non_null_value_count", 0))
                        for run in successful
                    )
                ),
                "median_returned_factor_count": float(
                    median(
                        float(run.get("returned_factor_count", 0))
                        for run in successful
                    )
                ),
                "median_dispatch_seconds": float(
                    median(
                        sum(
                            float(item.get("wall_seconds", 0.0))
                            for item in run.get("dispatch", [])
                        )
                        for run in successful
                    )
                ),
                "median_successful_sources": float(
                    median(
                        sum(
                            item.get("status") == "success"
                            for item in run.get("dispatch", [])
                        )
                        for run in successful
                    )
                ),
            }
        )

    for dimension in {record["dimension"] for record in records}:
        subset = [
            record for record in records if record["dimension"] == dimension
        ]
        values = [float(record["input_value"]) for record in subset]
        low, high = min(values), max(values)
        for record in subset:
            record["normalized_scale"] = (
                (float(record["input_value"]) - low) / (high - low)
                if high > low
                else 0.0
            )
    return sorted(records, key=lambda row: (row["dimension"], row["input_value"]))

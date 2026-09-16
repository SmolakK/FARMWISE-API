"""Collect raw, frozen empirical outputs for the FARMWISE evaluation.

This module only *executes* the experiments defined in
:mod:`evaluation.scenarios` and writes what it measured. It computes no
statistics.

Each collection is written to its own directory and is never overwritten::

    empirical_input/<collection-id>/
        manifest.json                   provenance + complete configuration
        empirical_runs.json             one record per measured request
        cross_source_observations.csv   long-format separate-source values
        cross_source_observations_restricted.csv
                                        IMGW rows only; git-ignored, local use
        quality/                        per-source quality reports

Experiments, in execution order:

1. ``coverage``         pre-check vs factor-only routing, quality off
2. ``cross-source``     separate-source values for agreement analysis
3. ``quality-overhead`` one request with quality assessment off vs on
4. ``scaling``          S2 level, spatial extent and temporal extent sweeps

Within an experiment, warm-up executions run first and are excluded from
``runs`` (they are listed separately in ``warmup_runs``); the measured
executions then run in an order shuffled with ``RANDOM_SEED``.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
from time import perf_counter

import pandas as pd
from tqdm import tqdm

from farmwise_api.core.main_call import (
    _default_disabled_sources,
    plan_source_dispatch,
    read_data,
)
from farmwise_api.core.utils.access_policy import (
    acknowledged_private_noncommercial_imgw,
    private_noncommercial_imgw_enabled,
)
from evaluation import scenarios as config
from evaluation.collect_cross_source import (
    separate_frame_to_observations,
    summarise_source_comparison,
    write_observations,
)
from evaluation.coverage_baseline import coverage_counts, factor_only_routing
from evaluation.run_instrumentation import MemoryMonitor, provenance
from evaluation.workload import request_workload, result_workload, source_timings

OUTPUT_ROOT = Path(__file__).resolve().parent / "empirical_input"
# File-level opt-in for this academic evaluation. It affects only direct
# execution of this collector; the public FARMWISE server continues to block
# IMGW through its own source policy.
INCLUDE_IMGW_RESEARCH = True

IMGW_ATTRIBUTION = (
    "Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki "
    "Wodnej – Państwowy Instytut Badawczy. Dane Instytutu Meteorologii i "
    "Gospodarki Wodnej – Państwowego Instytutu Badawczego zostały przetworzone."
)
EXPERIMENTS = ("coverage", "cross-source", "quality-overhead", "scaling")
OBSERVATION_COLUMNS = [
    "timestamp", "cell", "variable", "source", "value", "scenario", "region", "period",
]


@dataclass(frozen=True)
class WorkItem:
    """One execution of one request."""
    experiment: str
    request: dict
    repeat: int            # 1-based for measured runs, 0 for warm-ups
    mode: str | None = None
    warmup: bool = False

    @property
    def assess_quality(self) -> bool:
        if self.experiment == "cross-source":
            return True
        if self.experiment == "quality-overhead":
            return config.QUALITY_MODES[self.mode][0]
        return False

    @property
    def persist_quality_reports(self) -> bool:
        if self.experiment == "cross-source":
            return True
        if self.experiment == "quality-overhead":
            return config.QUALITY_MODES[self.mode][1]
        return False

    @property
    def separate_api(self) -> bool:
        return self.experiment in {"coverage", "cross-source"}


def _phase(items_measured, items_warmup, rng) -> list[WorkItem]:
    warmups = list(items_warmup)
    measured = list(items_measured)
    rng.shuffle(warmups)
    rng.shuffle(measured)
    return warmups + measured


def build_work_plan(
    *,
    coverage_scenarios=config.REQUEST_SCENARIOS,
    cross_scenarios=config.CROSS_SOURCE_SCENARIOS,
    quality_scenario=config.QUALITY_OVERHEAD_SCENARIO,
    scaling_scenarios=config.LIVE_SCALING_SCENARIOS,
    coverage_repeats=config.COVERAGE_REPEATS,
    coverage_warmups=config.COVERAGE_WARMUPS,
    quality_repeats=config.QUALITY_OVERHEAD_REPEATS,
    quality_warmups=config.QUALITY_OVERHEAD_WARMUPS,
    scaling_repeats=config.SCALING_REPEATS,
    scaling_warmups=config.SCALING_WARMUPS,
    seed=config.RANDOM_SEED,
    experiments=None,
) -> list[WorkItem]:
    """Deterministic execution order for a whole collection.

    The full plan is always built first and then filtered to ``experiments``,
    so a subset keeps the same seeded order it has within a full collection.
    """
    experiments = EXPERIMENTS if experiments is None else tuple(experiments)
    for name, value in (
        ("coverage_repeats", coverage_repeats),
        ("quality_repeats", quality_repeats),
        ("scaling_repeats", scaling_repeats),
    ):
        if value < 1:
            raise ValueError(f"{name} must be at least 1")
    rng = random.Random(seed)
    plan: list[WorkItem] = []

    plan += _phase(
        [
            WorkItem("coverage", request, repeat, mode)
            for request in coverage_scenarios
            for mode in config.COVERAGE_MODES
            for repeat in range(1, coverage_repeats + 1)
        ],
        [
            WorkItem("coverage", request, 0, mode, warmup=True)
            for request in coverage_scenarios
            for mode in config.COVERAGE_MODES
            for _ in range(coverage_warmups)
        ],
        rng,
    )
    # Cross-source runs are single observational collections, not timings.
    plan += [WorkItem("cross-source", request, 1) for request in cross_scenarios]
    if quality_scenario is not None:
        plan += _phase(
            [
                WorkItem("quality-overhead", quality_scenario, repeat, mode)
                for mode in config.QUALITY_MODES
                for repeat in range(1, quality_repeats + 1)
            ],
            [
                WorkItem("quality-overhead", quality_scenario, 0, mode, warmup=True)
                for mode in config.QUALITY_MODES
                for _ in range(quality_warmups)
            ],
            rng,
        )
    plan += _phase(
        [
            WorkItem("scaling", request, repeat)
            for request in scaling_scenarios
            for repeat in range(1, scaling_repeats + 1)
        ],
        [
            WorkItem("scaling", request, 0, warmup=True)
            for request in scaling_scenarios
            for _ in range(scaling_warmups)
        ],
        rng,
    )
    return [item for item in plan if item.experiment in experiments]


async def execute(item: WorkItem, *, timeout, quality_dir, rss_interval) -> tuple[dict, pd.DataFrame | None]:
    """Run one work item and return its record and returned frame."""
    request = item.request
    # A scenario may exclude sources (e.g. ERA5 from the single-backend scaling
    # sweeps). read_data adds these to its default exclusions (licence gates,
    # broken upstreams); the planned routing below must do the same.
    extra_disabled = request.get("disabled_sources") or None
    planning_disabled = (
        {**_default_disabled_sources(), **extra_disabled} if extra_disabled else None
    )
    # Planned routing and workload are computed before, and excluded from,
    # the timed section.
    plan = plan_source_dispatch(
        request["bounding_box"], request["time_from"], request["time_to"],
        request["factors"], disabled_sources=planning_disabled,
    )
    record = {
        "experiment": item.experiment,
        "scenario": request["scenario"],
        "dimension": request.get("dimension"),
        "input_value": request.get("input_value"),
        "mode": item.mode,
        "repeat": item.repeat,
        "request": request,
        "settings": {
            "assess_quality": item.assess_quality,
            "persist_quality_reports": item.persist_quality_reports,
            "separate_api": item.separate_api,
            "routing": item.mode if item.experiment == "coverage" else "precheck",
            "timeout_seconds": timeout,
            "disabled_sources": sorted(extra_disabled) if extra_disabled else [],
        },
        "workload": request_workload(request),
        "planned_coverage": coverage_counts(plan),
        "started_utc": datetime.now(timezone.utc).isoformat(),
    }
    routing = (
        factor_only_routing()
        if item.experiment == "coverage" and item.mode == "factor-only"
        else nullcontext()
    )
    frame = None
    monitor = MemoryMonitor(interval_seconds=rss_interval)
    started = perf_counter()
    try:
        with routing, monitor:
            result = await read_data(
                bounding_box=request["bounding_box"],
                level=request["level"],
                time_from=request["time_from"],
                time_to=request["time_to"],
                factors=request["factors"],
                separate_api=item.separate_api,
                timeout=timeout,
                assess_quality=item.assess_quality,
                persist_quality_reports=item.persist_quality_reports,
                quality_report_dir=quality_dir,
                disabled_sources=extra_disabled,
            )
        record["request_wall_seconds"] = perf_counter() - started
        metadata = result.get("metadata", {}) if isinstance(result, dict) else {}
        frame = result.get("data") if isinstance(result, dict) else None
        record["status"] = (
            "success" if frame is not None and not frame.empty else "no-data"
        )
        record["error"] = metadata.get("error")
        record["coverage_precheck"] = metadata.get("coverage_precheck")
        record["dispatch"] = metadata.get("dispatch", [])
        record["quality_assessment"] = metadata.get("quality_assessment")
        record["quality_report_count"] = len(metadata.get("quality_reports", []))
    except Exception as error:  # noqa: BLE001 - every failure is data here
        record["request_wall_seconds"] = perf_counter() - started
        record["status"] = "error"
        record["error"] = f"{type(error).__name__}: {error}"
        record["coverage_precheck"] = None
        record["dispatch"] = []
        record["quality_assessment"] = None
        record["quality_report_count"] = 0
    record["memory"] = monitor.result
    record["workload"].update(result_workload(frame))
    record.update(source_timings(record["dispatch"]))
    return record, frame


async def collect(
    *,
    coverage_scenarios=config.REQUEST_SCENARIOS,
    cross_scenarios=config.CROSS_SOURCE_SCENARIOS,
    quality_scenario=config.QUALITY_OVERHEAD_SCENARIO,
    scaling_scenarios=config.LIVE_SCALING_SCENARIOS,
    coverage_repeats=config.COVERAGE_REPEATS,
    coverage_warmups=config.COVERAGE_WARMUPS,
    quality_repeats=config.QUALITY_OVERHEAD_REPEATS,
    quality_warmups=config.QUALITY_OVERHEAD_WARMUPS,
    scaling_repeats=config.SCALING_REPEATS,
    scaling_warmups=config.SCALING_WARMUPS,
    seed=config.RANDOM_SEED,
    output_root=OUTPUT_ROOT,
    collection_id: str | None = None,
    timeout=config.REQUEST_TIMEOUT_SECONDS,
    rss_interval=config.RSS_SAMPLING_INTERVAL_SECONDS,
    experiments=EXPERIMENTS,
) -> dict:
    """Execute the selected experiments and write one frozen collection.

    ``experiments`` selects a subset of ``EXPERIMENTS``, e.g. to re-collect
    only ``("cross-source",)`` into a separate collection.
    """
    experiments = tuple(experiments)
    unknown = set(experiments) - set(EXPERIMENTS)
    if unknown or not experiments:
        raise ValueError(f"experiments must be a non-empty subset of {EXPERIMENTS}; got {experiments}")
    started_at = datetime.now(timezone.utc)
    collection_id = collection_id or started_at.strftime("%Y%m%dT%H%M%SZ")
    needs_imgw = "cross-source" in experiments and any(
        "IMGW" in s.get("required_sources", []) for s in cross_scenarios
    )
    if needs_imgw and not private_noncommercial_imgw_enabled():
        print(
            "WARNING: IMGW research use is not acknowledged in this process, so "
            "IMGW will not be dispatched and IMGW-ERA5 scenarios will lack IMGW. "
            "Run `python -m evaluation.collect_empirical`, which opens the gate.",
            file=sys.stderr,
        )
    output_dir = Path(output_root) / collection_id
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(
            f"{output_dir} already holds a collection; frozen outputs are never "
            "overwritten. Choose another collection_id."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    quality_dir = output_dir / "quality"

    plan = build_work_plan(
        coverage_scenarios=coverage_scenarios, cross_scenarios=cross_scenarios,
        quality_scenario=quality_scenario, scaling_scenarios=scaling_scenarios,
        coverage_repeats=coverage_repeats, coverage_warmups=coverage_warmups,
        quality_repeats=quality_repeats, quality_warmups=quality_warmups,
        scaling_repeats=scaling_repeats, scaling_warmups=scaling_warmups,
        seed=seed, experiments=experiments,
    )
    run_config = {
        **config.evaluation_config(),
        "random_seed": seed,
        "request_timeout_seconds": timeout,
        "rss_sampling_interval_seconds": rss_interval,
    }
    # UPDATE to anything that was changed within this call
    run_config["coverage"].update(
        repeats=coverage_repeats, warmups_per_scenario_and_mode=coverage_warmups,
        scenarios=coverage_scenarios,
    )
    run_config["cross_source"]["scenarios"] = cross_scenarios
    run_config["quality_overhead"].update(
        repeats=quality_repeats, warmups_per_mode=quality_warmups,
        scenario=quality_scenario,
    )
    run_config["scaling"].update(
        repeats=scaling_repeats, warmups_per_scenario=scaling_warmups,
        scenarios=scaling_scenarios,
    )
    manifest = provenance(run_config, started_at=started_at)
    manifest["collection_id"] = collection_id
    manifest["experiments"] = list(experiments)
    manifest["imgw_research_use_enabled"] = private_noncommercial_imgw_enabled()
    manifest["execution_order"] = [
        {"experiment": i.experiment, "scenario": i.request["scenario"],
         "mode": i.mode, "repeat": i.repeat, "warmup": i.warmup}
        for i in plan
    ]
    manifest_path = output_dir / "manifest.json"
    _write_json(manifest_path, manifest)

    runs, warmup_runs, observation_frames = [], [], []
    progress = tqdm(plan, desc="Empirical collection", unit="request",
                    dynamic_ncols=True, file=sys.stdout)
    for item in progress:
        progress.set_postfix_str(
            f"{item.experiment}:{item.request['scenario']}"
            f"{':' + item.mode if item.mode else ''}"
            f"{' warm-up' if item.warmup else f' #{item.repeat}'}",
            refresh=True,
        )
        record, frame = await execute(
            item, timeout=timeout, quality_dir=quality_dir, rss_interval=rss_interval,
        )
        if item.warmup:
            warmup_runs.append({
                key: record.get(key) for key in (
                    "experiment", "scenario", "mode", "status", "error",
                    "request_wall_seconds", "started_utc",
                )
            })
            continue
        record["run_id"] = len(runs) + 1
        if item.experiment == "cross-source" and record["status"] == "success":
            observations = separate_frame_to_observations(frame)
            record["cross_source_comparison"] = summarise_source_comparison(
                observations, required_sources=item.request.get("required_sources", []),
            )
            if not observations.empty:
                observations["scenario"] = item.request["scenario"]
                observations["region"] = item.request.get("region")
                observations["period"] = item.request.get("period")
                observation_frames.append(observations)
        runs.append(record)

    observations = (
        pd.concat(observation_frames, ignore_index=True)
        if observation_frames else pd.DataFrame(columns=OBSERVATION_COLUMNS)
    )
    observation_paths = write_observations(output_dir, observations)

    finished_at = datetime.now(timezone.utc)
    payload = {
        "schema_version": 2,
        "collection_id": collection_id,
        "collected_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "manifest": manifest_path.name,
        "imgw_research_use_enabled": private_noncommercial_imgw_enabled(),
        "imgw_attribution": (
            IMGW_ATTRIBUTION if private_noncommercial_imgw_enabled() else None
        ),
        "quality_report_dir": "quality",
        "runs": runs,
        "warmup_runs": warmup_runs,
    }
    runs_path = output_dir / "empirical_runs.json"
    _write_json(runs_path, payload)
    manifest["collection_finished_utc"] = finished_at.isoformat()
    _write_json(manifest_path, manifest)
    return {
        "collection_dir": output_dir,
        "manifest": manifest_path,
        "runs": runs_path,
        "observations": observation_paths["public"],
        "restricted_observations": observation_paths["restricted"],
        "quality_reports": quality_dir,
        "request_count": len(runs),
        "warmup_count": len(warmup_runs),
        "observation_count": len(observations),
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )


def main(argv=None) -> None:
    """Collect the selected experiments into a new frozen collection.

    python -m evaluation.collect_empirical
    python -m evaluation.collect_empirical --experiments cross-source
    """
    parser = argparse.ArgumentParser(
        description="Collect the selected experiments into a new frozen collection."
    )
    parser.add_argument(
        "--experiments", nargs="+", choices=EXPERIMENTS, default=list(EXPERIMENTS),
        help="experiments to run (default: all)",
    )
    parser.add_argument(
        "--collection-id", default=None,
        help="output directory name under empirical_input/ (default: UTC start time)",
    )
    args = parser.parse_args(argv)
    # The acknowledgement is scoped to this collection run. Leaving it set
    # would silently open the IMGW licence gate for anything else running
    # later in the same process.
    acknowledgement = (
        acknowledged_private_noncommercial_imgw()
        if INCLUDE_IMGW_RESEARCH
        else nullcontext()
    )
    with acknowledgement:
        result = asyncio.run(collect(
            experiments=tuple(args.experiments), collection_id=args.collection_id,
        ))
    print(
        f"Collected {result['request_count']} measured requests "
        f"({result['warmup_count']} warm-ups excluded) and "
        f"{result['observation_count']} cross-source observations in "
        f"{result['collection_dir']}."
    )


if __name__ == "__main__":
    main()

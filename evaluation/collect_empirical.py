"""Collect live empirical inputs for analysis in the evaluation notebooks."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import sys
from time import perf_counter
import tracemalloc

import pandas as pd
from tqdm import tqdm

from farmwise_api.core.main_call import plan_source_dispatch, read_data
from farmwise_api.core.utils.access_policy import (
    IMGW_RESEARCH_USE_ENV,
    private_noncommercial_imgw_enabled,
)
from evaluation.collect_cross_source import (
    separate_frame_to_observations,
    summarise_source_comparison,
    validate_private_output,
)
from evaluation.scenarios import (
    CROSS_SOURCE_SCENARIOS,
    LIVE_SCALING_SCENARIOS,
    REQUEST_SCENARIOS,
)


OUTPUT_DIR = Path(__file__).resolve().parent / "empirical_input"
SCALING_REPEATS = 3
REQUEST_TIMEOUT_SECONDS = 600
# File-level opt-in for this academic evaluation. This affects only direct
# execution of this collector; the public FARMWISE server continues to block
# IMGW through its own source policy.
INCLUDE_IMGW_RESEARCH = True


async def collect(
    scenarios=REQUEST_SCENARIOS,
    scaling_scenarios=LIVE_SCALING_SCENARIOS,
    cross_scenarios=CROSS_SOURCE_SCENARIOS,
    scaling_repeats=SCALING_REPEATS,
    *,
    output_dir=OUTPUT_DIR,
    timeout=REQUEST_TIMEOUT_SECONDS,
) -> dict:
    """Collect raw request, scaling, cross-source, and quality measurements."""
    if scaling_repeats < 1:
        raise ValueError("scaling_repeats must be at least 1")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    collection_started = datetime.now(timezone.utc)
    quality_run_name = collection_started.strftime("%Y%m%dT%H%M%S%fZ")
    quality_dir = output_dir / "quality" / quality_run_name
    observations_frames = []
    runs = []

    work_items = [
        (request, "coverage", 1) for request in scenarios
    ]
    work_items.extend(
        (request, "cross-source", 1) for request in cross_scenarios
    )

    scaling_items = [
        (request, "live-scaling", repeat)
        for repeat in range(1, scaling_repeats + 1)
        for request in scaling_scenarios
    ]
    random.Random(42).shuffle(scaling_items)
    work_items.extend(scaling_items)

    progress = tqdm(
        work_items,
        desc="Live empirical collection",
        unit="request",
        dynamic_ncols=True,
        file=sys.stdout,
    )
    for request, run_kind, repeat in progress:
        progress.set_postfix_str(
            f"{request['scenario']} ({repeat})", refresh=True
        )
        precheck_started = perf_counter()
        dispatch_plan = plan_source_dispatch(
            request["bounding_box"],
            request["time_from"],
            request["time_to"],
            request["factors"],
        )
        fallback_coverage = {
            "candidate_sources": len(dispatch_plan),
            "dispatched_sources": sum(
                item["dispatched"] for item in dispatch_plan
            ),
            "requests_avoided": sum(
                not item["dispatched"] for item in dispatch_plan
            ),
            "precheck_seconds": perf_counter() - precheck_started,
            "sources": dispatch_plan,
        }
        started = perf_counter()
        peak_memory_mb = None
        tracemalloc.start()
        try:
            result = await read_data(
                bounding_box=request["bounding_box"],
                level=request["level"],
                time_from=request["time_from"],
                time_to=request["time_to"],
                factors=request["factors"],
                separate_api=run_kind in {"coverage", "cross-source"},
                timeout=timeout,
                assess_quality=True,
                persist_quality_reports=True,
                quality_report_dir=quality_dir,
            )
            elapsed = perf_counter() - started
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peak_memory_mb = peak / (1024 * 1024)

            if not isinstance(result, dict):
                runs.append(
                    {
                        "request": request,
                        "run_kind": run_kind,
                        "repeat": repeat,
                        "status": "no-data",
                        "request_wall_seconds": elapsed,
                        "peak_traced_memory_mb": peak_memory_mb,
                        "coverage_precheck": fallback_coverage,
                        "dispatch": [],
                    }
                )
                continue

            metadata = result["metadata"]
            frame = result["data"]
            if isinstance(frame.columns, pd.MultiIndex):
                returned_cells = len(
                    frame.columns.get_level_values(1).unique()
                )
                returned_factors = len(
                    frame.columns.get_level_values(0).unique()
                )
            else:
                returned_cells = len(frame.columns)
                returned_factors = len(frame.columns)

            runs.append(
                {
                    "request": request,
                    "run_kind": run_kind,
                    "repeat": repeat,
                    "status": "success",
                    "request_wall_seconds": elapsed,
                    "peak_traced_memory_mb": peak_memory_mb,
                    "returned_row_count": len(frame),
                    "returned_column_count": len(frame.columns),
                    "returned_cell_count": returned_cells,
                    "returned_factor_count": returned_factors,
                    "non_null_value_count": int(frame.count().sum()),
                    "coverage_precheck": metadata["coverage_precheck"],
                    "dispatch": metadata["dispatch"],
                    "quality_report_count": len(
                        metadata.get("quality_reports", [])
                    ),
                }
            )

            if run_kind == "cross-source":
                observations = separate_frame_to_observations(frame)
                runs[-1]["cross_source_comparison"] = (
                    summarise_source_comparison(
                        observations,
                        required_sources=request.get(
                            "required_sources", []
                        ),
                    )
                )
                if not observations.empty:
                    observations["scenario"] = request["scenario"]
                    observations_frames.append(observations)
        except Exception as error:
            if tracemalloc.is_tracing():
                _current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                peak_memory_mb = peak / (1024 * 1024)
            runs.append(
                {
                    "request": request,
                    "run_kind": run_kind,
                    "repeat": repeat,
                    "status": "error",
                    "request_wall_seconds": perf_counter() - started,
                    "peak_traced_memory_mb": peak_memory_mb,
                    "error": str(error),
                    "coverage_precheck": fallback_coverage,
                    "dispatch": [],
                }
            )

    observations = (
        pd.concat(observations_frames, ignore_index=True)
        if observations_frames
        else pd.DataFrame(
            columns=[
                "timestamp",
                "cell",
                "variable",
                "source",
                "value",
                "scenario",
            ]
        )
    )
    observations_path = output_dir / "cross_source_observations_live.csv"
    validate_private_output(observations_path, observations)
    observations.to_csv(observations_path, index=False)

    payload = {
        "mode": "empirical-live",
        "collected_at": collection_started.isoformat(),
        "imgw_research_use_enabled": private_noncommercial_imgw_enabled(),
        "imgw_attribution": (
            "Źródłem pochodzenia danych jest Instytut Meteorologii i "
            "Gospodarki Wodnej – Państwowy Instytut Badawczy. Dane "
            "Instytutu Meteorologii i Gospodarki Wodnej – Państwowego "
            "Instytutu Badawczego zostały przetworzone."
            if private_noncommercial_imgw_enabled()
            else None
        ),
        "quality_report_dir": f"quality/{quality_run_name}",
        "live_scaling_repeats": scaling_repeats,
        "runs": runs,
    }
    runs_path = output_dir / "empirical_runs.json"
    runs_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return {
        "runs": runs_path,
        "observations": observations_path,
        "quality_reports": quality_dir,
        "request_count": len(runs),
        "observation_count": len(observations),
    }


def main() -> None:
    """Collect the scenarios configured in ``evaluation.scenarios``."""
    if INCLUDE_IMGW_RESEARCH:
        os.environ[IMGW_RESEARCH_USE_ENV] = "1"
    result = asyncio.run(
        collect(
            scenarios=REQUEST_SCENARIOS,
            scaling_scenarios=LIVE_SCALING_SCENARIOS,
            cross_scenarios=CROSS_SOURCE_SCENARIOS,
            scaling_repeats=SCALING_REPEATS,
        )
    )
    print(
        f"Collected {result['request_count']} live requests and "
        f"{result['observation_count']} cross-source observations in "
        f"{OUTPUT_DIR}."
    )


if __name__ == "__main__":
    main()

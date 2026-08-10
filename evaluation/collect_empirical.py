"""Collect live dispatch, agreement, and quality artifacts for evaluation."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from time import perf_counter

import pandas as pd
from tqdm import tqdm

from core.main_call import plan_source_dispatch, read_data
from core.utils.paths import CACHE_ROOT, PROJECT_ROOT
from evaluation.collect_cross_source import (
    separate_frame_to_observations,
    validate_private_output,
)
from evaluation.empirical import EMPIRICAL_RUN_SCHEMA_VERSION
from evaluation.scenarios import REQUEST_SCENARIOS


def _selected_scenarios(names: list[str] | None) -> list[dict]:
    scenarios_by_name = {
        scenario["scenario"]: scenario for scenario in REQUEST_SCENARIOS
    }
    if not names:
        return list(REQUEST_SCENARIOS)
    unknown = sorted(set(names) - set(scenarios_by_name))
    if unknown:
        raise ValueError(f"Unknown evaluation scenarios: {unknown}")
    return [scenarios_by_name[name] for name in names]


def _require_private_output_directory(path: Path) -> None:
    """Keep raw live evaluation artifacts outside the source repository."""
    try:
        path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return
    raise PermissionError(
        "Empirical collection output must be outside the repository because "
        "it may contain restricted live observations or derived reports."
    )


async def collect(args) -> dict:
    """Run selected live requests and persist raw provenance artifacts."""
    scenarios = _selected_scenarios(args.scenario)
    _require_private_output_directory(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    quality_dir = args.output_dir / "quality"
    observations_frames = []
    runs = []

    progress = tqdm(
        scenarios,
        desc="Live evaluation collection",
        unit="request",
        disable=args.no_progress,
        dynamic_ncols=True,
        file=sys.stdout,
    )
    for request in progress:
        progress.set_postfix_str(request["scenario"], refresh=True)
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
        try:
            result = await read_data(
                bounding_box=request["bounding_box"],
                level=request["level"],
                time_from=request["time_from"],
                time_to=request["time_to"],
                factors=request["factors"],
                separate_api=True,
                timeout=args.timeout,
                assess_quality=True,
                persist_quality_reports=True,
                quality_report_dir=quality_dir,
            )
            elapsed = perf_counter() - started
            if not isinstance(result, dict):
                runs.append(
                    {
                        "request": request,
                        "status": "no-data",
                        "request_wall_seconds": elapsed,
                        "coverage_precheck": fallback_coverage,
                        "dispatch": [],
                    }
                )
                continue
            metadata = result["metadata"]
            runs.append(
                {
                    "request": request,
                    "status": "success",
                    "request_wall_seconds": elapsed,
                    "coverage_precheck": metadata["coverage_precheck"],
                    "dispatch": metadata["dispatch"],
                    "quality_report_count": len(
                        metadata.get("quality_reports", [])
                    ),
                }
            )
            observations = separate_frame_to_observations(result["data"])
            if not observations.empty:
                observations["scenario"] = request["scenario"]
                observations_frames.append(observations)
        except Exception as error:
            runs.append(
                {
                    "request": request,
                    "status": "error",
                    "request_wall_seconds": perf_counter() - started,
                    "error": str(error),
                    "coverage_precheck": fallback_coverage,
                    "dispatch": [],
                }
            )
            if args.fail_fast:
                raise

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
    observations_path = args.output_dir / "cross_source_observations_live.csv"
    validate_private_output(observations_path, observations)
    observations.to_csv(observations_path, index=False)

    payload = {
        "schema_version": EMPIRICAL_RUN_SCHEMA_VERSION,
        "mode": "empirical-live",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "runs": runs,
    }
    runs_path = args.output_dir / "empirical_runs.json"
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=CACHE_ROOT / "evaluation" / "empirical_input",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        choices=[item["scenario"] for item in REQUEST_SCENARIOS],
        help="Run only this scenario; repeat the option to select several.",
    )
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--no-progress", action="store_true")
    args = parser.parse_args(argv)
    result = asyncio.run(collect(args))
    print(
        f"Collected {result['request_count']} live requests and "
        f"{result['observation_count']} observations in {args.output_dir}."
    )


if __name__ == "__main__":
    main()

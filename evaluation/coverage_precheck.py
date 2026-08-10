"""Benchmark requests avoided by FARMWISE's source coverage pre-check."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter, sleep

from tqdm import tqdm

from adapters.mappings.data_source_mapping import API_PATH_RANGES
from core.main_call import plan_source_dispatch
from evaluation.common import LOG_DIR, ensure_output_dirs, write_records
from evaluation.scenarios import REQUEST_SCENARIOS


def simulated_source_latencies(
    sources,
    *,
    latency_scale: float = 1.0,
) -> dict[str, float]:
    """Return deterministic latency values between 2 and 6 ms per source."""
    latencies = {}
    for source in sources:
        digest = hashlib.sha256(source.encode("utf-8")).digest()
        fraction = int.from_bytes(digest[:2], "big") / 65535
        latencies[source] = latency_scale * (0.002 + 0.004 * fraction)
    return latencies


def benchmark_coverage_precheck(
    scenarios=REQUEST_SCENARIOS,
    *,
    source_ranges=None,
    source_latencies=None,
    latency_scale: float = 1.0,
    execute_waits: bool = True,
    show_progress: bool = False,
    progress_position: int = 0,
    leave_progress: bool = True,
):
    """Run the pre-check batch and return one metrics record per request."""
    source_ranges = API_PATH_RANGES if source_ranges is None else source_ranges
    sources = list(source_ranges)
    latencies = (
        simulated_source_latencies(sources, latency_scale=latency_scale)
        if source_latencies is None
        else {
            source: float(source_latencies[source])
            for source in sources
        }
    )
    records = []

    requests = list(scenarios)
    progress = tqdm(
        requests,
        desc="Coverage pre-check",
        unit="request",
        total=len(requests),
        disable=not show_progress,
        dynamic_ncols=True,
        file=sys.stdout,
        position=progress_position,
        leave=leave_progress,
    )
    for request in progress:
        progress.set_postfix_str(request["scenario"], refresh=False)
        precheck_started = perf_counter()
        plan = plan_source_dispatch(
            request["bounding_box"],
            request["time_from"],
            request["time_to"],
            request["factors"],
            source_ranges=source_ranges,
        )
        precheck_seconds = perf_counter() - precheck_started
        dispatched = [
            item["source"] for item in plan if item["dispatched"]
        ]

        if execute_waits:
            baseline_started = perf_counter()
            for source in sources:
                sleep(latencies[source])
            unfiltered_seconds = perf_counter() - baseline_started

            filtered_started = perf_counter()
            for source in dispatched:
                sleep(latencies[source])
            filtered_dispatch_seconds = perf_counter() - filtered_started
        else:
            unfiltered_seconds = sum(latencies.values())
            filtered_dispatch_seconds = sum(
                latencies[source] for source in dispatched
            )

        filtered_seconds = precheck_seconds + filtered_dispatch_seconds
        avoided = len(sources) - len(dispatched)
        records.append(
            {
                "scenario": request["scenario"],
                "country": request["country"],
                "level": request["level"],
                "factor_count": len(request["factors"]),
                "factors": "|".join(request["factors"]),
                "time_from": request["time_from"],
                "time_to": request["time_to"],
                "latency_mode": (
                    "measured-simulation"
                    if execute_waits
                    else "profile-projection"
                ),
                "candidate_sources": len(sources),
                "dispatched_sources": len(dispatched),
                "requests_avoided": avoided,
                "avoidance_rate": avoided / len(sources) if sources else 0,
                "precheck_seconds": precheck_seconds,
                "unfiltered_wall_seconds": unfiltered_seconds,
                "filtered_wall_seconds": filtered_seconds,
                "wall_seconds_saved": max(
                    0.0, unfiltered_seconds - filtered_seconds
                ),
            }
        )
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=LOG_DIR / "coverage_precheck.csv",
    )
    parser.add_argument(
        "--latency-scale",
        type=float,
        default=1.0,
        help="Scale deterministic simulated adapter latency.",
    )
    parser.add_argument(
        "--latency-profile",
        type=Path,
        help="Optional JSON mapping of full source paths to observed seconds.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable the progress bar.",
    )
    args = parser.parse_args(argv)
    ensure_output_dirs()
    latency_profile = (
        json.loads(args.latency_profile.read_text(encoding="utf-8"))
        if args.latency_profile
        else None
    )
    records = benchmark_coverage_precheck(
        latency_scale=args.latency_scale,
        source_latencies=latency_profile,
        execute_waits=latency_profile is None,
        show_progress=not args.no_progress,
    )
    write_records(records, args.output)
    print(f"Wrote {len(records)} scenarios to {args.output}")


if __name__ == "__main__":
    main()

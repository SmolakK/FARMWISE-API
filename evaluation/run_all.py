"""Run FARMWISE empirical evaluation from collected live artifacts."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys

from tqdm import tqdm

from core.utils.paths import CACHE_ROOT
from evaluation.collect_cross_source import validate_private_output
from evaluation.collect_empirical import collect as collect_empirical
from evaluation.common import write_json, write_records
from evaluation.cross_source_agreement import compute_agreement_metrics
from evaluation.empirical import (
    empirical_coverage_records,
    empirical_live_scaling_records,
    load_empirical_observations,
    load_empirical_quality_reports,
    load_empirical_runs,
)
from evaluation.plots import generate_all_figures
from evaluation.scaling import benchmark_controlled_scaling
from evaluation.scenarios import REQUEST_SCENARIOS


def missing_empirical_inputs(
    runs_path: Path,
    observations_path: Path,
    quality_reports_dir: Path,
) -> list[Path]:
    """Return artifacts that have not yet been produced by the collector."""
    required = [runs_path, observations_path, quality_reports_dir]
    return [path for path in required if not path.exists()]


def run_all(
    *,
    runs_path: Path,
    observations_path: Path,
    quality_reports_dir: Path,
    output_dir: Path,
    reference_source="ERA5",
    controlled_scaling_repeats=5,
    show_progress=False,
):
    """Generate empirical results plus a separately labelled control sweep."""
    log_dir = output_dir / "logs"
    figure_dir = output_dir / "figures"

    # Validate before drawing a bar so missing collection artifacts produce a
    # clean IDE error instead of an abandoned 0% progress line.
    runs = load_empirical_runs(runs_path)
    observations = load_empirical_observations(observations_path)
    quality_reports = load_empirical_quality_reports(quality_reports_dir)
    validate_private_output(output_dir / "derived-results.csv", observations)

    progress = tqdm(
        total=7,
        desc="FARMWISE empirical evaluation",
        unit="stage",
        disable=not show_progress,
        dynamic_ncols=True,
        file=sys.stdout,
    )
    # Validate dir exist
    progress.set_postfix_str("validate live provenance", refresh=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    progress.update(1)

    # Measure coverage, latency, wall times, skipped sources, used sources
    progress.set_postfix_str("observed coverage", refresh=True)
    coverage = empirical_coverage_records(runs)
    write_records(coverage, log_dir / "coverage_precheck.csv")
    progress.update(1)

    # Measure scaling on empirical records, times taken to process, memory used
    progress.set_postfix_str("live end-to-end scaling", refresh=True)
    live_scaling = empirical_live_scaling_records(runs)
    write_records(live_scaling, log_dir / "scaling_live.csv")
    progress.update(1)
    # Run benchmark on controlled S2 scaling to see how this impact the wall times
    progress.set_postfix_str("controlled algorithmic scaling", refresh=True)
    controlled_scaling = benchmark_controlled_scaling(
        repeats=controlled_scaling_repeats,
        show_progress=show_progress,
        progress_position=1,
        leave_progress=False,
    )
    write_records(controlled_scaling, log_dir / "scaling_controlled.csv")
    progress.update(1)
    # Run tests on how values for the same factor and area agree between each other
    progress.set_postfix_str("observed source agreement", refresh=True)
    metrics, differences = compute_agreement_metrics(
        observations, reference_source=reference_source
    )
    if metrics.empty or differences.empty:
        raise ValueError(
            "Live observations contain no aligned cell-day pairs for "
            f"reference source {reference_source!r}."
        )
    metrics.to_csv(log_dir / "cross_source_agreement.csv", index=False)
    differences.to_csv(
        log_dir / "cross_source_differences.csv", index=False
    )
    progress.update(1)
    # Generate figures for the paper
    progress.set_postfix_str("live and controlled figures", refresh=True)
    figures = generate_all_figures(
        coverage_path=log_dir / "coverage_precheck.csv",
        scaling_path=log_dir / "scaling_live.csv",
        controlled_scaling_path=log_dir / "scaling_controlled.csv",
        differences_path=log_dir / "cross_source_differences.csv",
        figure_dir=figure_dir,
    )
    progress.update(1)

    progress.set_postfix_str("provenance manifest", refresh=True)
    latency_coverage = [
        record["avoided_latency_coverage_rate"] for record in coverage
    ]
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "empirical-live-with-controlled-supplement",
        "inputs": {
            "runs": str(runs_path.resolve()),
            "observations": str(observations_path.resolve()),
            "quality_reports": str(quality_reports_dir.resolve()),
            "collected_at": runs["collected_at"],
        },
        "method_notes": {
            "coverage_saved_time": (
                "Lower-bound estimate using median dispatch times observed "
                "for avoided sources in other live scenarios."
            ),
            "scaling_live": (
                "End-to-end read_data wall time and traced peak memory from "
                "live requests; cases vary one declared input dimension."
            ),
            "scaling_controlled": (
                "Supplementary generated workload measuring S2 covering, "
                "frame construction, and harmonization after warm-up."
            ),
            "agreement": (
                "Inner-aligned live observations by timestamp, S2 cell, and "
                "variable."
            ),
        },
        "coverage_scenarios": len(coverage),
        "mean_avoided_latency_coverage": (
            sum(latency_coverage) / len(latency_coverage)
            if latency_coverage
            else 0.0
        ),
        "live_scaling_cases": len(live_scaling),
        "controlled_scaling_cases": len(controlled_scaling),
        "agreement_pairs": len(metrics),
        "agreement_observations": len(differences),
        "quality_reports": len(quality_reports),
        "figures": [str(path.resolve()) for path in figures],
    }
    write_json(manifest, log_dir / "manifest.json")
    progress.update(1)
    progress.close()
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=CACHE_ROOT / "evaluation" / "empirical_input",
        help="Directory produced by evaluation.collect_empirical.",
    )
    parser.add_argument("--runs", type=Path)
    parser.add_argument("--observations", type=Path)
    parser.add_argument("--quality-reports", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=CACHE_ROOT / "evaluation" / "empirical_results",
    )
    parser.add_argument("--reference-source", default="ERA5")
    parser.add_argument(
        "--controlled-scaling-repeats",
        "--scaling-repeats",
        dest="controlled_scaling_repeats",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--collect",
        action="store_true",
        help="Collect live inputs before running analysis.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        choices=[item["scenario"] for item in REQUEST_SCENARIOS],
        help="With --collect, select a coverage/agreement scenario.",
    )
    parser.add_argument("--collection-timeout", type=float, default=600)
    parser.add_argument("--live-scaling-repeats", type=int, default=3)
    parser.add_argument("--collection-fail-fast", action="store_true")
    parser.add_argument("--no-progress", action="store_true")
    args = parser.parse_args(argv)

    runs_path = args.runs or args.input_dir / "empirical_runs.json"
    observations_path = (
        args.observations
        or args.input_dir / "cross_source_observations_live.csv"
    )
    quality_reports_dir = args.quality_reports or args.input_dir / "quality"
    if args.collect:
        if args.runs or args.observations or args.quality_reports:
            parser.error(
                "--collect writes standard artifacts under --input-dir and "
                "cannot be combined with individual input overrides."
            )
        asyncio.run(
            collect_empirical(
                argparse.Namespace(
                    output_dir=args.input_dir,
                    scenario=args.scenario,
                    timeout=args.collection_timeout,
                    live_scaling_repeats=args.live_scaling_repeats,
                    skip_live_scaling=False,
                    fail_fast=args.collection_fail_fast,
                    no_progress=args.no_progress,
                )
            )
        )

    missing = missing_empirical_inputs(
        runs_path, observations_path, quality_reports_dir
    )
    if missing:
        formatted = "\n  - ".join(str(path) for path in missing)
        parser.error(
            "empirical inputs have not been collected. Missing:\n"
            f"  - {formatted}\n"
            "Run once with script parameter --collect, or run: "
            "python -m evaluation.collect_empirical"
        )

    manifest = run_all(
        runs_path=runs_path,
        observations_path=observations_path,
        quality_reports_dir=quality_reports_dir,
        output_dir=args.output_dir,
        reference_source=args.reference_source,
        controlled_scaling_repeats=args.controlled_scaling_repeats,
        show_progress=not args.no_progress,
    )
    print(
        f"Generated empirical results from {manifest['coverage_scenarios']} "
        f"coverage requests, {manifest['live_scaling_cases']} live scaling "
        f"cases, and {manifest['agreement_observations']} aligned observations "
        f"in {args.output_dir}."
    )


if __name__ == "__main__":
    main()

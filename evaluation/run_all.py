"""Run the empirical FARMWISE evaluation from previously collected live data."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

from tqdm import tqdm

from core.utils.paths import CACHE_ROOT
from evaluation.collect_cross_source import validate_private_output
from evaluation.common import write_json, write_records
from evaluation.cross_source_agreement import compute_agreement_metrics
from evaluation.empirical import (
    empirical_coverage_records,
    load_empirical_observations,
    load_empirical_quality_reports,
    load_empirical_runs,
)
from evaluation.plots import generate_all_figures
from evaluation.scaling import benchmark_scaling


def run_all(
    *,
    runs_path: Path,
    observations_path: Path,
    quality_reports_dir: Path,
    output_dir: Path,
    reference_source="ERA5",
    scaling_repeats=5,
    show_progress=False,
):
    """Generate empirical tables and figures without synthetic fallbacks."""
    log_dir = output_dir / "logs"
    figure_dir = output_dir / "figures"

    progress = tqdm(
        total=6,
        desc="FARMWISE empirical evaluation",
        unit="stage",
        disable=not show_progress,
        dynamic_ncols=True,
        file=sys.stdout,
    )
    progress.set_postfix_str("validate live provenance", refresh=True)
    runs = load_empirical_runs(runs_path)
    observations = load_empirical_observations(observations_path)
    quality_reports = load_empirical_quality_reports(quality_reports_dir)
    validate_private_output(output_dir / "derived-results.csv", observations)
    log_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    progress.update(1)

    progress.set_postfix_str("observed coverage", refresh=True)
    coverage = empirical_coverage_records(runs)
    write_records(coverage, log_dir / "coverage_precheck.csv")
    progress.update(1)

    progress.set_postfix_str("measured scaling", refresh=True)
    scaling = benchmark_scaling(
        repeats=scaling_repeats,
        show_progress=show_progress,
        progress_position=1,
        leave_progress=False,
    )
    write_records(scaling, log_dir / "scaling.csv")
    progress.update(1)

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

    progress.set_postfix_str("empirical figures", refresh=True)
    figures = generate_all_figures(
        coverage_path=log_dir / "coverage_precheck.csv",
        scaling_path=log_dir / "scaling.csv",
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
        "mode": "empirical-live",
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
            "scaling": (
                "Measured locally on a controlled generated workload; it is "
                "not network end-to-end latency."
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
        "scaling_cases": len(scaling),
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
    parser.add_argument("--scaling-repeats", type=int, default=5)
    parser.add_argument("--no-progress", action="store_true")
    args = parser.parse_args(argv)
    runs_path = args.runs or args.input_dir / "empirical_runs.json"
    observations_path = (
        args.observations
        or args.input_dir / "cross_source_observations_live.csv"
    )
    quality_reports_dir = args.quality_reports or args.input_dir / "quality"
    manifest = run_all(
        runs_path=runs_path,
        observations_path=observations_path,
        quality_reports_dir=quality_reports_dir,
        output_dir=args.output_dir,
        reference_source=args.reference_source,
        scaling_repeats=args.scaling_repeats,
        show_progress=not args.no_progress,
    )
    print(
        f"Generated empirical results from {manifest['coverage_scenarios']} "
        f"live requests and {manifest['agreement_observations']} aligned "
        f"observations in {args.output_dir}."
    )


if __name__ == "__main__":
    main()

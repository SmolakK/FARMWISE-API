"""Run deterministic offline controls; do not use their values as evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import sys

from tqdm import tqdm

from evaluation.common import FIGURE_DIR, LOG_DIR, ensure_output_dirs, write_json, write_records
from evaluation.coverage_precheck import benchmark_coverage_precheck
from evaluation.cross_source_agreement import (
    compute_agreement_metrics,
    generate_synthetic_observations,
)
from evaluation.plots import generate_all_figures
from evaluation.quality_smoke import generate_quality_control_report
from evaluation.scaling import benchmark_scaling


def run_smoke(*, scaling_repeats=2, latency_scale=1.0, show_progress=False):
    """Regenerate explicitly labelled synthetic/offline control outputs."""
    ensure_output_dirs()
    progress = tqdm(
        total=6,
        desc="FARMWISE offline smoke controls",
        unit="stage",
        disable=not show_progress,
        dynamic_ncols=True,
        file=sys.stdout,
    )
    progress.set_postfix_str("simulated coverage", refresh=True)
    coverage = benchmark_coverage_precheck(
        latency_scale=latency_scale,
        show_progress=show_progress,
        progress_position=1,
        leave_progress=False,
    )
    write_records(coverage, LOG_DIR / "coverage_precheck.csv")
    progress.update(1)

    progress.set_postfix_str("controlled scaling workload", refresh=True)
    scaling = benchmark_scaling(
        repeats=scaling_repeats,
        show_progress=show_progress,
        progress_position=1,
        leave_progress=False,
    )
    write_records(scaling, LOG_DIR / "scaling.csv")
    progress.update(1)

    progress.set_postfix_str("synthetic agreement", refresh=True)
    observations = generate_synthetic_observations()
    metrics, differences = compute_agreement_metrics(observations)
    observations.to_csv(
        LOG_DIR / "cross_source_observations_synthetic.csv", index=False
    )
    metrics.to_csv(LOG_DIR / "cross_source_agreement.csv", index=False)
    differences.to_csv(LOG_DIR / "cross_source_differences.csv", index=False)
    progress.update(1)

    progress.set_postfix_str("control figures", refresh=True)
    figures = generate_all_figures()
    progress.update(1)
    progress.set_postfix_str("synthetic quality", refresh=True)
    write_json(
        generate_quality_control_report(),
        LOG_DIR / "quality_report_synthetic.json",
    )
    progress.update(1)
    progress.set_postfix_str("manifest", refresh=True)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "offline-smoke-test",
        "publication_warning": (
            "Coverage latency and cross-source observations are deterministic "
            "synthetic controls. Do not use these numbers as empirical results."
        ),
        "coverage_scenarios": len(coverage),
        "scaling_cases": len(scaling),
        "agreement_pairs": len(metrics),
        "figures": [
            path.relative_to(FIGURE_DIR.parent).as_posix() for path in figures
        ],
        "quality_reports": 1,
    }
    write_json(manifest, LOG_DIR / "manifest.json")
    progress.update(1)
    progress.close()
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scaling-repeats", type=int, default=2)
    parser.add_argument("--latency-scale", type=float, default=1.0)
    parser.add_argument("--no-progress", action="store_true")
    args = parser.parse_args(argv)
    manifest = run_smoke(
        scaling_repeats=args.scaling_repeats,
        latency_scale=args.latency_scale,
        show_progress=not args.no_progress,
    )
    print(
        f"Generated {manifest['coverage_scenarios']} offline controls, "
        f"{manifest['scaling_cases']} scaling cases, and "
        f"{manifest['agreement_pairs']} synthetic agreement pairs."
    )


if __name__ == "__main__":
    main()

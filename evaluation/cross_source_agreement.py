"""Quantify agreement between ERA5 and overlapping observational sources."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from evaluation.common import LOG_DIR, ensure_output_dirs


REQUIRED_COLUMNS = {"timestamp", "cell", "variable", "source", "value"}


def generate_synthetic_observations(
    *,
    seed=42,
    days=45,
    cells=8,
) -> pd.DataFrame:
    """Generate deterministic smoke-test data with known source deviations."""
    rng = np.random.default_rng(seed)
    timestamps = pd.date_range("2024-01-01", periods=days, freq="D")
    cell_names = [f"cell-{number:02d}" for number in range(cells)]
    source_parameters = {
        "ERA5": {
            "temperature": (0.25, 0.65),
            "precipitation": (0.08, 0.90),
        },
        "IMGW": {
            "temperature": (0.10, 0.40),
            "precipitation": (-0.03, 0.55),
        },
        "DWD": {
            "temperature": (-0.05, 0.35),
            "precipitation": (0.02, 0.50),
        },
        "GeoSphere": {
            "temperature": (0.05, 0.38),
            "precipitation": (-0.01, 0.52),
        },
    }
    records = []

    for day_index, timestamp in enumerate(timestamps):
        seasonal = 8 + 7 * np.sin(2 * np.pi * day_index / 365)
        for cell_index, cell in enumerate(cell_names):
            true_temperature = seasonal + cell_index * 0.18 + rng.normal(0, 0.2)
            true_precipitation = rng.gamma(shape=1.4, scale=2.3)
            truths = {
                "temperature": true_temperature,
                "precipitation": true_precipitation,
            }
            for source, variables in source_parameters.items():
                for variable, (bias, noise) in variables.items():
                    value = truths[variable] + bias + rng.normal(0, noise)
                    if variable == "precipitation":
                        value = max(0.0, value)
                    records.append(
                        {
                            "timestamp": timestamp,
                            "cell": cell,
                            "variable": variable,
                            "source": source,
                            "value": float(value),
                        }
                    )
    return pd.DataFrame(records)


def validate_observations(observations: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_COLUMNS.difference(observations.columns)
    if missing:
        raise ValueError(
            f"Agreement input is missing columns: {sorted(missing)}"
        )
    result = observations.loc[:, sorted(REQUIRED_COLUMNS)].copy()
    result["timestamp"] = pd.to_datetime(result["timestamp"])
    result["value"] = pd.to_numeric(result["value"], errors="raise")
    return result


def paired_differences(
    observations: pd.DataFrame,
    *,
    reference_source="ERA5",
) -> pd.DataFrame:
    """Align candidate sources to the reference by time, S2 cell, and variable."""
    observations = validate_observations(observations)
    keys = ["timestamp", "cell", "variable"]
    reference = observations[
        observations["source"] == reference_source
    ][keys + ["value"]].rename(columns={"value": "reference_value"})
    pairs = []

    for source in sorted(set(observations["source"]) - {reference_source}):
        candidate = observations[
            observations["source"] == source
        ][keys + ["value"]].rename(columns={"value": "candidate_value"})
        aligned = reference.merge(candidate, on=keys, how="inner")
        aligned["reference_source"] = reference_source
        aligned["candidate_source"] = source
        aligned["difference"] = (
            aligned["candidate_value"] - aligned["reference_value"]
        )
        pairs.append(aligned)
    if not pairs:
        return pd.DataFrame(
            columns=keys
            + [
                "reference_value",
                "candidate_value",
                "reference_source",
                "candidate_source",
                "difference",
            ]
        )
    return pd.concat(pairs, ignore_index=True)


def compute_agreement_metrics(
    observations: pd.DataFrame,
    *,
    reference_source="ERA5",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return pairwise metrics and aligned observation-level differences."""
    differences = paired_differences(
        observations, reference_source=reference_source
    )
    metrics = []
    for (variable, source), group in differences.groupby(
        ["variable", "candidate_source"], sort=True
    ):
        error = group["difference"]
        correlation = group["reference_value"].corr(group["candidate_value"])
        metrics.append(
            {
                "variable": variable,
                "reference_source": reference_source,
                "candidate_source": source,
                "pair": f"{reference_source} vs {source}",
                "n": len(group),
                "bias": float(error.mean()),
                "mae": float(error.abs().mean()),
                "rmse": float(np.sqrt(np.mean(np.square(error)))),
                "pearson_r": (
                    float(correlation) if pd.notna(correlation) else None
                ),
            }
        )
    return pd.DataFrame(metrics), differences


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        help="Canonical long CSV. Omit for deterministic smoke-test data.",
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=LOG_DIR / "cross_source_agreement.csv",
    )
    parser.add_argument(
        "--differences-output",
        type=Path,
        default=LOG_DIR / "cross_source_differences.csv",
    )
    parser.add_argument(
        "--reference-source",
        default="ERA5",
    )
    args = parser.parse_args(argv)
    ensure_output_dirs()
    observations = (
        pd.read_csv(args.input)
        if args.input
        else generate_synthetic_observations()
    )
    metrics, differences = compute_agreement_metrics(
        observations, reference_source=args.reference_source
    )
    metrics.to_csv(args.metrics_output, index=False)
    differences.to_csv(args.differences_output, index=False)
    print(
        f"Wrote {len(metrics)} source-variable comparisons to "
        f"{args.metrics_output}"
    )


if __name__ == "__main__":
    main()


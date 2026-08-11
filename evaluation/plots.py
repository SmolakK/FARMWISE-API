"""Generate publication-oriented figures from evaluation CSV logs."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from evaluation.common import FIGURE_DIR, LOG_DIR, ensure_output_dirs


SERIES_COLORS = ["#3366A3", "#D9822B", "#3A8F5C"]


def plot_coverage_precheck(data: pd.DataFrame, output: Path) -> Path:
    labels = data["scenario"].str.replace("-", "\n")
    positions = np.arange(len(data))
    fig, axis = plt.subplots(figsize=(10, 5.4), constrained_layout=True)
    axis.bar(
        positions,
        data["candidate_sources"],
        color="#D9DEE7",
        label="Candidate sources",
    )
    axis.bar(
        positions,
        data["dispatched_sources"],
        color=SERIES_COLORS[0],
        label="Dispatched sources",
    )
    axis.set_ylabel("Source requests")
    axis.set_xticks(positions, labels)
    axis.tick_params(axis="x", labelsize=8)
    axis.grid(axis="y", alpha=0.25)

    saved_axis = axis.twinx()
    saved_axis.plot(
        positions,
        data["wall_seconds_saved"] * 1000,
        color=SERIES_COLORS[1],
        marker="o",
        linewidth=2,
        label="Wall-clock saved",
    )
    saved_axis.set_ylabel("Wall-clock saved [ms]")
    handles, legend_labels = axis.get_legend_handles_labels()
    handles2, labels2 = saved_axis.get_legend_handles_labels()
    axis.legend(handles + handles2, legend_labels + labels2, loc="upper right")
    axis.set_title("Coverage pre-check avoids irrelevant source dispatches")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)
    return output


def plot_scaling(
    data: pd.DataFrame,
    output: Path,
    *,
    title="FARMWISE scaling behaviour",
) -> Path:
    fig, axes = plt.subplots(
        1, 2, figsize=(11, 4.8), sharex=True, constrained_layout=True
    )
    dimensions = ["S2 level", "Bounding-box area", "Factor count"]
    markers = ["o", "s", "^"]
    for color, marker, dimension in zip(
        SERIES_COLORS, markers, dimensions
    ):
        subset = data[data["dimension"] == dimension].sort_values(
            "normalized_scale"
        )
        axes[0].plot(
            subset["normalized_scale"],
            subset["latency_seconds"] * 1000,
            color=color,
            marker=marker,
            label=dimension,
        )
        if {
            "latency_p25_seconds",
            "latency_p75_seconds",
        }.issubset(subset.columns):
            axes[0].fill_between(
                subset["normalized_scale"],
                subset["latency_p25_seconds"] * 1000,
                subset["latency_p75_seconds"] * 1000,
                color=color,
                alpha=0.14,
            )
        axes[1].plot(
            subset["normalized_scale"],
            subset["peak_memory_mb"],
            color=color,
            marker=marker,
            label=dimension,
        )
        if {
            "peak_memory_p25_mb",
            "peak_memory_p75_mb",
        }.issubset(subset.columns):
            axes[1].fill_between(
                subset["normalized_scale"],
                subset["peak_memory_p25_mb"],
                subset["peak_memory_p75_mb"],
                color=color,
                alpha=0.14,
            )

    axes[0].set_ylabel("Median latency [ms]")
    axes[1].set_ylabel("Peak traced memory [MiB]")
    for axis, title in zip(axes, ("Latency", "Memory")):
        axis.set_title(title)
        axis.set_xlabel("Normalized input scale (minimum → maximum)")
        axis.grid(alpha=0.25)
    axes[0].legend()
    fig.suptitle(title)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)
    return output


def plot_agreement_scatter(data: pd.DataFrame, output: Path) -> Path:
    variables = sorted(data["variable"].unique())
    fig, axes = plt.subplots(
        1,
        len(variables),
        figsize=(5.5 * len(variables), 5),
        squeeze=False,
        constrained_layout=True,
    )
    for axis, variable in zip(axes[0], variables):
        subset = data[data["variable"] == variable]
        for color, (source, group) in zip(
            SERIES_COLORS,
            subset.groupby("candidate_source", sort=True),
        ):
            axis.scatter(
                group["reference_value"],
                group["candidate_value"],
                s=11,
                alpha=0.35,
                color=color,
                label=source,
            )
        minimum = min(
            subset["reference_value"].min(),
            subset["candidate_value"].min(),
        )
        maximum = max(
            subset["reference_value"].max(),
            subset["candidate_value"].max(),
        )
        axis.plot(
            [minimum, maximum],
            [minimum, maximum],
            color="#555555",
            linestyle="--",
            linewidth=1,
        )
        unit = "°C" if variable == "temperature" else "mm"
        axis.set_xlabel(f"ERA5 [{unit}]")
        axis.set_ylabel(f"Observational source [{unit}]")
        axis.set_title(variable.capitalize())
        axis.grid(alpha=0.2)
        axis.legend()
    fig.suptitle("Cell-day agreement with ERA5")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)
    return output


def plot_disagreement_distribution(data: pd.DataFrame, output: Path) -> Path:
    variables = sorted(data["variable"].unique())
    fig, axes = plt.subplots(
        1,
        len(variables),
        figsize=(5.5 * len(variables), 4.8),
        squeeze=False,
        constrained_layout=True,
    )
    for axis, variable in zip(axes[0], variables):
        subset = data[data["variable"] == variable]
        sources = sorted(subset["candidate_source"].unique())
        samples = [
            subset[subset["candidate_source"] == source]["difference"]
            for source in sources
        ]
        boxes = axis.boxplot(
            samples,
            tick_labels=sources,
            patch_artist=True,
            showfliers=False,
        )
        for patch, color in zip(boxes["boxes"], SERIES_COLORS):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
        axis.axhline(0, color="#555555", linestyle="--", linewidth=1)
        unit = "°C" if variable == "temperature" else "mm"
        axis.set_ylabel(f"Source − ERA5 [{unit}]")
        axis.set_title(variable.capitalize())
        axis.grid(axis="y", alpha=0.2)
    fig.suptitle("Cross-source disagreement distributions")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)
    return output


def generate_all_figures(
    *,
    coverage_path=LOG_DIR / "coverage_precheck.csv",
    scaling_path=LOG_DIR / "scaling_controlled.csv",
    controlled_scaling_path=None,
    differences_path=LOG_DIR / "cross_source_differences.csv",
    figure_dir=FIGURE_DIR,
) -> list[Path]:
    ensure_output_dirs()
    coverage = pd.read_csv(coverage_path)
    scaling = pd.read_csv(scaling_path)
    controlled_scaling = (
        pd.read_csv(controlled_scaling_path)
        if controlled_scaling_path is not None
        else None
    )
    differences = pd.read_csv(differences_path)
    paths = [
        plot_coverage_precheck(
            coverage, figure_dir / "coverage_precheck.png"
        ),
        plot_scaling(
            scaling,
            figure_dir / "scaling_behaviour.png",
            title=(
                "FARMWISE live end-to-end scaling"
                if controlled_scaling is not None
                else "FARMWISE controlled scaling"
            ),
        ),
        plot_agreement_scatter(
            differences, figure_dir / "cross_source_agreement.png"
        ),
        plot_disagreement_distribution(
            differences, figure_dir / "cross_source_disagreement.png"
        ),
    ]
    if controlled_scaling is not None:
        paths.insert(
            2,
            plot_scaling(
                controlled_scaling,
                figure_dir / "scaling_controlled.png",
                title="FARMWISE controlled algorithmic scaling",
            ),
        )
    return paths


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage", type=Path, default=LOG_DIR / "coverage_precheck.csv")
    parser.add_argument(
        "--scaling",
        type=Path,
        default=LOG_DIR / "scaling_controlled.csv",
    )
    parser.add_argument(
        "--differences",
        type=Path,
        default=LOG_DIR / "cross_source_differences.csv",
    )
    parser.add_argument("--figure-dir", type=Path, default=FIGURE_DIR)
    args = parser.parse_args(argv)
    paths = generate_all_figures(
        coverage_path=args.coverage,
        scaling_path=args.scaling,
        differences_path=args.differences,
        figure_dir=args.figure_dir,
    )
    print(f"Wrote {len(paths)} figures to {args.figure_dir}")


if __name__ == "__main__":
    main()


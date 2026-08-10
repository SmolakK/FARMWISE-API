"""Measure framework latency and peak memory as request complexity grows."""

from __future__ import annotations

import argparse
from pathlib import Path
from statistics import median
import sys
from time import perf_counter
import tracemalloc

import numpy as np
import pandas as pd
from tqdm import tqdm

from core.harmonization import harmonize_data
from core.utils.coordinates_to_cells import get_s2_cells
from evaluation.common import LOG_DIR, ensure_output_dirs, write_records


FACTOR_NAMES = [
    "Temperature [C]",
    "Precipitation [mm]",
    "Soil moisture",
    "Potential evaporation",
    "Groundwater depth",
    "Surface water quantity",
]


def measure_scaling_case(
    *,
    bounding_box,
    level,
    factor_count,
    repeats=2,
    days=3,
):
    """Measure S2 covering, frame construction, and two-source harmonization."""
    latencies = []
    peaks = []
    cell_count = 0

    for repeat in range(repeats):
        tracemalloc.start()
        started = perf_counter()
        cells = get_s2_cells(bounding_box, level)
        cell_count = len(cells)
        factors = FACTOR_NAMES[:factor_count]
        columns = pd.MultiIndex.from_tuples(
            [(factor, cell) for factor in factors for cell in cells],
            names=["factor", "cell"],
        )
        dates = pd.date_range("2024-01-01", periods=days, freq="D")
        rng = np.random.default_rng(10_000 + repeat)
        shape = (days, len(columns))
        frames = [
            (
                "synthetic.source.a",
                pd.DataFrame(rng.normal(size=shape), index=dates, columns=columns),
                tuple(factors),
            ),
            (
                "synthetic.source.b",
                pd.DataFrame(rng.normal(size=shape), index=dates, columns=columns),
                tuple(factors),
            ),
        ]
        harmonize_data(
            frames,
            source_weights={
                "synthetic.source.a": 1.0,
                "synthetic.source.b": 1.0,
            },
            data_type_methods={"default": "weighted_mean"},
        )
        latencies.append(perf_counter() - started)
        _current, peak = tracemalloc.get_traced_memory()
        peaks.append(peak / (1024 * 1024))
        tracemalloc.stop()

    north, south, east, west = bounding_box
    return {
        "level": level,
        "factor_count": factor_count,
        "bbox_area_degrees2": (north - south) * (east - west),
        "cell_count": cell_count,
        "value_count": days * cell_count * factor_count * 2,
        "latency_seconds": median(latencies),
        "peak_memory_mb": max(peaks),
    }


def benchmark_scaling(
    *,
    repeats=2,
    show_progress: bool = False,
    progress_position: int = 0,
    leave_progress: bool = True,
):
    """Run level, bounding-box-area, and factor-count scaling sweeps."""
    case_specs = []
    base_bbox = (51.25, 50.75, 17.35, 16.65)

    for level in range(6, 13):
        case_specs.append(
            (
                "S2 level",
                level,
                base_bbox,
                level,
                2,
            )
        )

    center_lat, center_lon = 51.0, 17.0
    for width in (0.25, 0.5, 1.0, 2.0, 3.0):
        bbox = (
            center_lat + width / 2,
            center_lat - width / 2,
            center_lon + width / 2,
            center_lon - width / 2,
        )
        case_specs.append(
            (
                "Bounding-box area",
                width * width,
                bbox,
                10,
                2,
            )
        )

    for factor_count in (1, 2, 3, 4, 6):
        case_specs.append(
            (
                "Factor count",
                factor_count,
                base_bbox,
                10,
                factor_count,
            )
        )

    records = []
    progress = tqdm(
        case_specs,
        desc="Scaling benchmark",
        unit="case",
        total=len(case_specs),
        disable=not show_progress,
        dynamic_ncols=True,
        file=sys.stdout,
        position=progress_position,
        leave=leave_progress,
    )
    for dimension, value, bounding_box, level, factor_count in progress:
        progress.set_postfix_str(
            f"{dimension}={value}, repeats={repeats}",
            refresh=False,
        )
        metrics = measure_scaling_case(
            bounding_box=bounding_box,
            level=level,
            factor_count=factor_count,
            repeats=repeats,
        )
        records.append(
            {
                "dimension": dimension,
                "input_value": value,
                **metrics,
            }
        )

    for dimension in {record["dimension"] for record in records}:
        dimension_records = [
            record for record in records if record["dimension"] == dimension
        ]
        values = [float(record["input_value"]) for record in dimension_records]
        low, high = min(values), max(values)
        for record in dimension_records:
            record["normalized_scale"] = (
                (float(record["input_value"]) - low) / (high - low)
                if high > low
                else 0
            )
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=LOG_DIR / "scaling.csv",
    )
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable the progress bar.",
    )
    args = parser.parse_args(argv)
    ensure_output_dirs()
    records = benchmark_scaling(
        repeats=args.repeats,
        show_progress=not args.no_progress,
    )
    write_records(records, args.output)
    print(f"Wrote {len(records)} scaling measurements to {args.output}")


if __name__ == "__main__":
    main()


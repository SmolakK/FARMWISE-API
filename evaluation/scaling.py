"""Measure controlled algorithmic scaling on a generated dense workload."""

from __future__ import annotations

import argparse
import gc
from pathlib import Path
from statistics import median
import sys
from time import perf_counter
import tracemalloc
import warnings

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


def _controlled_workload(
    *, bounding_box, level, factor_count, days, seed
):
    cells = get_s2_cells(bounding_box, level)
    factors = FACTOR_NAMES[:factor_count]
    columns = pd.MultiIndex.from_tuples(
        [(factor, cell) for factor in factors for cell in cells],
        names=["factor", "cell"],
    )
    dates = pd.date_range("2024-01-01", periods=days, freq="D")
    rng = np.random.default_rng(seed)
    shape = (days, len(columns))
    frames = [
        (
            "controlled.source.a",
            pd.DataFrame(rng.normal(size=shape), index=dates, columns=columns),
            tuple(factors),
        ),
        (
            "controlled.source.b",
            pd.DataFrame(rng.normal(size=shape), index=dates, columns=columns),
            tuple(factors),
        ),
    ]
    harmonize_data(
        frames,
        source_weights={
            "controlled.source.a": 1.0,
            "controlled.source.b": 1.0,
        },
        data_type_methods={"default": "weighted_mean"},
    )
    return len(cells), days * len(cells) * len(factors) * len(frames)


def measure_controlled_scaling_case(
    *,
    bounding_box,
    level,
    factor_count,
    repeats=2,
    days=3,
):
    """Measure one controlled, generated algorithmic scaling workload."""
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    if days < 1:
        raise ValueError("days must be at least 1")
    if not 1 <= factor_count <= len(FACTOR_NAMES):
        raise ValueError(
            f"factor_count must be between 1 and {len(FACTOR_NAMES)}"
        )

    latencies = []
    peaks = []
    cell_count = 0
    value_count = 0

    # Exercise S2, pandas, and harmonization once before tracing. Without this
    # warm-up, whichever case runs first absorbs one-time caches and reports a
    # misleadingly high memory peak.
    _controlled_workload(
        bounding_box=(51.01, 50.99, 10.01, 9.99),
        level=6,
        factor_count=1,
        days=1,
        seed=9_999,
    )

    for repeat in range(repeats):
        gc.collect()
        tracemalloc.start()
        started = perf_counter()
        cell_count, value_count = _controlled_workload(
            bounding_box=bounding_box,
            level=level,
            factor_count=factor_count,
            days=days,
            seed=10_000 + repeat,
        )
        latencies.append(perf_counter() - started)
        _current, peak = tracemalloc.get_traced_memory()
        peaks.append(peak / (1024 * 1024))
        tracemalloc.stop()

    north, south, east, west = bounding_box
    return {
        "measurement_mode": "controlled-generated-workload",
        "level": level,
        "factor_count": factor_count,
        "bbox_area_degrees2": (north - south) * (east - west),
        "cell_count": cell_count,
        "value_count": value_count,
        "latency_seconds": median(latencies),
        "peak_memory_mb": max(peaks),
    }


def measure_scaling_case(**kwargs):
    """Deprecated compatibility alias for the controlled benchmark."""
    warnings.warn(
        "measure_scaling_case is controlled, not live; use "
        "measure_controlled_scaling_case",
        DeprecationWarning,
        stacklevel=2,
    )
    return measure_controlled_scaling_case(**kwargs)


def benchmark_controlled_scaling(
    *,
    repeats=2,
    show_progress: bool = False,
    progress_position: int = 0,
    leave_progress: bool = True,
):
    """Run controlled level, area, and factor-count scaling sweeps."""
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
        desc="Controlled scaling",
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
        metrics = measure_controlled_scaling_case(
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


def benchmark_scaling(**kwargs):
    """Deprecated compatibility alias for the controlled scaling sweep."""
    warnings.warn(
        "benchmark_scaling is controlled, not live; use "
        "benchmark_controlled_scaling",
        DeprecationWarning,
        stacklevel=2,
    )
    return benchmark_controlled_scaling(**kwargs)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=LOG_DIR / "scaling_controlled.csv",
    )
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable the progress bar.",
    )
    args = parser.parse_args(argv)
    ensure_output_dirs()
    records = benchmark_controlled_scaling(
        repeats=args.repeats,
        show_progress=not args.no_progress,
    )
    write_records(records, args.output)
    print(f"Wrote {len(records)} scaling measurements to {args.output}")


if __name__ == "__main__":
    main()


"""Measure framework latency and peak memory as request complexity grows."""

from __future__ import annotations

import argparse
from pathlib import Path
from statistics import median
from time import perf_counter
import tracemalloc

import numpy as np
import pandas as pd

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


def benchmark_scaling(*, repeats=2):
    """Run level, bounding-box-area, and factor-count scaling sweeps."""
    cases = []
    base_bbox = (51.25, 50.75, 17.35, 16.65)

    for level in range(6, 13):
        cases.append(
            (
                "S2 level",
                level,
                measure_scaling_case(
                    bounding_box=base_bbox,
                    level=level,
                    factor_count=2,
                    repeats=repeats,
                ),
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
        cases.append(
            (
                "Bounding-box area",
                width * width,
                measure_scaling_case(
                    bounding_box=bbox,
                    level=10,
                    factor_count=2,
                    repeats=repeats,
                ),
            )
        )

    for factor_count in (1, 2, 3, 4, 6):
        cases.append(
            (
                "Factor count",
                factor_count,
                measure_scaling_case(
                    bounding_box=base_bbox,
                    level=10,
                    factor_count=factor_count,
                    repeats=repeats,
                ),
            )
        )

    records = []
    for dimension, value, metrics in cases:
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
    args = parser.parse_args(argv)
    ensure_output_dirs()
    records = benchmark_scaling(repeats=args.repeats)
    write_records(records, args.output)
    print(f"Wrote {len(records)} scaling measurements to {args.output}")


if __name__ == "__main__":
    main()


"""Generate a deterministic per-source quality-report control."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from core.quality_assess import assess_data_quality
from core.utils.coordinates_to_cells import get_s2_cells
from evaluation.common import LOG_DIR, ensure_output_dirs, write_json


def generate_quality_control_report():
    bbox = (51.10, 50.90, 17.10, 16.90)
    level = 8
    cells = get_s2_cells(bbox, level)
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    columns = pd.MultiIndex.from_tuples(
        [
            (factor, cell)
            for factor in ("Temperature [C]", "Precipitation [mm]")
            for cell in cells
        ],
        names=["factor", "cell"],
    )
    rng = np.random.default_rng(123)
    values = rng.normal(10, 2, size=(len(dates), len(columns)))
    frame = pd.DataFrame(values, index=dates, columns=columns)
    frame.iloc[1, 0] = np.nan
    frame.iloc[-1, 0] = 100
    precipitation_columns = frame.columns.get_level_values(0).str.contains(
        "Precipitation"
    )
    frame.loc[:, precipitation_columns] = frame.loc[
        :, precipitation_columns
    ].abs()

    report = assess_data_quality(
        frame,
        {
            "api_name": "synthetic_quality_source",
            "source": "evaluation.synthetic_quality_source",
            "columns": ["Temperature [C]", "Precipitation [mm]"],
        },
        (
            bbox,
            ("2024-01-01", "2024-01-05"),
            ["temperature", "precipitation"],
        ),
        {
            "bbox": bbox,
            "level": level,
            "time_from": "2024-01-01",
            "time_to": "2024-01-05",
            "factors": ["temperature", "precipitation"],
        },
    )
    report["evaluation_mode"] = "synthetic-control"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=LOG_DIR / "quality_report_synthetic.json",
    )
    args = parser.parse_args(argv)
    ensure_output_dirs()
    write_json(generate_quality_control_report(), args.output)
    print(f"Wrote quality control report to {args.output}")


if __name__ == "__main__":
    main()


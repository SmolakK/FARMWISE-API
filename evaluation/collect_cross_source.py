"""Collect live, separate-source FARMWISE output in canonical agreement format."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import re

import pandas as pd

from core.main_call import read_data
from evaluation.common import LOG_DIR, ensure_output_dirs


SOURCE_NAMES = {
    "cds_single_levels": "ERA5",
    "imgw_api_synop_daily": "IMGW",
    "wetterdienst_dwd": "DWD",
    "geosphere": "GeoSphere",
}


def separate_frame_to_observations(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert ``separate_api=True`` output to canonical long observations."""
    records = []
    for column in frame.columns:
        factor, cell = column
        match = re.match(r"^(.*) \(([^()]+)\)$", str(factor))
        if not match:
            continue
        physical_factor, adapter = match.groups()
        normalized = physical_factor.lower()
        if "temperature" in normalized:
            variable = "temperature"
        elif "precipitation" in normalized:
            variable = "precipitation"
        else:
            variable = physical_factor
        source = SOURCE_NAMES.get(adapter, adapter)
        for timestamp, value in frame[column].dropna().items():
            records.append(
                {
                    "timestamp": timestamp,
                    "cell": str(cell),
                    "variable": variable,
                    "source": source,
                    "value": value,
                }
            )
    return pd.DataFrame(records)


async def collect(args):
    result = await read_data(
        country=args.country,
        bounding_box=tuple(args.bounding_box) if args.bounding_box else None,
        level=args.level,
        time_from=args.time_from,
        time_to=args.time_to,
        factors=["temperature", "precipitation"],
        separate_api=True,
        persist_quality_reports=True,
    )
    if not isinstance(result, dict) or result["data"].empty:
        raise RuntimeError("No overlapping source data were returned.")
    observations = separate_frame_to_observations(result["data"])
    if observations.empty:
        raise RuntimeError("Returned columns could not be mapped to sources.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    observations.to_csv(args.output, index=False)
    print(f"Wrote {len(observations)} observations to {args.output}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    location = parser.add_mutually_exclusive_group(required=True)
    location.add_argument("--country")
    location.add_argument("--bounding-box", nargs=4, type=float)
    parser.add_argument("--level", type=int, default=10)
    parser.add_argument("--time-from", required=True)
    parser.add_argument("--time-to", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=LOG_DIR / "cross_source_observations_live.csv",
    )
    args = parser.parse_args(argv)
    ensure_output_dirs()
    asyncio.run(collect(args))


if __name__ == "__main__":
    main()


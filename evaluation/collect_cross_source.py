"""Collect live, separate-source FARMWISE output in canonical agreement format."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import re

import pandas as pd

from core.main_call import read_data
from evaluation.common import ensure_output_dirs
from core.utils.paths import CACHE_ROOT, PROJECT_ROOT


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


def validate_private_output(path: Path, observations: pd.DataFrame) -> None:
    """Prevent live IMGW rows from being written anywhere inside the repo."""
    if "IMGW" not in set(observations.get("source", [])):
        return
    try:
        path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return
    raise PermissionError(
        "Live IMGW observations must be written to a private path outside "
        "the repository (the default FARMWISE cache path is safe)."
    )


async def collect(args):
    result = await read_data(
        country=args.country,
        bounding_box=tuple(args.bounding_box) if args.bounding_box else None,
        level=args.level,
        time_from=args.time_from,
        time_to=args.time_to,
        factors=["temperature", "precipitation"],
        separate_api=True,
        assess_quality=True,
        persist_quality_reports=True,
    )
    if not isinstance(result, dict) or result["data"].empty:
        raise RuntimeError("No overlapping source data were returned.")
    observations = separate_frame_to_observations(result["data"])
    if observations.empty:
        raise RuntimeError("Returned columns could not be mapped to sources.")
    validate_private_output(args.output, observations)
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
        default=CACHE_ROOT / "evaluation" / "cross_source_observations_live.csv",
    )
    args = parser.parse_args(argv)
    ensure_output_dirs()
    asyncio.run(collect(args))


if __name__ == "__main__":
    main()


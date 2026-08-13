"""Collect live, separate-source FARMWISE output in canonical agreement format."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import re

import pandas as pd

from core.main_call import read_data
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


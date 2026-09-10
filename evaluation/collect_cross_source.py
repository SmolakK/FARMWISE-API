"""Collect live, separate-source FARMWISE output in canonical agreement format."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import re

import pandas as pd

from farmwise_api.core.main_call import read_data
from farmwise_api.core.utils.paths import PACKAGE_ROOT


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


def summarise_source_comparison(
    observations: pd.DataFrame,
    required_sources=(),
) -> dict:
    """Report whether a cross-source scenario produced comparable pairs."""
    observed_sources = sorted(set(observations.get("source", [])))
    required_sources = sorted(set(required_sources))
    missing_sources = sorted(set(required_sources) - set(observed_sources))
    comparison_sources = required_sources or observed_sources

    overlap_count = 0
    if len(comparison_sources) >= 2 and not observations.empty:
        selected = observations[
            observations["source"].isin(comparison_sources)
        ]
        sources_per_key = selected.groupby(
            ["timestamp", "cell", "variable"]
        )["source"].nunique()
        overlap_count = int(
            (sources_per_key >= len(comparison_sources)).sum()
        )

    return {
        "required_sources": required_sources,
        "observed_sources": observed_sources,
        "missing_sources": missing_sources,
        "overlapping_observation_keys": overlap_count,
        "comparison_ready": (
            len(comparison_sources) >= 2
            and not missing_sources
            and overlap_count > 0
        ),
    }


def validate_private_output(path: Path, observations: pd.DataFrame) -> None:
    """Prevent live IMGW rows from being written inside the Python package."""
    if "IMGW" not in set(observations.get("source", [])):
        return
    try:
        path.resolve().relative_to(PACKAGE_ROOT.resolve())
    except ValueError:
        return
    raise PermissionError(
        "Live IMGW observations must not be written inside the distributable "
        "farmwise_api package. Use the evaluation directory or a private "
        "path, retain attribution, and do not bundle the source dataset."
    )

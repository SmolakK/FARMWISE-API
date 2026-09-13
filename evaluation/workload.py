"""Workload descriptors recorded with every empirical run.

These turn a request and its result into the quantities the analysis relates
runtime and memory to: the geodesic area requested, the number of S2 cells
requested and returned, the number of values returned, the requested duration
and the per-source timings. They are computed outside the timed section.
"""

from __future__ import annotations

from datetime import date
import math

import pandas as pd
from s2sphere import LatLng, LatLngRect, RegionCoverer

# IUGG mean Earth radius. Areas use a spherical Earth; this is adequate for
# relating runtime to request size but is not an ellipsoidal area.
EARTH_RADIUS_KM = 6371.0088


def bbox_area_km2(bounding_box) -> float:
    """Spherical area of an (N, S, E, W) latitude-longitude box in km²."""
    north, south, east, west = map(float, bounding_box)
    return (
        EARTH_RADIUS_KM ** 2
        * abs(math.sin(math.radians(north)) - math.sin(math.radians(south)))
        * math.radians(abs(east - west))
    )


def bbox_dimensions_deg(bounding_box) -> dict:
    """Width and height of an (N, S, E, W) box in degrees (scenario metadata)."""
    north, south, east, west = map(float, bounding_box)
    return {"width_deg": abs(east - west), "height_deg": abs(north - south)}


def requested_s2_cell_count(bounding_box, level: int) -> int:
    """Number of S2 cells at ``level`` whose covering intersects the box.

    This is the spatial workload the request asks for, independent of how many
    cells a source actually has data for. ``max_cells`` is left unbounded so
    the covering is exact at the requested level.
    """
    north, south, east, west = map(float, bounding_box)
    rect = LatLngRect.from_point_pair(
        LatLng.from_degrees(south, west), LatLng.from_degrees(north, east)
    )
    coverer = RegionCoverer()
    coverer.min_level = level
    coverer.max_level = level
    coverer.max_cells = 2 ** 31 - 1
    return len(coverer.get_covering(rect))


def duration_days(time_from, time_to) -> int:
    """Inclusive number of calendar days in [time_from, time_to]."""
    start = date.fromisoformat(str(time_from)[:10])
    end = date.fromisoformat(str(time_to)[:10])
    return (end - start).days + 1


def request_workload(request: dict) -> dict:
    """Workload known before a request is executed."""
    bounding_box = request["bounding_box"]
    return {
        **bbox_dimensions_deg(bounding_box),
        "area_km2": bbox_area_km2(bounding_box),
        "requested_s2_cells": requested_s2_cell_count(
            bounding_box, request["level"]
        ),
        "duration_days": duration_days(request["time_from"], request["time_to"]),
        "requested_factors": len(request["factors"]),
    }


def result_workload(frame) -> dict:
    """Workload of a returned FARMWISE frame (columns: factor, S2 cell)."""
    if frame is None or getattr(frame, "empty", True):
        return {
            "returned_rows": 0,
            "returned_columns": 0,
            "returned_s2_cells": 0,
            "returned_factors": 0,
            "returned_values": 0,
        }
    columns = frame.columns
    if isinstance(columns, pd.MultiIndex):
        cells = columns.get_level_values(1).nunique()
        factors = columns.get_level_values(0).nunique()
    else:
        cells = factors = len(columns)
    return {
        "returned_rows": int(len(frame)),
        "returned_columns": int(len(columns)),
        "returned_s2_cells": int(cells),
        "returned_factors": int(factors),
        "returned_values": int(frame.count().sum()),
    }


def source_timings(dispatch) -> dict:
    """Per-source wall times and outcome counts from ``metadata['dispatch']``."""
    dispatch = dispatch or []
    statuses: dict[str, int] = {}
    for item in dispatch:
        status = item.get("status", "unknown")
        statuses[status] = statuses.get(status, 0) + 1
    seconds = [
        item["wall_seconds"] for item in dispatch
        if item.get("wall_seconds") is not None
    ]
    return {
        "source_wall_seconds": {
            item["source"]: item.get("wall_seconds") for item in dispatch
        },
        "source_status": {item["source"]: item.get("status") for item in dispatch},
        "dispatch_status_counts": statuses,
        "dispatch_seconds_sum": sum(seconds) if seconds else None,
        "dispatch_seconds_max": max(seconds) if seconds else None,
    }

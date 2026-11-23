"""CORINE Land Cover adapter using the EEA ArcGIS feature layers."""

from __future__ import annotations

import asyncio
import logging

from datetime import date, datetime, timedelta
from pyproj import Transformer
import httpx
import numpy as np
import pandas as pd
import s2sphere
import shapely
from shapely.geometry import Polygon, box, shape
from shapely.strtree import STRtree

from farmwise_api.core.utils.coordinates_to_cells import get_s2_cells

logger = logging.getLogger(__name__)

AVAILABLE_SNAPSHOTS = (1990, 2000, 2006, 2012, 2018)
CLASS_FIELDS = {
    1990: "Code_90",
    2000: "Code_00",
    2006: "Code_06",
    2012: "Code_12",
    2018: "Code_18",
}
OUTPUT_COLUMN = "CORINE land-cover class code"
# The EEA layers return at most 1000 features per page (a Europe-wide query
# asking for 2000 got 1000 and moved on to offset 1000), so ask for what is
# actually served.
PAGE_SIZE = 1000
# Pages requested at once. The polygon count is known up front, so pages are
# independent; more than a few at a time only loads the EEA server, which
# answers 500 when it is busy.
MAX_CONCURRENT_PAGES = 4
# The EEA ArcGIS server can answer 500 (or a 200 carrying an error body) for
# one page in the middle of a large query. Without a retry that single page
# discarded every page fetched before it and failed the whole source.
RETRY_STATUSES = frozenset({500, 502, 503, 504})
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 2.0
# A page that still fails after every attempt is split in two and each half
# retried, down to this many records: the server fails heavy pages (large or
# intricate polygons) more often than light ones.
MIN_SPLIT_PAGE = 125
# Polygons are simplified on the server to this fraction of the S2 cell edge
# (about 18 m at level 10). Some full-resolution pages are so heavy that the
# server answers 500 every time - a Slovakia box failed at offset 41000 on all
# attempts - and a 2x2 degree box took 44 s instead of 9 s. At this tolerance
# every cell of that box kept its dominant class (479 of 479).
SIMPLIFY_FRACTION = 0.002
# Average S2 cell edge at level 0, in degrees (it halves with each level).
_S2_LEVEL0_EDGE_DEGREES = 82.9


async def read_data(
    spatial_range,
    time_range,
    data_range,
    level,
    within_source_aggregation_methods=None,
) -> pd.DataFrame:
    """Return the dominant CORINE class in every intersecting S2 cell.

    CORINE is a categorical polygon dataset. The adapter therefore queries
    the feature layer and selects the class occupying the largest intersected
    area of each requested S2 cell. Each survey remains valid until the next
    available CORINE snapshot.
    """
    del data_range, within_source_aggregation_methods
    start = datetime.strptime(time_range[0], "%Y-%m-%d").date()
    end = datetime.strptime(time_range[1], "%Y-%m-%d").date()
    if start > end:
        raise ValueError("time_range start must not be after end")

    # Building the S2 cell polygons and matching them against the returned
    # features is CPU-bound shapely work (measured at ~4 s for a one-degree
    # box, and it grows with area). Run in the event loop it stalls every
    # other request in the process, so both steps go to a worker thread while
    # the HTTP calls stay asynchronous.
    cell_polygons = await asyncio.to_thread(_s2_cell_polygons, spatial_range, level)
    if not cell_polygons:
        return pd.DataFrame()
    cells = await asyncio.to_thread(_CellAreas, cell_polygons)
    frames = []
    async with httpx.AsyncClient(timeout=120) as client:
        for snapshot, period_start, period_end in _snapshot_periods(start, end):
            classes = await _dominant_classes_from_service(
                client, cells, snapshot, spatial_range, level
            )
            if not classes:
                continue
            index = pd.date_range(period_start, period_end, freq="D").date
            frame = pd.DataFrame(
                {
                    cell: [class_code] * len(index)
                    for cell, class_code in classes.items()
                },
                index=index,
            )
            frames.append(frame)

    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames).sort_index()
    result.index.name = "Timestamp"
    result.columns = pd.MultiIndex.from_product(
        [[OUTPUT_COLUMN], result.columns], names=[None, "S2CELL"]
    )
    return result


def _snapshot_periods(start: date, end: date):
    """Yield snapshots and the request period represented by each snapshot."""
    for position, snapshot in enumerate(AVAILABLE_SNAPSHOTS):
        next_snapshot = (
            date(AVAILABLE_SNAPSHOTS[position + 1], 1, 1)
            if position + 1 < len(AVAILABLE_SNAPSHOTS)
            else end + timedelta(days=1)
        )
        period_start = max(start, date(snapshot, 1, 1))
        period_end = min(end, next_snapshot - timedelta(days=1))
        if period_start <= period_end:
            yield snapshot, period_start, period_end


def _layer_url(snapshot):
    return (
        "https://image.discomap.eea.europa.eu/arcgis/rest/services/"
        f"Corine/CLC{snapshot}_WM/MapServer/0/query"
    )


def _simplification_tolerance(level):
    """Server-side simplification, in degrees, for cells of this S2 level."""
    edge = _S2_LEVEL0_EDGE_DEGREES / (2 ** level)
    return min(max(edge * SIMPLIFY_FRACTION, 1e-5), 0.01)


def _query_params(spatial_range):
    north, south, east, west = spatial_range
    return {
        "where": "1=1",
        "geometry": f"{west},{south},{east},{north}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
    }


class _RetryableError(Exception):
    """A failure the EEA server may not repeat: 5xx, timeouts, error bodies."""


async def _get_json(client, url, params):
    """One request, raising _RetryableError for what is worth retrying."""
    try:
        response = await client.get(url, params=params)
    except httpx.TransportError as error:  # timeouts, dropped connections
        raise _RetryableError(f"{type(error).__name__}: {error}") from error
    if response.status_code in RETRY_STATUSES:
        raise _RetryableError(f"HTTP {response.status_code}")
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        # ArcGIS reports its own failures as HTTP 200 with an error body.
        error = payload["error"]
        code = error.get("code") if isinstance(error, dict) else None
        if code in RETRY_STATUSES:
            raise _RetryableError(f"ArcGIS error {error}")
        raise RuntimeError(f"CORINE query failed: {error}")
    return payload


async def _get_json_with_retries(client, url, params, what):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return await _get_json(client, url, params)
        except _RetryableError as error:
            if attempt == MAX_ATTEMPTS:
                raise
            logger.info(
                "CORINE %s failed (%s); retrying (%d/%d)",
                what, error, attempt, MAX_ATTEMPTS - 1,
            )
            await asyncio.sleep(BACKOFF_SECONDS * attempt)


async def _count_features(client, url, base_params):
    payload = await _get_json_with_retries(
        client, url, {**base_params, "returnCountOnly": "true", "f": "json"},
        "feature count",
    )
    return int(payload.get("count", 0))


async def _fetch_page(client, url, base_params, field, tolerance, offset, size):
    """Features ``offset`` to ``offset + size``, splitting the page if needed."""
    params = {
        **base_params,
        "outSR": "4326",
        "outFields": field,
        "returnGeometry": "true",
        # Offsets are only stable with a fixed order.
        "orderByFields": "OBJECTID",
        "resultOffset": offset,
        "resultRecordCount": size,
        "maxAllowableOffset": tolerance,
        "geometryPrecision": 5,
        "f": "geojson",
    }
    try:
        payload = await _get_json_with_retries(
            client, url, params, f"page at offset {offset}"
        )
    except _RetryableError as error:
        if size <= MIN_SPLIT_PAGE:
            raise RuntimeError(
                f"CORINE page at offset {offset} ({size} records) still failed "
                f"after {MAX_ATTEMPTS} attempts: {error}"
            ) from error
        half = size // 2
        logger.info(
            "CORINE page at offset %s kept failing; splitting it in two", offset
        )
        first = await _fetch_page(
            client, url, base_params, field, tolerance, offset, half
        )
        second = await _fetch_page(
            client, url, base_params, field, tolerance, offset + half, size - half
        )
        return first + second
    return payload.get("features", [])


async def _dominant_classes_from_service(client, cells, snapshot, spatial_range, level):
    """Dominant class per cell for one snapshot, page by page.

    A Europe-wide box intersects 2.4 million CORINE polygons (about 2,400
    pages). Each page is reduced to per-cell class areas as it arrives, so
    neither the polygons nor the JSON are held for the whole query.
    """
    url = _layer_url(snapshot)
    field = CLASS_FIELDS[snapshot]
    base_params = _query_params(spatial_range)
    count = await _count_features(client, url, base_params)
    if count == 0:
        return {}
    pages = range(0, count, PAGE_SIZE)
    logger.info("CORINE %s: %d polygons in %d pages", snapshot, count, len(pages))
    tolerance = _simplification_tolerance(level)
    limit = asyncio.Semaphore(MAX_CONCURRENT_PAGES)
    partials = []

    async def _page(offset):
        async with limit:
            features = await _fetch_page(
                client, url, base_params, field, tolerance,
                offset, min(PAGE_SIZE, count - offset),
            )
        partials.append(await asyncio.to_thread(cells.measure, features, field))

    # A TaskGroup cancels the remaining pages as soon as one fails for good.
    try:
        async with asyncio.TaskGroup() as group:
            for offset in pages:
                group.create_task(_page(offset))
    except ExceptionGroup as failed:
        # Report the page's own error, not "unhandled errors in a TaskGroup".
        raise failed.exceptions[0] from None
    return cells.dominant(partials)


def _s2_cell_polygons(spatial_range, level):
    north, south, east, west = spatial_range
    requested_area = box(west, south, east, north)
    polygons = {}
    for cell_id in get_s2_cells(spatial_range, level):
        cell = s2sphere.Cell(cell_id)
        vertices = []
        for index in range(4):
            coordinate = s2sphere.LatLng.from_point(cell.get_vertex(index))
            vertices.append(
                (coordinate.lng().degrees, coordinate.lat().degrees)
            )
        clipped = Polygon(vertices).intersection(requested_area)
        if not clipped.is_empty:
            polygons[cell_id] = clipped
    return polygons


def _project(geometries):
    """WGS84 longitude/latitude to ETRS89 / LAEA Europe (EPSG:3035).

    An equal-area CRS suited to CORINE's European coverage, so intersection
    areas are comparable. A transformer per call: pages are measured in
    several threads at once.
    """
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)

    def _xy(coordinates):
        x, y = transformer.transform(coordinates[:, 0], coordinates[:, 1])
        return np.column_stack([x, y])

    array = np.empty(len(geometries), dtype=object)
    array[:] = list(geometries)
    return shapely.transform(array, _xy)


class _CellAreas:
    """S2 cell polygons, projected and indexed, to measure CORINE pages against."""

    def __init__(self, cell_polygons):
        self.cell_ids = list(cell_polygons)
        self.cells = _project(list(cell_polygons.values()))
        # Spatial index avoids testing every polygon against every cell.
        self.tree = STRtree(self.cells)

    def measure(self, features, field):
        """Intersected area per (cell position, class code) for one page."""
        field = field.casefold()
        polygons, codes = [], []
        for feature in features:
            geometry = feature.get("geometry")
            if not geometry:
                continue
            properties = feature.get("properties", {})
            class_code = next(
                (
                    value
                    for key, value in properties.items()
                    if key.casefold() == field
                ),
                None,
            )
            if class_code is None:
                continue
            try:
                class_code = int(class_code)
            except (TypeError, ValueError):
                continue
            polygon = shape(geometry)
            if polygon.is_empty:
                continue
            polygons.append(polygon)
            codes.append(class_code)
        if not polygons:
            return pd.Series(dtype=float)

        projected = _project(polygons)
        # Server-side simplification can leave a ring self-intersecting.
        invalid = ~shapely.is_valid(projected)
        if invalid.any():
            projected[invalid] = shapely.make_valid(projected[invalid])
        feature_index, cell_index = self.tree.query(projected, predicate="intersects")
        intersections = shapely.intersection(
            projected[feature_index], self.cells[cell_index]
        )
        kept = ~shapely.is_empty(intersections)
        frame = pd.DataFrame(
            {
                "cell": cell_index[kept],
                "code": np.asarray(codes)[feature_index[kept]],
                "area": shapely.area(intersections[kept]),
            }
        )
        return frame.groupby(["cell", "code"])["area"].sum()

    def dominant(self, partials):
        """The class with the largest total area in each cell."""
        partials = [partial for partial in partials if not partial.empty]
        if not partials:
            return {}
        totals = (
            pd.concat(partials).groupby(level=[0, 1]).sum()
            .rename_axis(["cell", "code"]).rename("area").reset_index()
            # Smallest class code wins an exact area tie, making the result
            # deterministic rather than dependent on feature order.
            .sort_values(["cell", "area", "code"], ascending=[True, False, True])
            .drop_duplicates("cell")
            .sort_values("cell")
        )
        return {
            self.cell_ids[cell]: int(code)
            for cell, code in zip(totals["cell"], totals["code"])
        }


__all__ = ["OUTPUT_COLUMN", "read_data"]

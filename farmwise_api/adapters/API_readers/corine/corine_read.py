"""CORINE Land Cover adapter using the EEA ArcGIS feature layers."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from collections import defaultdict
from pyproj import Transformer
import httpx
import pandas as pd
import s2sphere
from shapely.geometry import Polygon, box, shape
from shapely.ops import transform
from shapely.strtree import STRtree

from farmwise_api.core.utils.coordinates_to_cells import get_s2_cells


AVAILABLE_SNAPSHOTS = (1990, 2000, 2006, 2012, 2018)
CLASS_FIELDS = {
    1990: "Code_90",
    2000: "Code_00",
    2006: "Code_06",
    2012: "Code_12",
    2018: "Code_18",
}
OUTPUT_COLUMN = "CORINE land-cover class code"
PAGE_SIZE = 2000


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

    cell_polygons = _s2_cell_polygons(spatial_range, level)
    frames = []
    async with httpx.AsyncClient(timeout=120) as client:
        for snapshot, period_start, period_end in _snapshot_periods(start, end):
            features = await _fetch_features(client, snapshot, spatial_range)
            classes = _dominant_classes(cell_polygons, features, snapshot)
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


async def _fetch_features(client, snapshot, spatial_range):
    north, south, east, west = spatial_range
    url = (
        "https://image.discomap.eea.europa.eu/arcgis/rest/services/"
        f"Corine/CLC{snapshot}_WM/MapServer/0/query"
    )
    features = []
    offset = 0
    while True:
        response = await client.get(
            url,
            params={
                "where": "1=1",
                "geometry": f"{west},{south},{east},{north}",
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "outSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": CLASS_FIELDS[snapshot],
                "returnGeometry": "true",
                "resultOffset": offset,
                "resultRecordCount": PAGE_SIZE,
                "f": "geojson",
            },
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError(
                f"CORINE {snapshot} query failed: {payload['error']}"
            )
        page = payload.get("features", [])
        features.extend(page)
        if not payload.get("exceededTransferLimit", False):
            break
        offset += len(page)
    return features

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



def _dominant_classes(cell_polygons, features, snapshot):
    """Return the dominant CORINE class for each S2 cell.

    Dominance is defined by the largest intersecting area. Areas are
    calculated in ETRS89 / LAEA Europe (EPSG:3035), an equal-area CRS
    suitable for CORINE's European coverage.
    """
    field = CLASS_FIELDS[snapshot].casefold()

    # CORINE features and S2 polygons arrive in WGS84 longitude/latitude.
    # Project them before calculating areas.
    transformer = Transformer.from_crs(
        "EPSG:4326",
        "EPSG:3035",
        always_xy=True,
    )
    feature_polygons = []
    class_codes = []
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
        polygon = transform(transformer.transform, polygon)
        feature_polygons.append(polygon)
        class_codes.append(class_code)
    if not feature_polygons:
        return {}
    # Spatial index avoids testing every cell against every CORINE polygon.
    tree = STRtree(feature_polygons)
    result = {}
    for cell_id, cell_polygon in cell_polygons.items():
        if cell_polygon.is_empty:
            continue
        projected_cell = transform(
            transformer.transform,
            cell_polygon,
        )
        areas = defaultdict(float)
        # Shapely 2.x returns indices into feature_polygons.
        candidate_indices = tree.query(
            projected_cell,
            predicate="intersects",
        )
        for index in candidate_indices:
            feature_polygon = feature_polygons[index]
            intersection = projected_cell.intersection(feature_polygon)
            if intersection.is_empty:
                continue
            areas[class_codes[index]] += intersection.area
        if areas:
            # Smallest class code wins an exact area tie, making the result
            # deterministic rather than dependent on feature order.
            result[cell_id] = max(
                areas.items(),
                key=lambda item: (item[1], -item[0]),
            )[0]
    return result


__all__ = ["OUTPUT_COLUMN", "read_data"]

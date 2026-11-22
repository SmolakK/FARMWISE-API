import s2sphere
import logging

import numpy as np
from s2sphere import sphere as _s2

logger = logging.getLogger(__name__)

_MAX_LEVEL = s2sphere.CellId.MAX_LEVEL
_MAX_SIZE = s2sphere.CellId.MAX_SIZE
_LOOKUP_BITS = _s2.LOOKUP_BITS
_LOOKUP_POS = np.asarray(_s2.LOOKUP_POS, dtype=np.uint64)
_ORIENTATION_MASK = np.uint64(_s2.SWAP_MASK | _s2.INVERT_MASK)


def s2_cell_ids(lat, lon, level: int) -> np.ndarray:
    """S2 cell ids at ``level`` for arrays of coordinates in degrees.

    The same result as ``s2sphere.CellId.from_lat_lng(LatLng.from_degrees(
    lat, lon)).parent(level).id()`` for each point, computed for the whole
    array at once. Calling s2sphere per row took about 20 microseconds a
    point, so a Europe-wide parcel layer (46 million points) spent most of an
    hour there. Returns a uint64 array.
    """
    if not 0 <= level <= _MAX_LEVEL:
        raise ValueError(f"S2 level must be between 0 and {_MAX_LEVEL}, got {level}")
    phi = np.radians(np.asarray(lat, dtype=np.float64))
    theta = np.radians(np.asarray(lon, dtype=np.float64))
    cos_phi = np.cos(phi)
    x = np.cos(theta) * cos_phi
    y = np.sin(theta) * cos_phi
    z = np.sin(phi)

    # Face: the axis of the largest component, +3 when it is negative.
    ax, ay, az = np.abs(x), np.abs(y), np.abs(z)
    axis = np.where(ax > ay, np.where(ax > az, 0, 2), np.where(ay > az, 1, 2))
    major = np.choose(axis, (x, y, z))
    face = axis + np.where(major < 0, 3, 0)

    with np.errstate(divide="ignore", invalid="ignore"):
        u = np.select(
            [face == 0, face == 1, face == 2, face == 3, face == 4],
            [y / x, -x / y, -x / z, z / x, z / y],
            -y / z,
        )
        v = np.select(
            [face == 0, face == 1, face == 2, face == 3, face == 4],
            [z / x, z / y, -y / z, y / x, -x / y],
            -x / z,
        )

    def _uv_to_ij(t):
        # Quadratic projection, as s2sphere's default.
        st = np.where(
            t >= 0,
            0.5 * np.sqrt(1 + 3 * np.maximum(t, 0)),
            1 - 0.5 * np.sqrt(1 - 3 * np.minimum(t, 0)),
        )
        return np.clip(np.floor(_MAX_SIZE * st), 0, _MAX_SIZE - 1).astype(np.uint64)

    i = _uv_to_ij(u)
    j = _uv_to_ij(v)

    face = face.astype(np.uint64)
    n = face << np.uint64(s2sphere.CellId.POS_BITS - 1)
    bits = face & np.uint64(_s2.SWAP_MASK)
    mask = np.uint64((1 << _LOOKUP_BITS) - 1)
    for k in range(7, -1, -1):
        shift = np.uint64(k * _LOOKUP_BITS)
        bits = bits + (((i >> shift) & mask) << np.uint64(_LOOKUP_BITS + 2))
        bits = bits + (((j >> shift) & mask) << np.uint64(2))
        bits = _LOOKUP_POS[bits]
        n = n | ((bits >> np.uint64(2)) << np.uint64(k * 2 * _LOOKUP_BITS))
        bits = bits & _ORIENTATION_MASK
    leaf = n * np.uint64(2) + np.uint64(1)

    lsb = np.uint64(1 << (2 * (_MAX_LEVEL - level)))
    return (leaf & ~(lsb - np.uint64(1))) | lsb


def s2_cells(lat, lon, level: int) -> np.ndarray:
    """``s2sphere.CellId`` objects for arrays of coordinates (object array).

    One object per distinct cell, shared by every point in it, so a large
    point set does not build one Python object per point.
    """
    ids = s2_cell_ids(lat, lon, level)
    unique, inverse = np.unique(ids, return_inverse=True)
    cells = np.empty(len(unique), dtype=object)
    cells[:] = [s2sphere.CellId(int(cell_id)) for cell_id in unique]
    return cells[inverse.reshape(-1)]


def _limit_coordinates(spatial_range, coordinates):
    """
    Limit the coordinates DataFrame to those falling within the specified spatial range.

    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param coordinates: DataFrame containing latitude and longitude coordinates.
    :return: DataFrame containing coordinates within the specified spatial range.
    """
    n, s, e, w = spatial_range
    coordinates = coordinates[(coordinates.lat <= n) & (coordinates.lat >= s) &
                              (coordinates.lon <= e) & (coordinates.lon >= w)]
    return coordinates


def prepare_coordinates(coordinates, spatial_range, level):
    """
    Prepare coordinates for data retrieval, limiting them to the specified spatial range and assigning S2Cell IDs.

    :param coordinates: Coordinates to be transformed
    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param level: S2Cell level.
    :return: DataFrame containing coordinates within the specified spatial range and their corresponding S2Cell IDs.
    """
    coords = coordinates.copy()  # to prevent the warning about the copy-setting
    coords.lat = coords.lat.astype('float32')
    coords.lon = coords.lon.astype('float32')
    coords = _limit_coordinates(spatial_range=spatial_range, coordinates=coords)
    if coords.size == 0:
        logger.info("No data in the range")
        return None
    coords['S2CELL'] = s2_cells(coords.lat.to_numpy(), coords.lon.to_numpy(), level)
    return coords


from s2sphere import RegionCoverer, LatLngRect, LatLng


def get_s2_cells(bbox, level):
    """
    Generate S2 cell ids that intersect a bounding box at a given S2 level.

    Parameters
    ----------
    bbox : tuple
        (N, S, E, W) in decimal degrees
    level : int
        S2 cell level, typically 8–14 for environmental data

    Returns
    -------
    list
        List of S2 cell IDs as strings (token form)
    """

    north, south, east, west = bbox

    # Create LatLngRect for S2
    rect = LatLngRect.from_point_pair(
        LatLng.from_degrees(south, west),
        LatLng.from_degrees(north, east)
    )

    # Configure coverer
    coverer = RegionCoverer()
    coverer.min_level = level
    coverer.max_level = level
    coverer.max_cells = 20000  # safety limit, adjust if needed

    # Get covering S2 cells
    covering = coverer.get_covering(rect)

    return covering

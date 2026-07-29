import s2sphere


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
        print("No data in the range")
        return None
    coords['S2CELL'] = coords.apply(lambda x:
                                    s2sphere.CellId.from_lat_lng(
                                        s2sphere.LatLng.from_degrees(x.lat, x.lon)).parent(level),
                                    axis=1)
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

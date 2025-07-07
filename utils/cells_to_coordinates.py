import s2sphere


def _s2cell_id_to_coordinate(s2cell_id):
    """
    Convert an S2Cell ID to the coordinates of its center.

    :param s2cell_id: The S2Cell ID to convert.
    :return: A tuple containing the latitude and longitude of the center of the S2Cell.
    """
    cell_center = s2cell_id.to_lat_lng()
    return cell_center.lat().degrees, cell_center.lng().degrees


def s2cells_to_coordinates(pivoted_table):
    """
    Convert S2Cell IDs in a pivoted DataFrame to latitude and longitude coordinates.

    :param pivoted_table: A pandas DataFrame with S2Cell IDs as index levels and data as columns.
    :return: A DataFrame with latitude and longitude columns added based on the S2Cell IDs.
    """

    # Extract S2Cell IDs from the index
    s2cells = pivoted_table.index.get_level_values(1)

    # Convert S2Cell IDs to coordinates using _s2cell_id_to_coordinate function
    s2_coordinates = [_s2cell_id_to_coordinate(x) for x in s2cells]

    # Add latitude and longitude columns to the transposed DataFrame
    pivoted_table[['lat', 'lon']] = s2_coordinates

    return pivoted_table


def extract_bbox(cells_list):
    """
    Extract the bounding box (in North, South, East, West order) from a list of S2 cell objects.

    The function calculates the minimum and maximum latitude and longitude based on the
    centers of the provided S2 cells and returns the bounding box.

    Parameters:
    ----------
    cells_list : list of s2sphere.CellId
        A list of S2 cell objects from which the bounding box is to be extracted.

    Returns:
    -------
    dict
        A dictionary representing the bounding box with keys:
        - 'N': northernmost latitude (maximum latitude)
        - 'S': southernmost latitude (minimum latitude)
        - 'E': easternmost longitude (maximum longitude)
        - 'W': westernmost longitude (minimum longitude)

    Notes:
    -----
    This function uses the centers of the S2 cells. If you need a more accurate bounding box,
    consider using the vertices of each cell instead of the centers.
    """
    api_coors = [x.to_lat_lng() for x in cells_list]
    api_lats = [x.lat().degrees for x in api_coors]
    api_lons = [x.lng().degrees for x in api_coors]
    max_lat = max(api_lats)
    min_lat = min(api_lats)
    max_lng = max(api_lons)
    min_lng = min(api_lons)
    bbox = {
        "N": max_lat,
        "S": min_lat,
        "E": max_lng,
        "W": min_lng
    }
    return bbox
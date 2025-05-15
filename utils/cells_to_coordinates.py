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

import pandas as pd
import s2sphere
import numpy as np
from scipy.interpolate import griddata
import math
from tqdm import tqdm


def mean_cell_size(lvl):
    """
    Calculates the average surface area of a single S2 cell at a specified level.

    The function computes the average cell size for S2 levels ranging from 0 to 30,
    based on the total surface area of the Earth. It returns the average cell area
    for the specified S2 level.

    :param lvl: An integer representing the S2 level (must be between 0 and 30).
    :return: The average surface area of an S2 cell at the specified level in km².
             Raises a ValueError if the level is out of bounds (not between 0 and 30).
    """

    # Total surface area of Earth in km²
    earth_surface_area_km2 = 510.1e6

    # Dictionary to store the S2 levels and their average cell sizes in km²
    s2_level_to_area_km2 = {}

    # Calculate average area of S2 cells at each level
    for level in range(0, 31):  # S2 levels from 0 to 30
        num_cells = 6 * 4 ** level
        avg_cell_area_km2 = earth_surface_area_km2 / num_cells
        s2_level_to_area_km2[level] = avg_cell_area_km2
    return s2_level_to_area_km2[lvl]


def haversine(lat1, lon1, lat2, lon2):
    """
    Calculates the great-circle distance between two points on the Earth specified by their latitude and longitude.

    This function uses the Haversine formula to compute the shortest distance over the earth's surface,
    giving an approximation of the distance in kilometers.

    :param lat1: Latitude of the first point in degrees.
    :param lon1: Longitude of the first point in degrees.
    :param lat2: Latitude of the second point in degrees.
    :param lon2: Longitude of the second point in degrees.
    :return: The distance between the two points in kilometers.
    """
    R = 6371.0  # Earth radius in kilometers

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = R * c
    return distance


def bounding_box_area(north, south, east, west):
    """
    Calculates the approximate area of a bounding box defined by its northernmost, southernmost,
    easternmost, and westernmost points using the Haversine formula.

    This function computes the area as a rectangle on the Earth's surface, taking into account
    the curvature of the Earth by calculating distances at the midpoint latitude.

    :param north: Latitude of the northernmost point in degrees.
    :param south: Latitude of the southernmost point in degrees.
    :param east: Longitude of the easternmost point in degrees.
    :param west: Longitude of the westernmost point in degrees.
    :return: The approximate area of the bounding box in square kilometers.
    """
    # Calculate the distance between the northernmost and southernmost points (latitude distance)
    lat_distance = haversine(north, west, south, west)

    # Calculate the distance between the easternmost and westernmost points (longitude distance) at the midpoint
    # latitude
    mid_lat = (north + south) / 2
    lon_distance = haversine(mid_lat, west, mid_lat, east)

    # Calculate the area (approximation as a rectangle on the Earth's surface)
    area = lat_distance * lon_distance
    return area


def how_many(N, S, E, W, level):
    area = bounding_box_area(N, S, E, W)
    how_many_cells = math.ceil(area / mean_cell_size(lvl=level)) * 2
    how_many_cells = int(math.ceil(math.sqrt(how_many_cells)))
    return how_many_cells


def interpolate(df_data, spatal_range, level):
    """
    Interpolates data from a DataFrame over a specified spatial range using S2 cells at a given level.

    This function computes the bounding box area and generates a finer grid of S2 cells
    within the defined spatial range. It then interpolates the input data (e.g., ERA5 data)
    to these finer S2 cell coordinates.

    :param df_data: A pandas DataFrame containing data with 'lat' and 'lon' columns for latitude
                    and longitude, and additional columns for the data to be interpolated.
    :param spatal_range: A tuple (N, S, E, W) defining the bounding box for interpolation:
                         - N: Northern latitude limit
                         - S: Southern latitude limit
                         - E: Eastern longitude limit
                         - W: Western longitude limit
    :param level: An integer representing the S2 level to use for the grid cells.
    :return: A pandas DataFrame containing the interpolated data at the finer S2 cell grid.
    """
    print("INTERPOLATING")
    N, S, E, W = spatal_range
    how_many_cells = how_many(N,S,E,W, level)

    s2_cells = []
    s2_cell_centers = []
    latitudes = np.linspace(S, N, how_many_cells)
    longitudes = np.linspace(W, E, how_many_cells)

    for lat in tqdm(latitudes, total=len(latitudes)):
        for lon in longitudes:
            lat_lng = s2sphere.LatLng.from_degrees(lat, lon)
            cell = s2sphere.CellId.from_lat_lng(lat_lng).parent(level)
            cell_lat_lng = cell.to_lat_lng()
            cell_lat = cell_lat_lng.lat().degrees
            cell_lng = cell_lat_lng.lng().degrees
            if cell not in s2_cells and S <= cell_lat <= N and W <= cell_lng <= E:
                s2_cells.append(cell)
                s2_cell_centers.append([cell_lat, cell_lng])

    s2_cell_centers = np.array(s2_cell_centers)
    fine_lat = s2_cell_centers[:, 0]
    fine_lon = s2_cell_centers[:, 1]

    # Interpolate ERA5 data to the finer S2 cell grid
    columns_to = [x for x in df_data.columns if x != 'lat' and x != 'lon']
    interpolated_data = {}
    for colname in columns_to:
        to_concat = {}
        for day, values in df_data.groupby(level=1):
            finer_grid = griddata(
                (values.lon, values.lat), values[colname],
                (fine_lon, fine_lat),  # S2 cell coordinates
                method='linear'  # Interpolation method: 'linear', 'nearest', or 'cubic'
            )
            to_concat[day] = pd.DataFrame(finer_grid, index=s2_cells)
        interpolated_data[colname] = pd.concat(to_concat)
    interpolated_data = pd.concat(interpolated_data, axis=1).swaplevel().droplevel(1, axis=1)
    return interpolated_data

import pandas as pd
import s2sphere
import numpy as np
from scipy.interpolate import griddata
import math
from tqdm import tqdm

def mean_cell_size(lvl):
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

# Function to calculate the distance between two latitude/longitude points using the Haversine formula
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0  # Earth radius in kilometers

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = R * c
    return distance


# Function to calculate the area of a bounding box in km²
def bounding_box_area(north, south, east, west):
    # Calculate the distance between the northernmost and southernmost points (latitude distance)
    lat_distance = haversine(north, west, south, west)

    # Calculate the distance between the easternmost and westernmost points (longitude distance) at the midpoint latitude
    mid_lat = (north + south) / 2
    lon_distance = haversine(mid_lat, west, mid_lat, east)

    # Calculate the area (approximation as a rectangle on the Earth's surface)
    area = lat_distance * lon_distance
    return area


def interpolate(df_data, spatal_range, level):
    print("INTERPOLATING")
    N, S, E, W = spatal_range
    area = bounding_box_area(N, S, E, W)
    how_many_cells = math.ceil(area/mean_cell_size(lvl=level))*2
    how_many_cells = int(math.ceil(math.sqrt(how_many_cells)))

    s2_cells = []
    s2_cell_centers = []
    latitudes = np.linspace(S, N, how_many_cells)
    longitudes = np.linspace(W, E, how_many_cells)

    for lat in tqdm(latitudes,total=len(latitudes)):
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
            to_concat[day] = pd.DataFrame(finer_grid,index=s2_cells)
        interpolated_data[colname] = pd.concat(to_concat)
    interpolated_data = pd.concat(interpolated_data,axis=1).swaplevel().droplevel(1,axis=1)
    return interpolated_data

import s2sphere
import geopandas as gpd
from shapely.geometry import Polygon
import matplotlib.pyplot as plt


def generate_s2cell_polygons(bounding_box, cell_level, save_path=None):
    """
     Generates S2 cell polygons for a specified bounding box and cell level.

     This function uses the S2 geometry library to cover a bounding box with S2 cells
     at the specified level. It creates polygons for each cell and stores them in a GeoDataFrame.

     :param bounding_box: A tuple (west, south, east, north) defining the bounding box in degrees.
                          - west: Western longitude limit
                          - south: Southern latitude limit
                          - east: Eastern longitude limit
                          - north: Northern latitude limit
     :param cell_level: An integer representing the S2 cell level to use for the polygons.
     :param save_path: A path where generated polygons of the S2 cells will be stored. If not given, data not stored.
     :return: A GeoDataFrame containing the polygons of the S2 cells at the specified level.
     """
    west, south, east, north = bounding_box
    coverer = s2sphere.RegionCoverer()
    coverer.min_level = cell_level
    coverer.max_level = cell_level
    coverer.max_cells = 1000
    earth = s2sphere.LatLngRect(
        s2sphere.LatLng.from_degrees(south, west),
        s2sphere.LatLng.from_degrees(north, east)
    )
    covering = coverer.get_covering(earth)

    # Generate polygons for each cell
    polygons = []
    for cell_id in covering:
        cell = s2sphere.Cell(cell_id)
        vertices = []
        for i in range(4):
            vertex = s2sphere.LatLng.from_point(cell.get_vertex(i))
            vertices.append(
                (vertex.lng().degrees, vertex.lat().degrees))  # Reversed lat-lng to lng-lat for GeoDataFrame
        polygons.append(Polygon(vertices))

    # Create GeoDataFrame
    gdf = gpd.GeoDataFrame(geometry=polygons, crs='EPSG:4326')

    if save_path:
        gdf.to_file(save_path, crs=4326)
    return gdf


def generate_s2cell_points(bounding_box, cell_level):
    """
     Generates S2 cell polygons for a specified bounding box and cell level.

     This function uses the S2 geometry library to cover a bounding box with S2 cells
     at the specified level. It creates polygons for each cell and stores them in a GeoDataFrame.

     :param bounding_box: A tuple (west, south, east, north) defining the bounding box in degrees.
                          - west: Western longitude limit
                          - south: Southern latitude limit
                          - east: Eastern longitude limit
                          - north: Northern latitude limit
     :param cell_level: An integer representing the S2 cell level to use for the polygons.
     :param save_path: A path where generated polygons of the S2 cells will be stored. If not given, data not stored.
     :return: A GeoDataFrame containing the polygons of the S2 cells at the specified level.
     """
    west, south, east, north = bounding_box
    coverer = s2sphere.RegionCoverer()
    coverer.min_level = cell_level
    coverer.max_level = cell_level
    coverer.max_cells = 5000
    earth = s2sphere.LatLngRect(
        s2sphere.LatLng.from_degrees(south, west),
        s2sphere.LatLng.from_degrees(north, east)
    )
    covering = coverer.get_covering(earth)

    # Get the centroids of the S2 Cells
    points = []
    for cell_id in covering:
        centroid = cell_id.to_lat_lng()
        lat = centroid.lat().degrees
        lon = centroid.lng().degrees
        points.append((lon, lat))
    return points

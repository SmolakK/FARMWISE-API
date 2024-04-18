import s2sphere
import geopandas as gpd
from shapely.geometry import Polygon
import matplotlib.pyplot as plt

def generate_s2cell_polygons(bounding_box, cell_level):
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
            vertices.append((vertex.lng().degrees, vertex.lat().degrees))  # Reversed lat-lng to lng-lat for GeoDataFrame
        polygons.append(Polygon(vertices))

    # Create GeoDataFrame
    gdf = gpd.GeoDataFrame(geometry=polygons, crs='EPSG:4326')

    # Visualization
    fig, ax = plt.subplots()
    gdf.plot(ax=ax)
    ax.set_title(f'S2Cell Polygons at Level {cell_level}')
    plt.show()
    gdf.to_file(r'D:\level12.shp', crs=4326)
    return gdf

N = 59.0
S = 49.0
E = 22.2
W = 15.2
LEVEL = 12

generate_s2cell_polygons((W, S, E, N), LEVEL)

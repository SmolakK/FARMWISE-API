import pytest
import s2sphere
from shapely.geometry import Polygon
from utils.generate_cells import generate_s2cell_polygons, generate_s2cell_points


def test_generate_s2cell_polygons():
    # Define a small bounding box for testing
    bounding_box = (14.0, 50.0, 15.0, 51.0)  # (west, south, east, north)
    cell_level = 10

    # Generate S2 cell polygons
    polygons = generate_s2cell_polygons(bounding_box, cell_level)

    # Assertions
    assert not polygons.empty, "No polygons were generated"
    assert all(isinstance(geom, Polygon) for geom in polygons.geometry), "Generated objects are not polygons"
    assert len(polygons) > 0, "No S2 cells were covered in the bounding box"


def test_generate_s2cell_polygons_save_path(tmp_path):
    # Define a small bounding box for testing
    bounding_box = (14.0, 50.0, 15.0, 51.0)  # (west, south, east, north)
    cell_level = 10
    save_path = tmp_path / "s2_cells.gpkg"

    # Generate and save S2 cell polygons
    polygons = generate_s2cell_polygons(bounding_box, cell_level, save_path)

    # Assertions
    assert save_path.exists(), "The GeoPackage file was not created"
    assert not polygons.empty, "No polygons were generated and saved"


def test_generate_s2cell_points():
    # Define a small bounding box for testing
    bounding_box = (14.0, 50.0, 15.0, 51.0)  # (west, south, east, north)
    cell_level = 10

    # Generate S2 cell points
    points = generate_s2cell_points(bounding_box, cell_level)

    # Assertions
    assert len(points) > 0, "No points were generated"
    assert all(len(pt) == 2 for pt in points), "Points do not have latitude and longitude values"
    assert all(-90 <= pt[1] <= 90 for pt in points), "Latitude values are out of bounds"
    assert all(-180 <= pt[0] <= 180 for pt in points), "Longitude values are out of bounds"


def test_generate_s2cell_points_large_bounding_box():
    # Test with a larger bounding box
    bounding_box = (10.0, 40.0, 20.0, 50.0)  # (west, south, east, north)
    cell_level = 5

    # Generate S2 cell points
    points = generate_s2cell_points(bounding_box, cell_level)

    # Assertions
    assert len(points) > 0, "No points were generated for the large bounding box"

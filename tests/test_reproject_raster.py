import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.crs import CRS
import numpy as np
from utils.reproject_raster import reproject_raster


@pytest.fixture
def mock_raster():
    """
    Create a mock raster dataset for testing purposes.
    """
    width, height = 100, 100
    transform = from_origin(0, 100, 1, 1)  # Define transform: top-left corner (0, 100) with 1x1 pixel size
    crs = CRS.from_epsg(3857)

    # Generate a sample data array
    data = np.arange(width * height, dtype=np.float32).reshape(height, width)

    # Create an in-memory raster dataset
    with rasterio.MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype=data.dtype,
            crs=crs,
            transform=transform,
        ) as dataset:
            dataset.write(data, 1)
            yield dataset


def test_reproject_raster(mock_raster):
    # Call the function under test
    reprojected_data, reprojected_transform, reprojected_width, reprojected_height = reproject_raster(mock_raster)

    # Assert the output dimensions
    assert reprojected_data.shape == (reprojected_height, reprojected_width), "Reprojected dimensions mismatch."

    # Assert that the transform is valid
    assert reprojected_transform is not None, "Transform should not be None."

    # Assert that reprojected data contains some values
    assert not np.all(reprojected_data == 0), "Reprojected data should not be entirely zero."

    # Assert that the CRS has been correctly reprojected
    assert mock_raster.crs != "EPSG:4326", "Source CRS should differ from target CRS."

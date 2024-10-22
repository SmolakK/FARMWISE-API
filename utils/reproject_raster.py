import rasterio
import numpy as np
from rasterio.warp import calculate_default_transform, reproject, Resampling


def reproject_raster(src, target_crs="EPSG:4326"):
    """
    Reproject a raster to the target CRS.

    Parameters:
    - src: the open rasterio dataset to be reprojected.
    - target_crs: the target coordinate reference system (default 'EPSG:4326').

    Returns:
    - dst_array: the reprojected data array.
    - dst_transform: the transformation matrix for the reprojected data.
    - width: width of the reprojected raster.
    - height: height of the reprojected raster.
    """
    transform, width, height = calculate_default_transform(
        src.crs, target_crs, src.width, src.height, *src.bounds)

    dst_array = np.empty((height, width), dtype=src.read(1).dtype)

    # Reproject the raster
    reproject(
        source=rasterio.band(src, 1),  # Assuming single band (1)
        destination=dst_array,
        src_transform=src.transform,
        src_crs=src.crs,
        dst_transform=transform,
        dst_crs=target_crs,
        resampling=Resampling.nearest)

    return dst_array, transform, width, height

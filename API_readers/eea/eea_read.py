import os.path
import logging
import numpy as np
import rasterio
from datetime import datetime
import asyncio
import pandas as pd
from utils.coordinates_to_cells import prepare_coordinates
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds
from rasterio.warp import (
    transform_bounds,
    calculate_default_transform,
    reproject,
    Resampling
)

async def read_data(
        spatial_range:tuple, time_range:tuple, data_range:list, level:int
    )->pd.DataFrame:
    """
    Asynchronously reads environmental raster data from an EEA dataset
    for a specified spatial, temporal, and value range.

    Parameters
    ----------
    spatial_range : tuple
        A tuple containing the geographical coordinates (N, S, E, W)
        of the area for which data is requested. Format: (North, South,
        East, West) in decimal degrees.
    time_range : tuple
        Time interval in the form (start_time, end_time) used to filter data.
        Format: Unix timestamp.
    data_range : list
        A list of factors specifying the type of data requested.
    level : int
        S2Cell level.

    Returns
    -------
    pandas.DataFrame
        A DataFrame containing filtered raster values and metadata.

    Notes
    -----
    Source raster path (EEA_DATA variable):
    eea_data/eea_r_3035_1_km_env-zones_p_2018_v01_r00.tif
    """

    logging.basicConfig(format="%(message)s", level=logging.INFO)
    logging.info("DOWNLOADING: EEA")

    EEA_DATA = os.path.join(
        'API_readers',
        'eea',
        'eea_data',
        'eea_r_3035_1_km_env-zones_p_2018_v01_r00.tif'
    )

    # Parse time range
    start, end = time_range
    start = datetime.strptime(start, '%Y-%m-%d').date()
    end = datetime.strptime(end, '%Y-%m-%d').date()

    # Raster year constraint
    raster_year = 2018
    if not (start.year <= raster_year <= end.year):
        logging.warning(
            "Requested time range does not include raster year 2018"
        )

    # Read raster async-safe
    clipped, transform = await asyncio.to_thread(
        read_raster_window, EEA_DATA, spatial_range
    )

    height, width = clipped.shape

    # Generate lat/lon grids
    rows, cols = np.meshgrid(
        np.arange(height), np.arange(width), indexing="ij"
    )
    xs, ys = rasterio.transform.xy(
        transform, rows, cols, offset='center'
    )
    xs = np.array(xs)
    ys = np.array(ys)

    data_rows = []

    # Build row records
    for i in range(height):
        for j in range(width):
            idx = i * width + j
            value = clipped[i, j]
            # Skip nodata
            if np.isnan(value):
                continue
            data_rows.append({
                "lat": ys[idx],
                "lon": xs[idx],
                "value": float(value)
            })

    # Convert to DataFrame
    df = pd.DataFrame(data_rows)
    if df.empty:
        logging.warning("No raster data in selected bbox")
        return df

    # Assign S2 cells
    df = prepare_coordinates(df, spatial_range, level)
    df = df.set_index("S2CELL")

    # Aggregate per cell
    df = df.groupby(level=0).mean().reset_index()
    df = df.drop(['lat', 'lon'], axis=1)
    df.value = round(df.value,0)
    df["Timestamp"] = pd.to_datetime('2018-01-01').floor("D")

    dates = pd.date_range(start=start, end=end, freq='D')
    df_expanded = pd.concat([df.assign(Timestamp=d) for d in dates])
    final_df = df_expanded.pivot_table(index="Timestamp", columns="S2CELL")

    return final_df


def read_raster_window(path, spatial_range):
    """
    Read raster window and return data reprojected to EPSG:4326
    """
    north, south, east, west = spatial_range
    dst_crs = "EPSG:4326"

    with rasterio.open(path) as src:
        left, bottom, right, top = transform_bounds(
            dst_crs, src.crs, west, south, east, north
        )
        window = from_bounds(
            left, bottom, right, top, transform=src.transform
        )
        src_data = src.read(1, window=window).astype(float)
        src_data[src_data == src.nodata] = np.nan
        src_transform = src.window_transform(window)

        dst_transform, dst_width, dst_height = calculate_default_transform(
            src.crs,
            dst_crs,
            window.width,
            window.height,
            *rasterio.transform.array_bounds(
                window.height, window.width, src_transform
            )
        )

        dst_data = np.empty((dst_height, dst_width), dtype=float)
        dst_data[:] = np.nan
        reproject(
            source=src_data,
            destination=dst_data,
            src_transform=src_transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.nearest
        )

    return dst_data, dst_transform

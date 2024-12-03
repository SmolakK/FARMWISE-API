import numpy as np
import pandas as pd
from utils.coordinates_to_cells import prepare_coordinates
from utils.interpolate_data import interpolate
import rasterio
from rasterio.windows import from_bounds
import asyncio

EGDI_FILE = r'data/gewp7_peu7_4326.tif'


async def read_data(spatial_range, time_range, data_range, level):
    """
    N = 51.2
    S = 49.0
    E = 17.1
    W = 15.0
    LEVEL = 8
    TIME_FROM = '2010-01-01'
    TIME_TO = '2023-12-31'
    FACTORS = ['hydraulic conductivity']

    df = read_data((N, S, E, W),(TIME_FROM,TIME_TO),FACTORS,LEVEL)

    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param time_range: A tuple containing the start and end timestamps defining the time range.
    :param data_range: A list of properties requested.
                       Allowed properties: 'hydraulic conductivity'
    :param level: S2Cell level.
    :return: A pandas DataFrame containing the processed data.
    """
    def load_raster_data():
        with rasterio.open(EGDI_FILE) as dataset:
            north, south, east, west = spatial_range
            window = rasterio.windows.from_bounds(
                left=west, bottom=south, right=east, top=north, transform=dataset.transform
            )

            # Read the data within the window
            data = dataset.read(1, window=window)

            # Generate meshgrid of row and column indices
            rows, cols = data.shape
            row_indices, col_indices = np.meshgrid(
                np.arange(window.row_off, window.row_off + rows),
                np.arange(window.col_off, window.col_off + cols),
                indexing='ij'
            )

            # Use the meshgrid to get corresponding x, y coordinates
            x_coords, y_coords = rasterio.transform.xy(dataset.transform, row_indices, col_indices, offset='center')

            return data, x_coords, y_coords

    # Offload raster loading to a separate thread to avoid blocking the event loop
    data, x_coords, y_coords = await asyncio.to_thread(load_raster_data)

    # Flatten the data and coordinates
    flat_data = data.flatten()
    flat_x_coords = np.array(x_coords).flatten()
    flat_y_coords = np.array(y_coords).flatten()

    # Create a DataFrame
    df = pd.DataFrame({
        'lon': flat_x_coords,
        'lat': flat_y_coords,
        'Hydraulic Conductivity DRASTIC': flat_data
    })
    df = prepare_coordinates(df, spatial_range, level)
    df = df.set_index('S2CELL')
    df = df.groupby(level=0).mean().reset_index()

    # Explode to days
    days = pd.date_range(time_range[0], time_range[1], freq='D')
    df = pd.concat([df.assign(Timestamp=date.date()) for date in days])

    df = df.drop(['lat', 'lon'], axis=1)

    # Pivot the DataFrame
    final_df = df.pivot_table(index='Timestamp', columns='S2CELL')

    return final_df

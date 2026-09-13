import numpy as np
import pandas as pd
from farmwise_api.core.utils.coordinates_to_cells import prepare_coordinates
import rasterio
from rasterio.windows import from_bounds
import asyncio
from farmwise_api.adapters.mappings.data_source_mapping import WITHIN_SOURCE_AGGREGATION_METHODS
from farmwise_api.core.within_source_aggregation import aggregate_to_s2
from farmwise_api.core.utils.paths import adapter_data

EGDI_RESOURCE = ("egdi", "data", "gewp7_peu1_d10km_4326.tif")


async def read_data(spatial_range, time_range, data_range, level,
                    within_source_aggregation_methods=None) -> pd.DataFrame:
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
    north, south, east, west = spatial_range

    # Load and process the raster file asynchronously using a synchronous context manager in a thread
    def load_raster_data():
        # EGDI files are intentionally not distributed with FARMWISE. A local
        # user must provide a lawfully obtained copy through FARMWISE_DATA_DIR.
        with rasterio.open(adapter_data(*EGDI_RESOURCE)) as dataset:
            window = from_bounds(left=west, bottom=south, right=east, top=north, transform=dataset.transform)
            win_transform = rasterio.windows.transform(window, dataset.transform)

            # Read the data within the window
            # Mask the raster's nodata value so fill pixels (sea, areas
            # outside the mapped extent) do not enter the S2-cell averages
            # as if they were index scores.
            data = dataset.read(1, window=window, masked=True)
            data = np.ma.filled(data.astype(float), np.nan)

            # Column and row coordinates within the window
            cols = np.arange(data.shape[1])
            rows = np.arange(data.shape[0])

            # Build meshgrid in pixel space
            col_indices, row_indices = np.meshgrid(cols, rows)

            # Convert to spatial coords
            x_coords, y_coords = rasterio.transform.xy(
                win_transform, row_indices, col_indices, offset="center"
            )

            # Cast to numpy arrays
            x_coords = np.array(x_coords)
            y_coords = np.array(y_coords)

            return data, x_coords, y_coords

    # Offload raster loading to a separate thread to avoid blocking the event loop
    data, x_coords, y_coords = await asyncio.to_thread(load_raster_data)

    # Flatten data and coordinates asynchronously
    flat_data = data.flatten()
    flat_x_coords = np.array(x_coords).flatten()
    flat_y_coords = np.array(y_coords).flatten()

    df = pd.DataFrame({
        'lon': flat_x_coords,
        'lat': flat_y_coords,
        'Depth to Watertable DRASTIC': flat_data
    })

    # Prepare coordinates and perform grouping
    df = prepare_coordinates(df, spatial_range, level)
    df = aggregate_to_s2(
        df,
        group_by=("S2CELL",),
        logical_data_types=data_range,
        methods=(within_source_aggregation_methods
                 or WITHIN_SOURCE_AGGREGATION_METHODS),
        column_aggregations={"lat": "mean", "lon": "mean"},
    ).reset_index()

    # Explode to days
    days = pd.date_range(time_range[0], time_range[1], freq='D')
    df = pd.concat([df.assign(Timestamp=date.date()) for date in days])

    # Drop unnecessary columns
    df = df.drop(['lat', 'lon'], axis=1)

    # Pivot the DataFrame
    final_df = df.pivot_table(index='Timestamp', columns='S2CELL')

    return final_df

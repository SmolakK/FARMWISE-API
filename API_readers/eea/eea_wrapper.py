import os.path
import logging
import rasterio
from datetime import datetime
import asyncio
import pandas as pd
from utils.coordinates_to_cells import prepare_coordinates
from utils.interpolate_data import interpolate

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
    Source raster path:
    eea_data/eea_r_3035_1_km_env-zones_p_2018_v01_r00.tif (EEA_DATA variable)
    """

    logging.basicConfig(format="%(message)s", level=logging.INFO)
    logging.info("DOWNLOADING: EEA")

    EEA_DATA = os.path.join(
        'eea_data',
        'eea_r_3035_1_km_env-zones_p_2018_v01_r00.tif'
    )



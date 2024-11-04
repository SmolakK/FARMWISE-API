import os.path
import cdsapi
import xarray as xr
import pandas as pd
from datetime import datetime
# from API_readers.cds.cds_mappings.cds_soilgrid_mappings import DATA_ALIASES, GLOBAL_MAPPING
from utils.coordinates_to_cells import prepare_coordinates
from utils.interpolate_data import interpolate
import warnings
import numpy as np

def read_data(spatial_range, time_range, data_range, level):
    """
    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param time_range: A tuple containing the start and end timestamps defining the time range.
    :param data_range: A list of data types requested.
                       Allowed data types: 'precipitation', 'sunlight', 'cloud cover', 'temperature',
                       'wind', 'pressure', 'humidity'.
    :param level: S2Cell level.
    :return:
    """
    print("DOWNLOADING: Copernicus Land Cover")

    dataset = 'satellite-land-cover'
    # Initialise the client
    c = cdsapi.Client()
    north, south, east, west = spatial_range
    start, end = time_range
    start = datetime.strptime(start, '%Y-%m-%d').date()
    end = datetime.strptime(end, '%Y-%m-%d').date()
    years = list(map(str,range(start.year,end.year+1)))
    # data_requested = list([k for k, v in DATA_ALIASES.items() if v in data_range])

    folder_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'temp_storage')
    file_name = dataset + "_temp_data.zip"
    temp_file_path = os.path.join(folder_path, file_name)

    # Request the data
    response = c.retrieve(
        dataset,  # Dataset name
        {
            'variable': 'all',  # Specify variables (land cover classes)
            'year': years,
            "version": ["v2_0_7cds","v2_1_1"],
            'area': [north, west, south, east],  # Spatial extent: North, West, South, East
        },
        temp_file_path
    )


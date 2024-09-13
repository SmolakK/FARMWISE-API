from mappings.data_source_mapping import API_PATH_RANGES
from utils.overlap_checks import spatial_ranges_overlap, time_ranges_overlap
import importlib
import zarr
import pandas as pd
from utils.cells_to_coordinates import s2cells_to_coordinates


def read_data(bounding_box, level, time_from, time_to, factors):
    """
    Main data reading call - combines different APIs which overlap with the requested area and time range.

    :param bounding_box: A tuple containing the geographical coordinates (N, S, E, W) of the area for which data is requested.
                         Format: (North, South, East, West) in decimal degrees.
    :param level: S2Cell level.
    :param time_from: The starting time from when data should be collected. Format: Unix timestamp.
    :param time_to: The ending time to when data should be collected. Format: Unix timestamp.
    :param factors: A list of factors specifying the type of data requested.
                    Allowed factors: 'precipitation', 'sunlight', 'cloud cover', 'temperature',
                    'wind', 'pressure', 'humidity'.

    :return: Requested DataCube in Zarr format. The DataCube contains data for the requested factors within the specified time range
             and geographical area.

    :raises: Specific exceptions raised by individual API modules if data retrieval fails.

    Note: `API_PATH_RANGES` is a dictionary mapping API names to their spatial, temporal, and data range constraints.
    """
    data_storage = []  # This will store data called from different APIs
    for k, v in API_PATH_RANGES.items():  # Iterate over API ranges
        api_spatial_range = v[0]  # Spatial range
        api_time_range = v[1]  # Temporal range
        api_data_range = set(v[2])  # Data range
        spatial_overlap = spatial_ranges_overlap(bounding_box, api_spatial_range)  # Check spatial overlap
        temporal_overlap = time_ranges_overlap((time_from, time_to), api_time_range)  # Check temporal overlap
        data_overlap = set(factors).intersection(api_data_range)  # Check data overlap
        if spatial_overlap and temporal_overlap and len(data_overlap) > 0:  # If overlaps
            module = importlib.import_module(k)  # Import the proper module
            # Read data from the module (parameters are the same for all read_data() functions)
            api_response_data = module.read_data(spatial_range=bounding_box, time_range=(time_from, time_to),
                                                 data_range=factors, level=level)
            data_storage.append(api_response_data)
    data_storage = pd.concat(data_storage,axis=1)  # TODO: how to merge data
    s_d_zarr = zarr.array(data_storage)
    return s_d_zarr

N = 59.0
S = 49.0
E = 24.2
W = 15.2
LEVEL = 18
TIME_FROM = '2017-01-01'
TIME_TO = '2017-04-22'
FACTORS = ['temperature', 'cloud cover']

read_data(bounding_box = (N, S, E, W), level = LEVEL, time_from = TIME_FROM, time_to = TIME_TO, factors = FACTORS)

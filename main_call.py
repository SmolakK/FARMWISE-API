from mappings.data_source_mapping import API_PATH_RANGES
from utils.overlap_checks import spatial_ranges_overlap, time_ranges_overlap
from utils.interpolate_data import interpolate
import importlib
import pandas as pd
import logging
import asyncio

logger = logging.getLogger(__name__)


async def read_data(bounding_box, level, time_from, time_to, factors, separate_api=False, timeout=600,
                    interpolation=False):
    """
    Main data reading call - combines different APIs which overlap with the requested area and time range.

    :param interpolation: If true, interpolation is applied to the resulting data. Especially useful for maps and
    high data resolutions.
    :param timeout: Timeout for each API after which the process will skip this API.
    :param separate_api: If True APIs are stored in separate columns and not averaged
    :param bounding_box: A tuple containing the geographical coordinates (N, S, E, W) of the area for which data is requested.
                         Format: (North, South, East, West) in decimal degrees.
    :param level: S2Cell level.
    :param time_from: The starting time from when data should be collected. Format: Unix timestamp.
    :param time_to: The ending time to when data should be collected. Format: Unix timestamp.
    :param factors: A list of factors specifying the type of data requested.
                    Examples of allowed factors: 'precipitation', 'temperature'

    :return: Requested data in DataFrame of pandas.

    :raises: Specific exceptions raised by individual API modules if data retrieval fails.

    Note: `API_PATH_RANGES` is a dictionary mapping API names to their spatial, temporal, and data range constraints.
    """
    data_storage = []  # This will store data called from different APIs
    api_metadata = []
    for api_name, ranges in API_PATH_RANGES.items():  # Iterate over API ranges
        api_spatial_range = ranges[0]  # Spatial range
        api_time_range = ranges[1]  # Temporal range
        api_data_range = set(ranges[2])  # Data range
        spatial_overlap = spatial_ranges_overlap(bounding_box, api_spatial_range)  # Check spatial overlap
        temporal_overlap = time_ranges_overlap((time_from, time_to), api_time_range)  # Check temporal overlap
        data_overlap = set(factors).intersection(api_data_range)  # Check data overlap
        if spatial_overlap and temporal_overlap and len(data_overlap) > 0:  # If overlaps
            try:
                module = importlib.import_module(api_name)  # Import the proper module
                # Read data from the module (parameters are the same for all read_data() functions)
                api_response_data = await asyncio.wait_for(
                    module.read_data(spatial_range=bounding_box, time_range=(time_from, time_to),
                                     data_range=factors, level=level),
                    timeout=timeout)
                if isinstance(api_response_data, pd.DataFrame):
                    api_name_suffix = api_name.split('.')[-1]
                    api_columns = list(api_response_data.columns.get_level_values(0).unique())
                    api_dates = list(api_response_data.index.astype(str).unique())
                    api_cells = list(api_response_data.columns.get_level_values(1).unique().astype(str))
                    api_metadata.append({
                        "api_name": api_name_suffix,
                        "columns": api_columns,
                        "dates": api_dates,
                        "cells": api_cells,
                        "status": "success" if isinstance(api_response_data, pd.DataFrame) else "failure",
                        "error": str(e) if "e" in locals() else None  # Add error details if any
                    })
                    if separate_api:
                        api_response_data = api_response_data.add_suffix(f' ({api_name_suffix})')
                    data_storage.append(api_response_data)
                    logger.info(f'Data retrieved from {api_name_suffix}')
            except asyncio.TimeoutError:
                logger.error(f'Request to {api_name_suffix} timed out')
            except Exception as e:
                logger.error(f'Failed to retrieve data from {api_name}: {e}')

    # Concatenate data if any DataFrames were retrieved
    if data_storage:
        try:
            combined_data = pd.concat(data_storage)
            combined_data = combined_data.groupby(level=0).mean()  # average data from separate APIs
            if interpolation:  # be aware this inserts values to NaNs
                combined_data = interpolate(combined_data, bounding_box, level)
            return {"data": combined_data,  # The DataFrame containing the concatenated data
                    "metadata": {"apis": api_metadata  # List of metadata dictionaries for each API
                                 }
                    }
        except Exception as e:
            logger.error(f'Error concatenating data: {e}')
            return pd.DataFrame()  # Return an empty DataFrame if concatenation fails
    else:
        logger.warning("No data retrieved from available APIs")
        return pd.DataFrame()


asyncio.run(read_data((51.09, 50.00, 14.56, 14.14), 10, '2017-01-10', '2017-01-12', ['temperature', 'precipitation'],
                      separate_api=False, interpolation=True))

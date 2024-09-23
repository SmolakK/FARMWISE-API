import cdsapi
import xarray as xr
import pandas as pd
from io import BytesIO
from datetime import datetime
from API_readers.cds.cds_mappings.cds_mapping import PARAMETER_VALUES, PARAMETER_SELECTION, DATA_ALIASES


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
    print("DOWNLOADING: Copernicus ERA5 data")
    # Initialise the client
    c = cdsapi.Client()
    north, south, east, west = spatial_range
    start, end = time_range
    start = datetime.strptime(start, '%Y-%m-%d')
    end = datetime.strptime(end, '%Y-%m-%d')
    years = list(range(start.year, end.year + 1))
    data_requested = list([k for k, v in DATA_ALIASES.items() if v in data_range])
    if len(years) == 1:
        if start.month < end.month:
            months = list(range(start.month, end.month + 1))
        elif start.month == end.month:
            months = [start.month]
    else:
        months = list(range(1,13))
    if len(months) == 1:
        if start.day < end.day:
            days = list(range(start.day, end.day + 1))
        elif start.day == end.day:
            days = [start.day]
    else:
        days = list(range(1,32))

    # Request the data and keep it in memory
    response = c.retrieve(
        'reanalysis-era5-single-levels',  # Dataset name
        {
            'product_type': 'reanalysis',
            'variable': data_requested,  # Specify variables
            'year': list(map(str,years)),  # Specify year(s)
            'month': [str(i).zfill(2) for i in months],  # Specify month(s)
            'day': [str(i).zfill(2) for i in days],  # Specify day(s)
            'format': 'netcdf',  # File format
            'area': [north,west,south,east],  # Spatial extent: North, West, South, East
        }
    )

    # Load the response content into an in-memory NetCDF file
    netcdf_data = BytesIO(response.content)

    # Open the in-memory NetCDF data using xarray
    ds = xr.open_dataset(netcdf_data)

    # Convert xarray Dataset to pandas DataFrame
    df = ds.to_dataframe().reset_index()

N = 59.0
S = 49.0
E = 24.2
W = 15.2
LEVEL = 18
TIME_FROM = '2017-01-01'
TIME_TO = '2017-01-02'
FACTORS = ['temperature', 'snow']
read_data((N, S, E, W), (TIME_FROM, TIME_TO), FACTORS, LEVEL)
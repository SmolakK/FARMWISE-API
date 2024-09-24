import os.path
import cdsapi
import xarray as xr
import pandas as pd
from datetime import datetime
from API_readers.cds.cds_mappings.cds_mapping import DATA_ALIASES, GLOBAL_MAPPING
from utils.coordinates_to_cells import prepare_coordinates
from utils.interpolate_data import interpolate
import warnings


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
    start = datetime.strptime(start, '%Y-%m-%d').date()
    end = datetime.strptime(end, '%Y-%m-%d').date()
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

    folder_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),'temp_storage')
    file_name = "era5_temp_data.nc"
    temp_file_path = os.path.join(folder_path, file_name)
    # Request the data and keep it in memory
    response = c.retrieve(
        'reanalysis-era5-single-levels',  # Dataset name
        {
            'product_type': 'reanalysis',
            'variable': data_requested,  # Specify variables
            'year': list(map(str,years)),  # Specify year(s)
            'month': [str(i).zfill(2) for i in months],  # Specify month(s)
            'day': [str(i).zfill(2) for i in days], # Specify day(s)
            'hour': [f"{hour:02}:00" for hour in range(24)],
            'format': 'netcdf',
            'grid':[1.0, 1.0], # File format
            'area': [north,west,south,east],  # Spatial extent: North, West, South, East
        },
        temp_file_path
    )

    # Open tempfile
    ds = xr.open_dataset(temp_file_path)

    # Convert xarray Dataset to pandas DataFrame
    df = ds.to_dataframe().reset_index()

    # Cleaning
    df = df[~df.isna()]
    df = df.drop(['expver','number'],axis=1)
    df = df.drop_duplicates()

    # Naming
    df = df.rename(GLOBAL_MAPPING,axis=1)
    df = df.rename({'latitude':'lat','longitude':'lon','valid_time':'Timestamp'},axis=1)

    # To daily
    df['day'] = df['Timestamp'].dt.date
    df = df.groupby(['day', 'lat', 'lon']).mean().reset_index()
    df = df.drop(['day'],axis=1)

    # Temporal cut
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df['Timestamp'] = df['Timestamp'].dt.date
    df = df[(df['Timestamp'] >= start) & (df['Timestamp'] <= end)]

    # S2Cell Mapping
    df = prepare_coordinates(df,spatial_range,level)

    # Average overlapping
    original_size = df.shape[0]
    df = df.groupby(['S2CELL', 'Timestamp']).mean()
    if original_size != df.shape[0]:
        warnings.warn("Some data were aggregated")

    # Recalculate temperature te Celsius
    if "Temperature [°C]" in df.columns:
        df["Temperature [°C]"] = df["Temperature [°C]"] - 273.15

    # Data interpolation
    if level >= 10:
        df = interpolate(df, spatial_range, level)
        df = df.reset_index().rename({'level_0': 'S2CELL', 'level_1': 'Timestamp'},axis=1)
    else:
        df = df.drop(['lat', 'lon'], axis=1)

    # Pivot the DataFrame
    df = df.pivot_table(index='Timestamp', columns='S2CELL')

    return df

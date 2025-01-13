import os.path
import cdsapi
import xarray as xr
import pandas as pd
from datetime import datetime, timedelta
from API_readers.cds.cds_mappings.cds_single_levels_mapping import DATA_ALIASES, GLOBAL_MAPPING
from utils.coordinates_to_cells import prepare_coordinates
import warnings
import asyncio
import zipfile
import shutil


async def read_data(spatial_range, time_range, data_range, level):
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

    dataset = 'reanalysis-era5-single-levels'

    # Initialise the client
    c = cdsapi.Client()
    north, south, east, west = spatial_range
    start, end = time_range
    start = datetime.strptime(start, '%Y-%m-%d').date()
    end = datetime.strptime(end, '%Y-%m-%d').date()
    data_requested = list([k for k, v in DATA_ALIASES.items() if v in data_range])

    # Generate the unique lists
    years = set()
    months = set()
    days = set()

    current_date = start
    while current_date <= end:
        years.add(str(current_date.year))  # Convert to string
        months.add(f"{current_date.month:02}")  # Zero-padded as text
        days.add(f"{current_date.day:02}")  # Zero-padded as text
        current_date += timedelta(days=1)

    # Convert sets to sorted lists
    years = sorted(list(years))
    months = sorted(list(months))
    days = sorted(list(days))

    folder_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'temp_storage')
    file_name = dataset + "_temp_data.zip"
    temp_file_path = os.path.join(folder_path, file_name)
    # Request the data and keep it in memory
    request = {
            'product_type': ["reanalysis"],
            'variable': data_requested,  # Specify variables
            "year": list(years),
            "month": list(months),
            "day": list(days),
            "time": [f"{hour:02}:00" for hour in range(24)],
            'data_format': "netcdf",
            "download_format": "zip",
            'area': [north, west, south, east],  # Spatial extent: North, West, South, East
        }
    c.retrieve(dataset,request).download(temp_file_path)

    # Unzip files
    with zipfile.ZipFile(temp_file_path, 'r') as zip_ref:
        zip_ref.extractall(folder_path)
    extracted_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith('.nc')]
    datasets = [xr.open_dataset(f) for f in extracted_files]
    ds = xr.merge(datasets)

    # Convert xarray Dataset to pandas DataFrame
    df = ds.to_dataframe().reset_index()

    # Cleaning
    df = df[~df.isna()]
    df = df.drop(['expver', 'number'], axis=1)
    df = df.drop_duplicates()

    # Naming
    df = df.rename(GLOBAL_MAPPING, axis=1)
    df = df.rename({'latitude': 'lat', 'longitude': 'lon', 'valid_time': 'Timestamp'}, axis=1)

    # To daily
    df['day'] = df['Timestamp'].dt.date
    df = df.groupby(['day', 'lat', 'lon']).mean().reset_index()
    df = df.drop(['day'], axis=1)

    # Temporal cut
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df['Timestamp'] = df['Timestamp'].dt.date
    df = df[(df['Timestamp'] >= start) & (df['Timestamp'] <= end)]

    # S2Cell Mapping
    df = prepare_coordinates(df, spatial_range, level)

    # Average overlapping
    original_size = df.shape[0]
    df = df.groupby(['S2CELL', 'Timestamp']).mean()
    if original_size != df.shape[0]:
        warnings.warn("Some data were aggregated")

    # Recalculate temperature to Celsius
    if "Temperature [°C]" in df.columns:
        df["Temperature [°C]"] = df["Temperature [°C]"] - 273.15

    # Recalculate precipitation to a daily sum
    if 'Precipitation total [mm]' in df.columns:
        df['Precipitation total [mm]'] = df['Precipitation total [mm]']*(24*60*60)

    df = df.drop(['lat', 'lon'], axis=1)

    # Pivot the DataFrame
    df = df.pivot_table(index='Timestamp', columns='S2CELL')

    # Cleanup
    os.remove(temp_file_path)
    shutil.rmtree(folder_path)

    return df

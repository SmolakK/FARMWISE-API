import os
import cdsapi
import xarray as xr
import pandas as pd
from datetime import datetime
from utils.coordinates_to_cells import prepare_coordinates
from utils.interpolate_data import interpolate
import warnings
import zipfile
import glob
from cds_mappings.cds_vegetation_mapping import GLOBAL_MAPPING, DATA_ALIASES


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
    print("DOWNLOADING: Copernicus Agriculture Data")

    dataset = "sis-agroproductivity-indicators"

    # Initialise the client
    c = cdsapi.Client()
    north, south, east, west = spatial_range
    start, end = time_range
    start = datetime.strptime(start, '%Y-%m-%d').date()
    end = datetime.strptime(end, '%Y-%m-%d').date()

    # Generate a list of years, months, and days between start and end dates
    date_range = pd.date_range(start=start, end=end, freq='10D')
    years = sorted(set(date_range.strftime('%Y')))
    months = sorted(set(date_range.strftime('%m')))
    days = sorted(set(date_range.strftime('%d')))
    data_requested = list([k for k, v in DATA_ALIASES.items() if v in data_range])

    folder_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'temp_storage')
    file_name = dataset + "_temp_data.zip"
    temp_file_path = os.path.join(folder_path, file_name)

    # Prepare the request parameters
    response = c.retrieve(
        dataset,  # Dataset name
        {
        'product_family': ["evapotranspiration_indicators"],
        "variable": data_requested,
        'year': years,
        'month': months,
        'day': days,
        },
        temp_file_path
    )

    # Unzip the downloaded data
    with zipfile.ZipFile(temp_file_path, 'r') as zip_ref:
        zip_ref.extractall(folder_path)

    # Now read the extracted NetCDF files
    nc_files = glob.glob(os.path.join(folder_path, '*.nc'))

    # Check if any NetCDF files were extracted
    if not nc_files:
        raise FileNotFoundError("No NetCDF files found after extracting the zip file.")

    # Open and concatenate all NetCDF files
    ds = [xr.open_dataset(nc_file).sel(lat_var=slice(north, south), lon_var=slice(west, east)) for nc_file in nc_files]

    # Select the desired spatial subset
    ds = [dd.to_dataframe().reset_index() for dd in ds]

    # Convert xarray Dataset to pandas DataFrame
    df = pd.concat(ds)

    # Rename columns if necessary
    if 'time' in df.columns:
        df.rename(columns={'time': 'Timestamp'}, inplace=True)
    df.rename(columns={'lat_var':'lat','lon_var':'lon'},inplace=True)
    df = df.drop(['crs', 'PIXEL_COUNTS', 'ALBH_QFLAG', 'FCOVER_QFLAG', 'LAI_QFLAG'], axis=1)

    df = df.rename(GLOBAL_MAPPING, axis=1)

    # Convert 'Timestamp' to datetime if it's not already
    if not pd.api.types.is_datetime64_any_dtype(df['Timestamp']):
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])

    # Filter data within the specified time range
    df = df[(df['Timestamp'] >= pd.to_datetime(start)) & (df['Timestamp'] <= pd.to_datetime(end))]

    # S2Cell Mapping
    df = prepare_coordinates(df, spatial_range, level)

    # Average overlapping data
    original_size = df.shape[0]
    df = df.groupby(['S2CELL', 'Timestamp']).mean()
    if original_size != df.shape[0]:
        warnings.warn("Some data were aggregated due to overlapping cells.")

    # Data interpolation
    if level >= 18:
        df = interpolate(df, spatial_range, level)
        df = df.reset_index().rename({'level_0': 'S2CELL', 'level_1': 'Timestamp'}, axis=1)
    else:
        df = df.reset_index()
        df.drop(['lat', 'lon'], axis=1, inplace=True)

    # Pivot the DataFrame
    df = df.pivot_table(index='Timestamp', columns='S2CELL')

    # Clean up temporary files
    os.remove(temp_file_path)
    for f in nc_files:
        os.remove(f)

    return df

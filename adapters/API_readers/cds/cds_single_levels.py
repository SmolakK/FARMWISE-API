import cdsapi
import xarray as xr
import pandas as pd
from datetime import datetime, timedelta
from adapters.API_readers.cds.cds_mappings.cds_single_levels_mapping import DATA_ALIASES, GLOBAL_MAPPING
from core.utils.coordinates_to_cells import prepare_coordinates
import warnings
from core.utils.paths import scratch_dir


async def read_data(spatial_range, time_range, data_range, level):
    """
    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param time_range: A tuple containing the start and end timestamps defining the time range.
    :param data_range: A list of data types requested.
                       Allowed data types: 'precipitation', 'sunlight', 'cloud cover', 'temperature',
                       'wind', 'pressure', 'humidity', 'soil_humidity'.
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

    request = {
            'product_type': ["reanalysis"],
            'variable': data_requested,  # Specify variables
            "year": list(years),
            "month": list(months),
            "day": list(days),
            "time": [f"{hour:02}:00" for hour in range(24)],
            'data_format': "netcdf",
            "download_format": "unarchived",
            'area': [north, west, south, east],  # Spatial extent: North, West, South, East
        }
    with scratch_dir("cds") as folder_path:
        temp_file_path = folder_path / f"{dataset}_temp_data.nc"
        c.retrieve(dataset, request).download(str(temp_file_path))
        downloaded_dataset = xr.open_dataset(temp_file_path)
        try:
            df = downloaded_dataset.to_dataframe().reset_index()
        finally:
            downloaded_dataset.close()

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

    return df

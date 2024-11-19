import asyncio
from soilgrids import SoilGrids
from utils.interpolate_data import how_many
import pandas as pd
import numpy as np
from utils.coordinates_to_cells import prepare_coordinates
from API_readers.soilgrids.soilgrids_mappings.soilgrids_mapping import GLOBAL_MAPPING, DATA_ALIASES, DEPTH_MAPPING
import warnings


async def read_data(spatial_range, time_range, data_range, level):
    """
    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param time_range: A tuple containing the start and end timestamps defining the time range.
    :param data_range: A list of soil properties requested.
                       Allowed soil properties: 'soc', 'clay', 'silt',
                       'sand', 'bdod', 'phh2o', 'cec', etc.
    :param level: S2Cell level.
    :return: A pandas DataFrame containing the processed soil data.
    """
    print("DOWNLOADING: SoilGrids Data")

    # Initialize the SoilGrids client
    soilgrids = SoilGrids()

    # Define the bounding box
    north, south, east, west = spatial_range
    size_lat, size_lon = how_many(north, south, east, west, level)

    data_requested = list([k for k, v in DATA_ALIASES.items() if v in data_range])

    # Define an async function to get soil data
    async def fetch_soil_data(soil_property):
        print(f"Fetching {soil_property} data...")
        data = await asyncio.to_thread(
            soilgrids.get_coverage_data,
            service_id=soil_property,
            coverage_id=DEPTH_MAPPING[soil_property],
            west=west,
            south=south,
            east=east,
            north=north,
            crs='urn:ogc:def:crs:EPSG::4326',
            width=size_lon,
            height=size_lat,
            output=r'API_readers/soilgrids/temp_storage/out_{}.tif'.format(soil_property)
        )
        return data

    # Fetch all soil data asynchronously
    datasets = await asyncio.gather(*[fetch_soil_data(prop) for prop in data_requested])

    # Process datasets asynchronously
    def process_data():
        # Convert the datasets into numpy arrays and stack them
        datasets_np = [np.array(data) for data in datasets]
        datasets_np = np.stack(datasets_np, axis=0)

        # Create latitude and longitude grids based on the bounding box
        latitudes = np.linspace(south, north, size_lat)
        longitudes = np.linspace(west, east, size_lon)

        data_rows = []
        for i, lat in enumerate(latitudes):
            for j, lon in enumerate(longitudes):
                coors = {'lat': lat, 'lon': lon}
                coors.update({k: v for k, v in zip(data_requested, datasets_np[:, 0, i, j])})
                data_rows.append(coors)

        # Convert the list of rows into a DataFrame
        df = pd.DataFrame.from_dict(data_rows)
        return df

    df = await asyncio.to_thread(process_data)

    # Prepare coordinates and downgrade to S2 cells
    df = prepare_coordinates(df, spatial_range, level)
    df = df.set_index('S2CELL')
    df = df.groupby(level=0).mean().reset_index()

    df = df.rename(GLOBAL_MAPPING, axis=1)

    # Average overlapping
    original_size = df.shape[0]
    df = df.groupby(['S2CELL']).mean()
    if original_size != df.shape[0]:
        warnings.warn("Some data were aggregated")

    # Explode to days
    days = pd.date_range(time_range[0], time_range[1], freq='D')
    df = pd.concat([df.assign(Timestamp=date.date()) for date in days])

    df = df.drop(['lat', 'lon'], axis=1)

    # Pivot the DataFrame asynchronously
    df = await asyncio.to_thread(lambda: df.pivot_table(index='Timestamp', columns='S2CELL'))

    return df

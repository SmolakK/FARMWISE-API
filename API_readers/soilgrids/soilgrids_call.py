from soilgrids import SoilGrids
from utils.interpolate_data import how_many
import pandas as pd
import numpy as np
from utils.coordinates_to_cells import prepare_coordinates
from API_readers.soilgrids.soilgrids_mappings.soilgrids_mapping import GLOBAL_MAPPING, DATA_ALIASES, DEPTH_MAPPING


def read_data(spatial_range, time_range, data_range, level):
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

    # Loop through the requested data ranges (soil properties)
    datasets = []
    for soil_property in data_requested:
        print(f"Fetching {soil_property} data...")

        # Get soil data for the specific bounding box and soil property
        data = soilgrids.get_coverage_data(service_id=soil_property,
                                           coverage_id=DEPTH_MAPPING[soil_property],
                                           west=west,
                                           south=south,
                                           east=east,
                                           north=north,
                                           crs='urn:ogc:def:crs:EPSG::4326',
                                           width=size_lon,  # Resolution - adjust as needed
                                           height=size_lat,
                                           output=r'temp_storage\out.tif')

        # Convert the soil data into a numpy array for easier handling
        soil_values = np.array(data)
        datasets.append(soil_values)

    # Create lat/lon grids based on the bounding box and pixel dimensions
    latitudes = np.linspace(south, north, size_lat)
    longitudes = np.linspace(west, east, size_lon)

    data_rows = []
    datasets = np.stack(datasets, axis=0)
    for i, lat in enumerate(latitudes):
        for j, lon in enumerate(longitudes):
            coors = {'lat': lat, 'lon': lon}
            coors.update({k: v for k, v in zip(data_requested, np.stack(datasets, axis=0)[:, 0, i, j])})
            data_rows.append(coors)

    # Convert the list of rows into a pandas DataFrame
    df = pd.DataFrame.from_dict(data_rows)
    df = prepare_coordinates(df, spatial_range, level)

    # Downgrade to S2CELLS
    df = df.set_index('S2CELL')
    df = df.groupby(level=0).mean().reset_index(drop=True)

    # Naming
    df = df.rename(GLOBAL_MAPPING, axis=1)

    # Explode to days
    days = pd.date_range(time_range[0],time_range[1],freq='D')
    df = pd.concat([df.assign(Timestamp=date) for date in days])

    df = df.drop(['lat', 'lon'], axis=1)

    # Pivot the DataFrame
    df = df.pivot_table(index='Timestamp', columns='S2CELL')

    return df

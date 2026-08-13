from soilgrids import SoilGrids
from farmwise_api.core.utils.interpolate_data import how_many
import pandas as pd
import numpy as np
from farmwise_api.core.utils.coordinates_to_cells import prepare_coordinates
from farmwise_api.adapters.API_readers.soilgrids.soilgrids_mappings.soilgrids_mapping import GLOBAL_MAPPING, DATA_ALIASES, DEPTH_MAPPING
import warnings
from farmwise_api.core.utils.paths import scratch_file
from farmwise_api.adapters.mappings.data_source_mapping import WITHIN_SOURCE_AGGREGATION_METHODS
from farmwise_api.core.within_source_aggregation import aggregate_to_s2


def fetch_soil_data(soilgrids, soil_property, west, south, east, north, size_lon, size_lat):
    print(f"Fetching {soil_property} data...")
    data = soilgrids.get_coverage_data(
        service_id=soil_property,
        coverage_id=DEPTH_MAPPING[soil_property],
        west=west,
        south=south,
        east=east,
        north=north,
        crs='urn:ogc:def:crs:EPSG::4326',
        width=size_lon,
        height=size_lat,
        output=str(scratch_file("soilgrids", stem=f"out_{soil_property}")),
    )
    return np.array(data)


async def read_data(spatial_range, time_range, data_range, level,
                    within_source_aggregation_methods=None):
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

    # Fetch all soil data
    datasets_np = []
    for prop in data_requested:
        data = fetch_soil_data(soilgrids, prop, west, south, east, north, size_lon, size_lat)
        datasets_np.append(data)

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

    # Prepare coordinates and downgrade to S2 cells
    df = prepare_coordinates(df, spatial_range, level)
    df = df.rename(GLOBAL_MAPPING, axis=1)
    df = aggregate_to_s2(
        df,
        group_by=("S2CELL",),
        logical_data_types=data_range,
        methods=(within_source_aggregation_methods
                 or WITHIN_SOURCE_AGGREGATION_METHODS),
        column_aggregations={"lat": "mean", "lon": "mean"},
    )

    # Explode to days
    days = pd.date_range(time_range[0], time_range[1], freq='D')
    df = pd.concat([df.assign(Timestamp=date.date()) for date in days])

    df = df.drop(['lat', 'lon'], axis=1)

    # Pivot the DataFrame asynchronously
    df = df.reset_index().pivot(index='Timestamp', columns='S2CELL')

    return df

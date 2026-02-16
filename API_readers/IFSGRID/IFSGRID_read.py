import os
import asyncio
from API_readers.IFSGRID.mappings.IFSGRID_mappings import DATA_ALIASES
from API_readers.IFSGRID.utils.extraction import factor_mapping_extractor, extract_values
from shapely.geometry import box
import pandas as pd
from utils.coordinates_to_cells import prepare_coordinates
from API_readers.IFSGRID.utils.preparation import check_overlap

async def read_data(spatial_range, time_range, data_range, level):

    DATASET = os.path.join(
        'API_readers',
        'IFSGRID',
        'data',
        'IFSGRID',
        'data'
    )

    start_date, end_date = check_overlap(time_range)
    if start_date is None:
        return None
    
    data_paths = factor_mapping_extractor(data_range, DATA_ALIASES, DATASET)
    factor_data_frame = pd.DataFrame(columns=['lat','lon'])
    
    north, south, east, west = spatial_range
    bbox_geom = box(west, south, east, north)

    for key, value in data_paths.items():
        try:
            data = extract_values(value, key, bbox_geom)
            factor_data_frame = pd.merge(
                factor_data_frame, 
                data, 
                on=["lat", "lon"], 
                how="outer"
            )
        except Exception as e:
            print(value, e)
            
    df = prepare_coordinates(factor_data_frame, spatial_range, level)
    df = df.set_index('S2CELL')
    df = df.groupby(level=0).mean().reset_index()
    df = df.drop(['lat', 'lon'], axis=1)

    dates = pd.date_range(start='2018-01-01', end=end_date, freq='D')
    df_expanded = pd.concat([df.assign(Timestamp=d) for d in dates])
    final_df = df_expanded.pivot_table(index="Timestamp", columns="S2CELL")

    return final_df

# Define the input parameters
N, S, E, W = 51.2, 49.0, 17.1, 15.0
TIME_FROM, TIME_TO = '2018-01-01', '2020-12-31'
FACTORS = ['agricultural structure']
LEVEL = 8

# Run the async function
if __name__ == "__main__":
    result = asyncio.run(read_data((N, S, E, W), (TIME_FROM, TIME_TO), FACTORS, LEVEL))
    print(result)

    
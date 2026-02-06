import os


async def read_data(spatial_range, time_range, data_range, level):

    DATASET = os.path.join(
        'API_readers',
        'IFSGRID',
        'data',
        'IFSGRID',
        'data'
    )

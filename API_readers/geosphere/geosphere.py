import httpx
import pandas as pd
from io import StringIO
from utils.coordinates_to_cells import prepare_coordinates
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from API_readers.geosphere.geosphere_mapping.geosphere_mapping import GLOBAL_MAPPING, DATA_ALIASES
import warnings
from datetime import datetime


async def fetch_station_metadata(resource_id="klima-v2-1d"):
    """
    Fetch metadata for all stations.
    """
    url = f"https://dataset.api.hub.geosphere.at/v1/station/historical/{resource_id}/metadata"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()['stations']
    data = pd.DataFrame(data)
    return data[['id', 'name', 'lat', 'lon']]


@retry(
    stop=stop_after_attempt(5),  # Retry up to 5 times
    wait=wait_exponential(multiplier=1, min=1, max=10),  # Exponential backoff
    retry=retry_if_exception_type(httpx.RequestError),  # Retry on HTTP request errors
)
async def fetch_station_data(resource_id, station_ids, time_range, parameters):
    """
    Fetch data for a list of stations.
    """
    start_date, end_date = time_range
    url = f"https://dataset.api.hub.geosphere.at/v1/station/historical/{resource_id}"
    params = {
        "parameters": ",".join(parameters),
        "start": start_date,
        "end": end_date,
        "station_ids": ",".join(map(str, station_ids)),
        "output_format": 'csv'
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = pd.read_csv(StringIO(response.text))
    return data


async def fetch_klima_v2_1d_by_bbox(spatial_range, time_range, data_range, level):
    """
    Fetch `klima-v2-1d` data by bounding box.
    :param spatial_range: Tuple containing the bounding box (south, west, north, east) in EPSG:4326.
    :param time_range: Tuple containing the start and end dates in 'YYYY-MM-DD' format.
    :param data_range: List of parameter codes to request (e.g., ['TL', 'RR']).
    :return: pandas DataFrame containing the requested data.
    """

    north, south, east, west = spatial_range
    start, end = time_range
    start = datetime.strptime(start, '%Y-%m-%d').date()
    end = datetime.strptime(end, '%Y-%m-%d').date()
    data_requested = list([k for k, v in DATA_ALIASES.items() if v in data_range])

    # Step 1: Fetch station metadata
    metadata_df = await fetch_station_metadata()

    # Step 2: Filter stations within the bounding box
    filtered_stations = metadata_df[
        (metadata_df["lat"] >= south) &
        (metadata_df["lat"] <= north) &
        (metadata_df["lon"] >= west) &
        (metadata_df["lon"] <= east)
        ]

    if filtered_stations.empty:
        print("No stations found within the specified bounding box.")
        return None

    station_ids = filtered_stations["id"].tolist()

    # Step 3: Fetch data for the filtered stations
    data_df = await fetch_station_data("klima-v2-1d", station_ids, time_range, data_requested)

    # Step 4: Combine and return the data
    if data_df.empty:
        print("No data found for the selected stations.")
        return None

    # CLEAN
    data_df = data_df[~data_df.isna().any(axis=1)]
    if 'precipitation' in data_range:
        data_df['rr'][data_df['rr'] < 0] = 0

    # Merge with metadata to include station coordinates
    data_df = data_df.merge(
        filtered_stations[["id", "lat", "lon"]],
        left_on="station", right_on='id',
        how="left"
    )

    # To daily
    data_df['Timestamp'] = pd.to_datetime(data_df['time']).dt.date
    data_df = data_df.drop(['time'], axis=1)

    # S2Cell Mapping
    data_df = prepare_coordinates(data_df, spatial_range, level)

    # Naming
    data_df = data_df[['S2CELL', 'Timestamp'] + data_requested]
    data_df = data_df.rename(GLOBAL_MAPPING, axis=1)

    # Temporal cut
    data_df = data_df[(data_df['Timestamp'] >= start) & (data_df['Timestamp'] <= end)]

    # Average overlapping
    original_size = data_df.shape[0]
    data_df = data_df.groupby(['S2CELL', 'Timestamp']).mean()
    if original_size != data_df.shape[0]:
        warnings.warn("Some data were aggregated")

    data_df = data_df.pivot_table(index='Timestamp', columns='S2CELL')
    return data_df

from wetterdienst.provider.dwd.observation import DwdObservationRequest
import pandas as pd
from core.utils.coordinates_to_cells import prepare_coordinates
import warnings
import asyncio
import datetime as dt
from adapters.API_readers.wetterdienst.wetterdienst_mapping.dwd_mapping import DATA_ALIASES, GLOBAL_MAPPING


async def fetch_data(request):
    """
    Fetch data asynchronously using Wetterdienst's DwdObservationRequest.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, request.values.all)


def _to_pandas(frame):
    """Normalize Wetterdienst's Polars output and legacy pandas output."""
    if hasattr(frame, "to_pandas"):
        return frame.to_pandas()
    return pd.DataFrame(frame)


async def read_data(spatial_range, time_range, data_range, level):
    """
    Reads meteorological data from DWD using wetterdienst.

    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param time_range: A tuple containing the start and end timestamps defining the time range.
    :param data_range: A list of parameter names requested (e.g., ['temperature_air_mean_200', 'precipitation_height']).
    :param level: S2Cell level.
    :return: A pandas DataFrame containing the processed data.
    """
    north, south, east, west = spatial_range
    start_date, end_date = time_range
    start_date = dt.datetime.strptime(start_date, '%Y-%m-%d')
    end_date = dt.datetime.strptime(end_date, '%Y-%m-%d')
    data_requested = list([k for k, v in DATA_ALIASES.items() if v in data_range])

    # Create a request object
    requests = DwdObservationRequest(
        parameters=[
            ("daily", "climate_summary", parameter)
            for parameter in data_requested
        ],
        start_date=start_date,
        end_date=end_date
    ).filter_by_bbox(west, south, east, north)

    # Fetch data asynchronously
    values_result = await fetch_data(requests)
    if hasattr(values_result, "to_dict"):
        # Compatibility with Wetterdienst versions that returned both values
        # and station metadata from ``to_dict``.
        values = values_result.to_dict(
            with_metadata=False,
            with_stations=True,
        )
        df = pd.DataFrame.from_dict(values["values"])
        df_stations = pd.DataFrame.from_dict(values["stations"])
    else:
        df = _to_pandas(values_result.df)
        df_stations = _to_pandas(requests.df)

    if df.empty:
        warnings.warn("No stations found in the specified bounding box.")
        return None

    # cleaning
    df = pd.pivot_table(df, index=['station_id','date'], columns='parameter', values='value').reset_index()
    df = df[~df.isna().any(axis=1)]

    # get stations locations
    df = df.merge(df_stations, left_on='station_id', right_on='station_id')
    df = df[data_requested + ['latitude','longitude','date']]


    df = df.rename(
        columns={
            'date': 'Timestamp',
            'latitude': 'lat',
            'longitude': 'lon',
        }
    )

    # Assign S2 cells
    df = prepare_coordinates(df, spatial_range, level)

    # Group by S2CELL, Timestamp, and Parameter
    original_size = df.shape[0]
    df = df.groupby(['S2CELL', 'Timestamp']+data_requested).mean().reset_index()

    if original_size != df.shape[0]:
        warnings.warn("Some data were aggregated")

    # Resample to daily intervals
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])

    df.set_index('Timestamp', inplace=True)
    df = (
        df.groupby(['S2CELL'] + data_requested)
            .resample('1D')
            .mean()
            .reset_index()
    )
    df['Timestamp'] = df['Timestamp'].dt.date
    df = df[(df['Timestamp'] >= start_date.date()) & (df['Timestamp'] <= end_date.date())]

    df = df.drop(['lat', 'lon'], axis=1)
    df = df.rename(GLOBAL_MAPPING, axis=1)

    # Recalculate temperature to Celsius
    if "Temperature [°C]" in df.columns:
        df["Temperature [°C]"] = df["Temperature [°C]"] - 273.15

    # Pivot the DataFrame
    df_pivot = df.pivot_table(
        index='Timestamp', columns='S2CELL')

    return df_pivot

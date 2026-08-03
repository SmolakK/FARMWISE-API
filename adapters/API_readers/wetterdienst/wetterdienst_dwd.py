from wetterdienst.provider.dwd.observation import DwdObservationRequest
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from core.utils.coordinates_to_cells import prepare_coordinates
import warnings
import asyncio
import datetime as dt
from threading import Event
from adapters.API_readers.wetterdienst.wetterdienst_mapping.dwd_mapping import DATA_ALIASES, GLOBAL_MAPPING
from adapters.mappings.data_source_mapping import WITHIN_SOURCE_AGGREGATION_METHODS
from core.within_source_aggregation import aggregate_to_s2


class _DwdFetchCancelled(Exception):
    """Internal signal used to stop between station downloads."""


def _collect_request(request, cancel_event):
    """Collect DWD values synchronously while honoring station boundaries."""
    values_api = request.values
    query_method = getattr(type(values_api), "query", None)

    if callable(query_method):
        frames = []
        results = iter(values_api.query())
        try:
            while True:
                if cancel_event.is_set():
                    raise _DwdFetchCancelled
                try:
                    result = next(results)
                except StopIteration:
                    break
                if cancel_event.is_set():
                    raise _DwdFetchCancelled
                frames.append(_to_pandas(result.df))
        finally:
            close = getattr(results, "close", None)
            if callable(close):
                close()
        return (
            pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(),
            _to_pandas(request.df),
        )

    # Compatibility with older Wetterdienst releases.
    values_result = values_api.all()
    if hasattr(values_result, "to_dict"):
        values = values_result.to_dict(
            with_metadata=False,
            with_stations=True,
        )
        return (
            pd.DataFrame.from_dict(values["values"]),
            pd.DataFrame.from_dict(values["stations"]),
        )
    return _to_pandas(values_result.df), _to_pandas(request.df)


def _build_and_collect_request(
    data_requested,
    start_date,
    end_date,
    bbox,
    cancel_event,
):
    """Build, spatially filter, and collect DWD data in one worker thread."""
    if cancel_event.is_set():
        raise _DwdFetchCancelled
    west, south, east, north = bbox
    request = DwdObservationRequest(
        parameters=[
            ("daily", "climate_summary", parameter)
            for parameter in data_requested
        ],
        start_date=start_date,
        end_date=end_date,
    ).filter_by_bbox(west, south, east, north)
    if cancel_event.is_set():
        raise _DwdFetchCancelled
    return _collect_request(request, cancel_event)


async def fetch_data(data_requested, start_date, end_date, bbox):
    """Run all blocking Wetterdienst operations outside the asyncio loop."""
    cancel_event = Event()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="farmwise-dwd")
    concurrent_future = executor.submit(
        _build_and_collect_request,
        data_requested,
        start_date,
        end_date,
        bbox,
        cancel_event,
    )
    future = asyncio.wrap_future(concurrent_future)
    try:
        return await asyncio.shield(future)
    except asyncio.CancelledError:
        cancel_event.set()
        try:
            await asyncio.shield(future)
        except (Exception, asyncio.CancelledError):
            pass
        raise
    finally:
        executor.shutdown(wait=True, cancel_futures=True)


def _to_pandas(frame):
    """Normalize Wetterdienst's Polars output and legacy pandas output."""
    if hasattr(frame, "to_pandas"):
        return frame.to_pandas()
    return pd.DataFrame(frame)


async def read_data(spatial_range, time_range, data_range, level,
                    within_source_aggregation_methods=None):
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

    # Wetterdienst performs synchronous network I/O while constructing and
    # filtering a request, so the whole operation runs in the worker.
    df, df_stations = await fetch_data(
        data_requested,
        start_date,
        end_date,
        (west, south, east, north),
    )

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

    df = aggregate_to_s2(
        df,
        logical_data_types=data_range,
        methods=(within_source_aggregation_methods
                 or WITHIN_SOURCE_AGGREGATION_METHODS),
        column_aggregations={"lat": "mean", "lon": "mean"},
    ).reset_index()

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

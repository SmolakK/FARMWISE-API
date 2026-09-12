from wetterdienst.provider.dwd.observation import DwdObservationRequest
from concurrent.futures import ThreadPoolExecutor
import inspect
import pandas as pd
from farmwise_api.core.utils.coordinates_to_cells import prepare_coordinates
import warnings
import asyncio
import datetime as dt
from threading import Event
from farmwise_api.adapters.API_readers.wetterdienst.wetterdienst_mapping.dwd_mapping import DATA_ALIASES, GLOBAL_MAPPING
from farmwise_api.adapters.mappings.data_source_mapping import WITHIN_SOURCE_AGGREGATION_METHODS
from farmwise_api.core.within_source_aggregation import aggregate_to_s2


class _DwdFetchCancelled(Exception):
    """Internal signal used to stop between station downloads."""


def _reject_incompatible_pydevd_asyncio_patch():
    """Reject PyCharm's Python 3.12-incompatible asyncio REPL patch."""
    task_class = asyncio.Task
    try:
        supports_eager_start = (
            "eager_start" in inspect.signature(task_class.__init__).parameters
        )
    except (TypeError, ValueError):
        supports_eager_start = True

    if (
        getattr(task_class, "_pydevd_nest_patched", False)
        and not supports_eager_start
    ):
        raise RuntimeError(
            "PyCharm's asyncio debugger is incompatible with Python 3.12 "
            "and aiohttp used by Wetterdienst. In PyCharm open Help > Find "
            "Action > Registry, disable 'python.debug.asyncio.repl', then "
            "restart the debug session (JetBrains issue PY-71488). Running "
            "without the debugger is unaffected."
        )


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
    # Wetterdienst's directory-listing cache serializes values with pickle.
    # Disable that cache so a writable cache directory can never become a
    # deserialization boundary.
    settings = {"cache_disable": True}
    request = DwdObservationRequest(
        parameters=[
            ("daily", "climate_summary", parameter)
            for parameter in data_requested
        ],
        start_date=start_date,
        end_date=end_date,
        settings=settings,
    ).filter_by_bbox(west, south, east, north)
    if cancel_event.is_set():
        raise _DwdFetchCancelled
    return _collect_request(request, cancel_event)


async def fetch_data(data_requested, start_date, end_date, bbox):
    """Run all blocking Wetterdienst operations outside the asyncio loop."""
    _reject_incompatible_pydevd_asyncio_patch()
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
                    within_source_aggregation_methods=None) -> pd.DataFrame | None:
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
    aggregation_methods = (
        within_source_aggregation_methods or WITHIN_SOURCE_AGGREGATION_METHODS
    )

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

    # Collapse duplicate observations before reshaping. Each parameter is
    # aggregated with the policy of its own logical data type.
    parameter_frames = []
    for parameter, parameter_frame in df.groupby('parameter', sort=False):
        data_type = DATA_ALIASES.get(parameter, "default")
        parameter_frames.append(
            aggregate_to_s2(
                parameter_frame[['station_id', 'date', 'parameter', 'value']],
                group_by=('station_id', 'date', 'parameter'),
                logical_data_types=(data_type,),
                methods=aggregation_methods,
                column_data_types={'value': data_type},
            ).reset_index()
        )
    df = pd.concat(parameter_frames, ignore_index=True).pivot(
        index=['station_id', 'date'],
        columns='parameter',
        values='value',
    ).reset_index()
    # Drop a row only when it carries no observation at all. The check has to
    # be restricted to the parameter columns: station_id and date are never
    # null after reset_index(), so testing the whole row would never drop
    # anything, while testing with .any() would discard a day that reported
    # temperature but no precipitation.
    observation_columns = [
        column for column in df.columns if column not in ('station_id', 'date')
    ]
    if observation_columns:
        df = df[~df[observation_columns].isna().all(axis=1)]

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
        methods=aggregation_methods,
        column_aggregations={"lat": "mean", "lon": "mean"},
    ).reset_index()

    # DWD climate summaries are already daily. Keep the unique rows produced
    # by aggregate_to_s2 instead of performing another implicit mean.
    df['Timestamp'] = pd.to_datetime(
        df['Timestamp'],
        utc=True,
    ).dt.tz_convert(None)
    df = df[
        (df['Timestamp'] >= pd.Timestamp(start_date))
        & (df['Timestamp'] <= pd.Timestamp(end_date))
    ]

    df = df.drop(['lat', 'lon'], axis=1)
    df = df.rename(GLOBAL_MAPPING, axis=1)

    # Recalculate temperature to Celsius
    # if "Temperature [°C]" in df.columns:
    #     df["Temperature [°C]"] = df["Temperature [°C]"] - 273.15

    # Pivot the DataFrame
    df_pivot = df.pivot(
        index='Timestamp', columns='S2CELL')

    return df_pivot

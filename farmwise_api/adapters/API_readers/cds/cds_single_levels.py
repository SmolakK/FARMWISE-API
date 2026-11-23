import cdsapi
import numpy as np
import xarray as xr
import pandas as pd
from datetime import datetime, timedelta
from farmwise_api.adapters.API_readers.cds.cds_mappings.cds_single_levels_mapping import DATA_ALIASES, GLOBAL_MAPPING
from farmwise_api.core.utils.coordinates_to_cells import prepare_coordinates
import zipfile
from farmwise_api.core.utils.paths import scratch_dir
from farmwise_api.adapters.mappings.data_source_mapping import WITHIN_SOURCE_AGGREGATION_METHODS
from farmwise_api.core.within_source_aggregation import aggregate_to_s2
import asyncio
import logging
import threading

logger = logging.getLogger(__name__)

# Monthly ERA5 chunks submitted to the CDS at the same time. The CDS limits
# how many requests one user may have running and queues the rest, so a
# higher number gains little and only lengthens that user's queue.
MAX_CONCURRENT_CDS_REQUESTS = 4


def _open_downloaded_dataset(path):
    """Open a CDS NetCDF response, including ZIP-wrapped NetCDF files."""
    if not zipfile.is_zipfile(path):
        return xr.open_dataset(path)

    # One directory per archive: monthly chunks are downloaded concurrently,
    # and every ERA5 archive names its members the same way, so a shared
    # directory let one month overwrite another's files mid-read.
    extract_dir = path.parent / f"{path.stem}_extracted"
    extract_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        netcdf_members = [
            member
            for member in archive.infolist()
            if not member.is_dir()
            and member.filename.lower().endswith((".nc", ".nc4", ".cdf"))
        ]
        for member in netcdf_members:
            target = (extract_dir / member.filename).resolve()
            if not target.is_relative_to(extract_dir.resolve()):
                raise ValueError("CDS returned an unsafe ZIP member path")
            archive.extract(member, extract_dir)

    netcdf_files = sorted(extract_dir / member.filename for member in netcdf_members)
    if not netcdf_files:
        raise ValueError("CDS returned a ZIP archive without any NetCDF files")
    if len(netcdf_files) == 1:
        return xr.open_dataset(netcdf_files[0])

    datasets = [xr.open_dataset(file_path) for file_path in netcdf_files]
    try:
        # ERA5 may split accumulated and instantaneous variables into separate
        # NetCDF files. Load the merged result before closing the source files.
        return xr.merge(datasets, compat="override").load()
    finally:
        for dataset in datasets:
            dataset.close()


PRECIPITATION_COLUMN = "Precipitation total [mm]"
_DAILY_KEYS = ["day", "lat", "lon"]


def _daily_from_hourly(hourly, data_range, methods):
    """Reduce hourly ERA5 rows to daily values per grid point.

    Returns ``(instantaneous, precipitation)``. Precipitation is a partial
    sum: the 00:00 accumulation belongs to the previous day, so a day's total
    is split across two calendar-day blocks and the parts are added up later.
    """
    df = hourly.drop(['expver', 'number'], axis=1, errors='ignore')
    df = df.drop_duplicates()

    # Naming
    df = df.rename(GLOBAL_MAPPING, axis=1)
    # ``valid_time`` in current CDS files, ``time`` in older ones.
    time_column = 'valid_time' if 'valid_time' in df.columns else 'time'
    df = df.rename(
        {'latitude': 'lat', 'longitude': 'lon', time_column: 'Timestamp'},
        axis=1,
    )

    # Convert source units before temporal aggregation. ERA5 ``tp`` contains
    # hourly accumulated metres; ``swvl1`` is a volumetric fraction.
    if "Temperature [°C]" in df.columns:
        df["Temperature [°C]"] = df["Temperature [°C]"] - 273.15
    if PRECIPITATION_COLUMN in df.columns:
        df[PRECIPITATION_COLUMN] = df[PRECIPITATION_COLUMN] * 1000
    if "Soil moisture [%]" in df.columns:
        df["Soil moisture [%]"] = df["Soil moisture [%]"] * 100

    keys = ['lat', 'lon']
    timestamps = pd.to_datetime(df['Timestamp'])
    value_columns = [
        column for column in df.columns
        if column not in {*keys, 'Timestamp'}
    ]
    instantaneous_columns = [
        column for column in value_columns
        if column != PRECIPITATION_COLUMN
    ]
    instantaneous = precipitation = None
    if instantaneous_columns:
        frame = df[keys + instantaneous_columns].copy()
        frame['day'] = timestamps.dt.floor('D')
        instantaneous = aggregate_to_s2(
            frame,
            group_by=_DAILY_KEYS,
            logical_data_types=data_range,
            methods=methods,
            warn_on_aggregation=False,
        ).reset_index()
    if PRECIPITATION_COLUMN in df.columns:
        frame = df[keys + [PRECIPITATION_COLUMN]].copy()
        frame['day'] = (timestamps - pd.Timedelta(hours=1)).dt.floor('D')
        precipitation = aggregate_to_s2(
            frame,
            group_by=_DAILY_KEYS,
            logical_data_types=data_range,
            methods=methods,
            column_aggregations={PRECIPITATION_COLUMN: 'sum'},
            warn_on_aggregation=False,
        ).reset_index()
    return instantaneous, precipitation


def _daily_from_dataset(dataset, data_range, methods):
    """``_daily_from_hourly`` over one downloaded month, a day at a time.

    Converting a whole month to a DataFrame first held every hourly value at
    once: for a Europe-wide box that is tens of millions of rows per month,
    with several months downloading together, and it ran out of memory.
    """
    time_name = "valid_time" if "valid_time" in dataset.dims else "time"
    days = pd.to_datetime(np.asarray(dataset[time_name].values)).floor("D")
    instantaneous, precipitation = [], []
    for day in days.unique():
        block = dataset.isel({time_name: np.flatnonzero(days == day)})
        daily, accumulated = _daily_from_hourly(
            block.to_dataframe().reset_index(), data_range, methods
        )
        if daily is not None:
            instantaneous.append(daily)
        if accumulated is not None:
            precipitation.append(accumulated)
    return instantaneous, precipitation


async def read_data(spatial_range, time_range, data_range, level,
                    within_source_aggregation_methods=None) -> pd.DataFrame:
    """
    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param time_range: A tuple containing the start and end timestamps defining the time range.
    :param data_range: A list of data types requested.
                       Allowed data types: 'precipitation', 'sunlight', 'cloud cover', 'temperature',
                       'wind', 'pressure', 'humidity', 'soil_humidity'.
    :param level: S2Cell level.
    :return:
    """
    logger.info("DOWNLOADING: Copernicus ERA5 data")

    dataset = 'reanalysis-era5-single-levels'

    north, south, east, west = spatial_range
    start, end = time_range
    start = datetime.strptime(start, '%Y-%m-%d').date()
    end = datetime.strptime(end, '%Y-%m-%d').date()
    data_requested = list([k for k, v in DATA_ALIASES.items() if v in data_range])

    # ERA5 total precipitation at 00:00 is the accumulation for the previous
    # hour. Include the following midnight so every requested day has 24
    # hourly accumulations.
    retrieval_end = (
        end + timedelta(days=1)
        if 'total_precipitation' in data_requested
        else end
    )
    # Set when the caller gives up (the dispatcher's timeout). Worker threads
    # cannot be interrupted, but they check this before downloading so an
    # abandoned request stops instead of fetching into a deleted directory.
    cancelled = threading.Event()
    limit = asyncio.Semaphore(MAX_CONCURRENT_CDS_REQUESTS)
    methods = (
        within_source_aggregation_methods
        or WITHIN_SOURCE_AGGREGATION_METHODS
    )

    async def _fetch(retrieve):
        async with limit:
            return await asyncio.to_thread(retrieve)

    with scratch_dir("cds") as folder_path:
        chunk_jobs = []
        for chunk_start, chunk_end in _monthly_periods(start, retrieval_end):
            request = {
                'product_type': ["reanalysis"],
                'variable': data_requested,
                "year": [str(chunk_start.year)],
                "month": [f"{chunk_start.month:02}"],
                "day": [
                    f"{day:02}"
                    for day in range(chunk_start.day, chunk_end.day + 1)
                ],
                "time": [f"{hour:02}:00" for hour in range(24)],
                'data_format': "netcdf",
                "download_format": "unarchived",
                'area': [north, west, south, east],
            }
            temp_file_path = folder_path / (
                f"{dataset}_{chunk_start:%Y%m}_temp_data.nc"
            )
            def _retrieve_chunk(request=request, temp_file_path=temp_file_path):
                """Submit, wait and decode: cdsapi is synchronous throughout.

                The CDS queue wait is often minutes, and run in the event loop
                it blocked every other request in the process - including the
                job-status polls of an asynchronous request.

                Each thread has its own client: chunks run concurrently and
                the client keeps a per-instance HTTP session.
                """
                if cancelled.is_set():
                    return [], []
                result = cdsapi.Client().retrieve(dataset, request)
                if cancelled.is_set():
                    return [], []
                result.download(str(temp_file_path))
                downloaded_dataset = _open_downloaded_dataset(temp_file_path)
                try:
                    return _daily_from_dataset(
                        downloaded_dataset, data_range, methods
                    )
                finally:
                    downloaded_dataset.close()

            chunk_jobs.append(_fetch(_retrieve_chunk))

        # The CDS queues every request separately and a large area waits
        # minutes per month. Submitted one after another, a three-month
        # Europe-wide request needed ~12 minutes and hit the 600 s dispatch
        # timeout; submitted together the waits overlap.
        try:
            downloaded_frames = await asyncio.gather(*chunk_jobs)
        except BaseException:
            cancelled.set()
            raise

    instantaneous = [part for parts, _ in downloaded_frames for part in parts]
    accumulated = [part for _, parts in downloaded_frames for part in parts]

    daily_frames = []
    if instantaneous:
        daily_frames.append(pd.concat(instantaneous, ignore_index=True))
    if accumulated:
        # Add up the two halves of each day's total (see _daily_from_hourly).
        daily_frames.append(
            pd.concat(accumulated, ignore_index=True)
            .groupby(_DAILY_KEYS, as_index=False)[PRECIPITATION_COLUMN]
            .sum(min_count=1)
        )

    if not daily_frames:
        return pd.DataFrame()
    df = daily_frames[0]
    for daily_frame in daily_frames[1:]:
        df = df.merge(daily_frame, on=_DAILY_KEYS, how='outer')
    df['Timestamp'] = pd.to_datetime(df.pop('day')).dt.date

    # Temporal cut
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df['Timestamp'] = df['Timestamp'].dt.date
    df = df[(df['Timestamp'] >= start) & (df['Timestamp'] <= end)]

    # S2Cell Mapping
    df = prepare_coordinates(df, spatial_range, level)

    df = aggregate_to_s2(
        df,
        logical_data_types=data_range,
        methods=methods,
        column_aggregations={"lat": "mean", "lon": "mean"},
    )

    df = df.drop(['lat', 'lon'], axis=1)

    # Pivot the DataFrame
    df = df.reset_index().pivot(index='Timestamp', columns='S2CELL')

    return df


def _monthly_periods(start, end):
    """Yield non-Cartesian monthly date chunks for a CDS request."""
    current = start
    while current <= end:
        next_month = (
            current.replace(year=current.year + 1, month=1, day=1)
            if current.month == 12
            else current.replace(month=current.month + 1, day=1)
        )
        chunk_end = min(end, next_month - timedelta(days=1))
        yield current, chunk_end
        current = next_month

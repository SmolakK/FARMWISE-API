import cdsapi
import xarray as xr
import pandas as pd
from datetime import datetime, timedelta
from farmwise_api.adapters.API_readers.cds.cds_mappings.cds_single_levels_mapping import DATA_ALIASES, GLOBAL_MAPPING
from farmwise_api.core.utils.coordinates_to_cells import prepare_coordinates
import zipfile
from farmwise_api.core.utils.paths import scratch_dir
from farmwise_api.adapters.mappings.data_source_mapping import WITHIN_SOURCE_AGGREGATION_METHODS
from farmwise_api.core.within_source_aggregation import aggregate_to_s2


def _open_downloaded_dataset(path):
    """Open a CDS NetCDF response, including ZIP-wrapped NetCDF files."""
    if not zipfile.is_zipfile(path):
        return xr.open_dataset(path)

    extract_dir = path.parent / "extracted"
    extract_dir.mkdir()
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


async def read_data(spatial_range, time_range, data_range, level,
                    within_source_aggregation_methods=None):
    """
    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param time_range: A tuple containing the start and end timestamps defining the time range.
    :param data_range: A list of data types requested.
                       Allowed data types: 'precipitation', 'sunlight', 'cloud cover', 'temperature',
                       'wind', 'pressure', 'humidity', 'soil_humidity'.
    :param level: S2Cell level.
    :return:
    """
    print("DOWNLOADING: Copernicus ERA5 data")

    dataset = 'reanalysis-era5-single-levels'

    # Initialise the client
    c = cdsapi.Client()
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
    downloaded_frames = []
    with scratch_dir("cds") as folder_path:
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
            c.retrieve(dataset, request).download(str(temp_file_path))
            downloaded_dataset = _open_downloaded_dataset(temp_file_path)
            try:
                downloaded_frames.append(
                    downloaded_dataset.to_dataframe().reset_index()
                )
            finally:
                downloaded_dataset.close()

    df = pd.concat(downloaded_frames, ignore_index=True)

    # Cleaning
    df = df[~df.isna()]
    df = df.drop(['expver', 'number'], axis=1, errors='ignore')
    df = df.drop_duplicates()

    # Naming
    df = df.rename(GLOBAL_MAPPING, axis=1)
    df = df.rename({'latitude': 'lat', 'longitude': 'lon', 'valid_time': 'Timestamp'}, axis=1)

    # Convert source units before temporal aggregation. ERA5 ``tp`` contains
    # hourly accumulated metres; ``swvl1`` is a volumetric fraction.
    if "Temperature [°C]" in df.columns:
        df["Temperature [°C]"] = df["Temperature [°C]"] - 273.15
    if "Precipitation total [mm]" in df.columns:
        df["Precipitation total [mm]"] = (
            df["Precipitation total [mm]"] * 1000
        )
    if "Soil moisture [%]" in df.columns:
        df["Soil moisture [%]"] = df["Soil moisture [%]"] * 100

    # Convert hourly data to daily values. Instantaneous variables use the
    # configured method; accumulated precipitation must be summed and its
    # timestamp shifted back to the hour represented by the accumulation.
    methods = (
        within_source_aggregation_methods
        or WITHIN_SOURCE_AGGREGATION_METHODS
    )
    keys = ['lat', 'lon']
    precipitation_column = "Precipitation total [mm]"
    value_columns = [
        column for column in df.columns
        if column not in {*keys, 'Timestamp'}
    ]
    instantaneous_columns = [
        column for column in value_columns
        if column != precipitation_column
    ]
    daily_frames = []
    if instantaneous_columns:
        instantaneous = df[keys + instantaneous_columns].copy()
        instantaneous['day'] = pd.to_datetime(df['Timestamp']).dt.date
        daily_frames.append(
            aggregate_to_s2(
                instantaneous,
                group_by=('day', 'lat', 'lon'),
                logical_data_types=data_range,
                methods=methods,
            ).reset_index()
        )
    if precipitation_column in df.columns:
        accumulated = df[keys + [precipitation_column]].copy()
        accumulated['day'] = (
            pd.to_datetime(df['Timestamp']) - pd.Timedelta(hours=1)
        ).dt.date
        daily_frames.append(
            aggregate_to_s2(
                accumulated,
                group_by=('day', 'lat', 'lon'),
                logical_data_types=data_range,
                methods=methods,
                column_aggregations={precipitation_column: 'sum'},
            ).reset_index()
        )

    if not daily_frames:
        return pd.DataFrame()
    df = daily_frames[0]
    for daily_frame in daily_frames[1:]:
        df = df.merge(daily_frame, on=['day', 'lat', 'lon'], how='outer')
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
        methods=(within_source_aggregation_methods
                 or WITHIN_SOURCE_AGGREGATION_METHODS),
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

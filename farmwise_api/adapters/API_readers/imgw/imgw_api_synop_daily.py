import asyncio
import httpx
import pandas as pd
import warnings
from farmwise_api.adapters.mappings.data_source_mapping import WITHIN_SOURCE_AGGREGATION_METHODS
from farmwise_api.core.within_source_aggregation import aggregate_to_s2
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from zipfile import ZipFile
import io
from farmwise_api.adapters.API_readers.imgw.imgw_mappings.synop_mapping import s_d_COLUMNS, s_d_SELECTION, s_d_t_COLUMNS, s_d_t_SELECTION, DATA_ALIASES, GLOBAL_MAPPING
from tqdm import tqdm
from farmwise_api.core.utils.coordinates_to_cells import prepare_coordinates
from farmwise_api.core.utils.imgw_utils import create_timestamp_from_row, expand_range, get_years_between_dates
from farmwise_api.core.utils.access_policy import require_private_noncommercial_imgw
from farmwise_api.core.utils.paths import adapter_data
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

URL = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_meteorologiczne/dobowe/synop"
SPACE_TIME_COLUMNS = ['Station code', 'Year', 'Month', 'Day', 'Code', 'lat', 'lon', 'Name']
_MONTHLY_ARCHIVE_RE = re.compile(
    r"^(?P<year>\d{4})_(?P<month>0[1-9]|1[0-2])_s\.zip$",
    re.IGNORECASE,
)

_STATION_ARCHIVE_RE = re.compile(
    r"^(?:\d{4}(?:_\d{4})?)_(?P<station>\d{3,})_s\.zip$",
    re.IGNORECASE,
)


def _select_synop_archives(file_names, station_keys, time_range):
    """Select IMGW SYNOP archives for both station- and month-based layouts."""

    requested_months = {
        (period.year, period.month)
        for period in pd.period_range(
            time_range[0],
            time_range[1],
            freq="M",
        )
    }

    selected = []

    for file_name in file_names:
        basename = file_name.rsplit("/", 1)[-1]

        # New layout, e.g. 2026_08_s.zip:
        # one archive contains all SYNOP stations for one month.
        monthly_match = _MONTHLY_ARCHIVE_RE.fullmatch(basename)

        if monthly_match:
            year_month = (
                int(monthly_match.group("year")),
                int(monthly_match.group("month")),
            )

            if year_month in requested_months:
                selected.append(file_name)

            continue

        # Historical layout, e.g.
        # 2025_100_s.zip
        # 1966_1970_100_s.zip
        station_match = _STATION_ARCHIVE_RE.fullmatch(basename)

        if station_match:
            station = station_match.group("station")

            if not station_keys or station in station_keys:
                selected.append(file_name)

            continue

        # Future-proof fallback: if IMGW introduces another _s.zip layout,
        # do not silently discard it. Spatial filtering still happens later.
        if basename.lower().endswith("_s.zip"):
            selected.append(file_name)

    return selected

async def _get_with_retries(client, url, attempts=3):
    """Fetch an IMGW directory or archive with bounded transport retries."""
    for attempt in range(1, attempts + 1):
        try:
            response = await client.get(url, timeout=60)
            # Avoid invoking the status helper for successful responses.  This
            # also keeps lightweight async test doubles compatible with the
            # real httpx response API, where raise_for_status is synchronous.
            if response.status_code >= 400:
                response.raise_for_status()
            return response
        except (httpx.TransportError, httpx.HTTPStatusError):
            if attempt == attempts:
                raise
            await asyncio.sleep(attempt)


async def read_data(spatial_range, time_range, data_range, level,
                    within_source_aggregation_methods=None) -> pd.DataFrame | None:
    """
    Read data from the IMGW-API for the specified spatial and time range, and data types.

    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param time_range: A tuple containing the start and end timestamps defining the time range.
    :param data_range: A list of data types requested.
                       Allowed data types: 'precipitation', 'sunlight', 'cloud cover', 'temperature',
                       'wind', 'pressure', 'humidity'.
    :param level: S2Cell level.
    :return: A DataFrame containing the requested data pivoted by Timestamp and S2CELL.
    """
    require_private_noncommercial_imgw()
    logger.info("DOWNLOADING: IMGW synop data")

    # Load and process the coordinates CSV asynchronously
    coors = pd.read_csv(
        adapter_data("imgw", "constants", "imgw_coordinates.csv")
    )
    coors = coors[~coors.isna().any(axis=1)]
    coordinates = prepare_coordinates(coordinates=coors, spatial_range=spatial_range, level=level)
    if coordinates is None:
        return None

    years = get_years_between_dates(*time_range)
    data_requested = set([k for k, v in DATA_ALIASES.items() if v in data_range])

    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await _get_with_retries(client, URL)
        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all links (assuming directory listing is in <a> tags)
        links = soup.find_all('a')

        # Extract folder names
        folders = [link['href'].replace('/','') for link in links if link['href'].endswith('/')]
        folders = [year for year in folders if re.match(r'^\d{4}(_\d{4})?$', year)]

        # Expand names for searching
        expanded_years = {}
        for item in folders:
            expanded_years.update(expand_range(item))

        if any(year not in expanded_years for year in years):
            warnings.warn("Requested year is not available from IMGW")
            return None
        read_urls = list(dict.fromkeys(
            urljoin(URL + '/', expanded_years[x])
            for x in years
        ))

    s_d_files = []

    # Process URLs
    station_keys = {
        str(int(value))
        for value in coordinates.get("Value", pd.Series(dtype=float)).dropna()
    }
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for url in tqdm(read_urls,total=len(read_urls)):
            try:
                response = await _get_with_retries(client, url)
                # Parse HTML to find file links
                soup = BeautifulSoup(response.text, 'html.parser')
                links = soup.find_all('a')
                file_names = [
                    link['href']
                    for link in links
                    if link.get('href', '').lower().endswith('.zip')
                ]
                # Recent IMGW folders contain one archive per station.  Only
                # fetch stations retained by the spatial preselection rather
                # than every station in Poland.
                matching_files = _select_synop_archives(
                    file_names,
                    station_keys,
                    time_range,
                )

                for file_name in matching_files:
                    zip_url = urljoin(url + '/', file_name)
                    try:
                        zip_response = await _get_with_retries(client, zip_url)
                    except (httpx.TransportError, httpx.HTTPStatusError) as error:
                        warnings.warn(f"Skipping unavailable IMGW archive {zip_url}: {error}")
                        continue

                    # Process zip files asynchronously
                    with ZipFile(io.BytesIO(zip_response.content)) as zip_ref:
                        for name in zip_ref.namelist():
                            if '_t' in name:
                                continue

                            s_d_file = pd.read_csv(zip_ref.open(name), encoding='windows-1250', names=s_d_COLUMNS)
                            data_selection = list(data_requested.intersection(set(s_d_SELECTION)))
                            data_selection += SPACE_TIME_COLUMNS
                            s_d_file = s_d_file.loc[:, s_d_file.columns.intersection(data_selection)]
                            s_d_files.append(s_d_file)
            except (httpx.TransportError, httpx.HTTPStatusError) as error:
                warnings.warn(f"IMGW server not responding for {url}: {error}")

    # Concatenate dataframes
    if not s_d_files:
        return pd.DataFrame()

    s_d = pd.concat(
        s_d_files,
        ignore_index=True,
    )

    s_d['Timestamp'] = s_d.apply(
        create_timestamp_from_row,
        axis=1,
    )

    s_d['Timestamp'] = s_d['Timestamp'].dt.date

    s_d_merged = s_d.merge(
        coordinates,
        left_on='Station code',
        right_on='Code',
    )
    # ``Value`` is the station identifier from IMGW's station catalogue.  It
    # is used to select archives but is metadata, not an observed factor.
    s_d_merged.drop(['Unnamed: 0', 'Value'], axis=1, errors='ignore', inplace=True)

    # Map to global names
    s_d_merged = s_d_merged.rename(GLOBAL_MAPPING, axis=1)

    # Convert columns to numeric and concatenate
    s_d_merged_values = s_d_merged.drop(columns=SPACE_TIME_COLUMNS + ['S2CELL', 'Timestamp']).apply(pd.to_numeric,
                                                                                                    errors='coerce')
    s_d_merged = pd.concat([s_d_merged[['Timestamp', 'S2CELL']], s_d_merged_values], axis=1)

    # Filter date range
    start, end = datetime.strptime(time_range[0], '%Y-%m-%d').date(), datetime.strptime(time_range[1],
                                                                                        '%Y-%m-%d').date()
    s_d_merged = s_d_merged[(s_d_merged.Timestamp >= start) & (s_d_merged.Timestamp <= end)]

    s_d_merged = aggregate_to_s2(
        s_d_merged,
        logical_data_types=data_range,
        methods=(within_source_aggregation_methods
                 or WITHIN_SOURCE_AGGREGATION_METHODS),
        column_aggregations={"lat": "mean", "lon": "mean"},
    )

    # Pivot the DataFrame asynchronously
    s_d_pivot = s_d_merged.reset_index().pivot(
        index='Timestamp', columns='S2CELL'
    )

    return s_d_pivot

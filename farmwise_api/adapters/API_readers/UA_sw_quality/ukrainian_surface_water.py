import logging
from io import StringIO
from urllib.parse import urljoin
import httpx
import pandas as pd
from bs4 import BeautifulSoup
from tqdm.asyncio import tqdm as async_tqdm
from farmwise_api.adapters.API_readers.UA_sw_quality.UA_sw_quality_mappings.UA_sw_quality_mapping import new_headers, DATA_ALIASES
from farmwise_api.adapters.mappings.data_source_mapping import WITHIN_SOURCE_AGGREGATION_METHODS
from farmwise_api.core.within_source_aggregation import aggregate_to_s2
from farmwise_api.core.utils.coordinates_to_cells import prepare_coordinates

logger = logging.getLogger(__name__)


base_url = 'https://data.gov.ua/dataset/surface-water-monitoring'


async def download_file_content(client, base_url):
    response = await client.get(base_url)
    response.raise_for_status()
    return response.content


# Function to clean CSV content
def load_and_clean_data(csv_content):
    try:
        df = pd.read_csv(StringIO(csv_content.decode('UTF-8-SIG')), delimiter=';', encoding='UTF-8-SIG',
                         on_bad_lines='skip')
        # drop unnecessary columns (w Ukrainian names)
        df.drop(df.columns[[1, 2, 3, 4]], axis=1, inplace=True)

        # Convert 'Controle_Date' to datetime format (yyyy-mm-dd)
        df['Controle_Date'] = pd.to_datetime(df['Controle_Date'], format='%Y-%m-%d', errors='coerce')

        # Drop any unnamed columns
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]

        return df
    except Exception as e:
        logger.warning("Failed to read CSV content: %s", e)
        return None


# Async function to scrape the website, download CSV files, clean them, and return a combined DataFrame
async def read_data(
    spatial_range,
    time_range,
    data_range,
    level,
    within_source_aggregation_methods=None,
) -> pd.DataFrame:
    """
        Read and process SURFACE WATER QUALITY data, filtering by spatial and time ranges, and return a MultiIndex DataFrame.

        :param spatial_range: Tuple (N, S, E, W) defining the bounding box.
        :param time_range: Tuple (start, end) of timestamps for filtering.
        :param data_range: List of requested data categories.
        :param level: S2Cell level for spatial aggregation.
        :return: DataFrame with MultiIndex ['date', 'S2CELL'] and numeric measurement columns.
        """
    logger.info("DOWNLOADING: Ukrainian surface water quality data")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(base_url)
        soup = BeautifulSoup(response.content, 'html.parser')

        # Find all links to CSV files with class "resource-url-analytics"
        csv_links = []
        for link in soup.find_all('a', class_='resource-url-analytics'):
            href = link.get('href')
            if href and href.endswith('.csv') and 'output' in href:
                csv_links.append(urljoin(base_url, href))

        # Download and clean CSVs concurrently
        all_data = []

        async def process_csv(csv_url):
            csv_content = await download_file_content(client, csv_url)
            return load_and_clean_data(csv_content)

        for coro in async_tqdm.as_completed([process_csv(url) for url in csv_links], desc="Processing CSV files"):
            cleaned_df = await coro
            if cleaned_df is not None:
                all_data.append(cleaned_df)

    if not all_data:
        logger.warning("No Ukrainian surface water CSV files could be read.")
        return pd.DataFrame()

    # Combine all DataFrames into a single DataFrame. The blank-row drop used
    # to target the last per-file frame, leaving blank rows in the result.
    combined_df = pd.concat(all_data, ignore_index=True)
    combined_df.dropna(how='all', inplace=True)

    if len(combined_df.columns) == len(new_headers):
        combined_df.columns = new_headers
    else:
        logger.warning(
            "Number of columns does not match the number of custom headers."
        )

    unique_points = combined_df[['point_id', 'lat', 'lon']].drop_duplicates()
    unique_points = unique_points[pd.to_numeric(unique_points[['lat','lon']].stack(), errors='coerce')
                .unstack()
                .notna()
                .all(axis=1)]
    coordinates = prepare_coordinates(coordinates=unique_points, spatial_range=spatial_range, level=level)
    if coordinates is None or coordinates.empty:
        logging.info("No coordinates within spatial range.")
        return pd.DataFrame()

    valid_ids = coordinates['point_id'].unique()
    combined_df = combined_df[combined_df['point_id'].isin(valid_ids)]

    time_from, time_to = pd.to_datetime(time_range[0]), pd.to_datetime(time_range[1])
    combined_df = combined_df[(combined_df['date'] >= time_from) & (combined_df['date'] <= time_to)]

    # Select numeric columns based on data_range
    category_columns = {col for col, cat in DATA_ALIASES.items() if cat in data_range}
    available_columns = [col for col in category_columns if col in combined_df.columns]
    if not available_columns:
        logging.warning("No data columns found for the requested categories.")
        return pd.DataFrame()

    # Ensure numeric columns
    cols_to_convert = [col for col in new_headers if col != "date"]
    combined_df[cols_to_convert] = combined_df[cols_to_convert].apply(pd.to_numeric, errors='coerce')

    final_df = combined_df[['point_id', 'date'] + available_columns]
    final_df = final_df.merge(coordinates[['point_id', 'S2CELL']], on='point_id')

    final_df = final_df.drop(columns=['point_id'])
    final_df = aggregate_to_s2(
        final_df,
        group_by=("date", "S2CELL"),
        logical_data_types=data_range,
        methods=(within_source_aggregation_methods
                 or WITHIN_SOURCE_AGGREGATION_METHODS),
        column_data_types=DATA_ALIASES,
    ).reset_index()

    return final_df.pivot(index='date', columns='S2CELL')

import asyncio
import httpx
import pandas as pd
import logging
import nest_asyncio
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from io import BytesIO
from tqdm.asyncio import tqdm
from pyproj import Transformer
from API_readers.gios_gw.gios_gw_mappings.gios_gw_mapping import selected_columns, DATA_ALIASES, schema
from utils.coordinates_to_cells import prepare_coordinates

# Apply nest_asyncio for interactive environments
nest_asyncio.apply()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize transformer for coordinate conversion
transformer = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)
URL = 'https://mjwp.gios.gov.pl/wyniki-badan/wyniki-badan-2023.html'


async def find_subpage_links(url: str, client: httpx.AsyncClient) -> list:
    """Fetch the main page and extract subpage links containing 'wyniki-badan'."""
    try:
        response = await client.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        links = [urljoin(url, link.get('href')) for link in
                 soup.find_all('a', href=lambda href: href and 'wyniki-badan' in href)]
        logging.info(f"Found {len(links)} subpage links on main page.")
        return links
    except httpx.RequestError as e:
        logging.error(f"Error fetching main page: {e}")
        return []


async def find_xlsx_links(url: str, client: httpx.AsyncClient) -> list:
    """Fetch a subpage and extract all .xlsx file links with cleaned file names."""
    try:
        response = await client.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        links = [(urljoin(url, link.get('href')), link.get_text(strip=True).replace('/', '-'))
                 for link in soup.find_all('a', href=lambda href: href and href.lower().endswith('.xlsx'))]
        logging.info(f"Found {len(links)} xlsx links on subpage {url}.")
        return links
    except httpx.RequestError as e:
        logging.error(f"Error fetching subpage {url}: {e}")
        return []


async def process_xlsx(url: str, client: httpx.AsyncClient) -> pd.DataFrame:
    """Download and read an Excel file into a DataFrame."""
    try:
        response = await client.get(url)
        response.raise_for_status()
        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(None, pd.read_excel, BytesIO(response.content))
        logging.info(f"Processed file from {url} with shape {df.shape}.")
        return df
    except httpx.RequestError as e:
        logging.error(f"Error fetching xlsx file {url}: {e}")
    except Exception as e:
        logging.error(f"Error processing xlsx file {url}: {e}")
    return pd.DataFrame()


def convert_coords(df: pd.DataFrame) -> pd.DataFrame:
    """Convert coordinates from EPSG:2180 to EPSG:4326."""
    try:
        if 'PUWG 1992 X' in df.columns and 'PUWG 1992 Y' in df.columns:
            coords = transformer.transform(df['PUWG 1992 X'].values, df['PUWG 1992 Y'].values)
            df['lon'], df['lat'] = coords
            df = df.drop(columns=["PUWG 1992 X", "PUWG 1992 Y"])
    except Exception as e:
        logging.error(f"Error converting coordinates: {e}")
    return df


def standardize_dataframe(df, schema):
    """
    Standardize a DataFrame to a predefined schema by reindexing and converting data types.

    :param df: Input DataFrame with renamed columns.
    :param schema: Dictionary mapping column names to their expected data types.
    :return: Standardized DataFrame.
    """
    # Convert coordinates
    df = convert_coords(df)

    # Reindex to schema columns
    standard_columns = list(schema.keys())
    df = df.reindex(columns=standard_columns)

    # Clean and convert data types
    for col, dtype in schema.items():
        if col in df.columns:
            if dtype in ['float', 'int']:
                df[col] = df[col].astype(str).str.replace(',', '.').str.replace('<', '')
                df[col] = pd.to_numeric(df[col], errors='coerce')
                if dtype == 'int':
                    df[col] = df[col].astype('Int64')
            elif dtype == 'Timestamp':
                df[col] = pd.to_datetime(df[col], format='%d.%m.%Y', errors='coerce')
            elif dtype == 'category':
                df[col] = df[col].astype('category')

    return df


async def read_data(spatial_range, time_range, data_range, level):
    """
    Read and process groundwater data, filtering by spatial and time ranges, and return a MultiIndex DataFrame.

    :param spatial_range: Tuple (N, S, E, W) defining the bounding box.
    :param time_range: Tuple (start, end) of timestamps for filtering.
    :param data_range: List of requested data categories.
    :param level: S2Cell level for spatial aggregation.
    :return: DataFrame with MultiIndex ['date', 'S2CELL'] and numeric measurement columns.
    """
    print("DOWNLOADING: GIOS groundwater q&q data")
    async with httpx.AsyncClient(timeout=30) as client:
        subpage_links = await find_subpage_links(URL, client)
        if not subpage_links:
            logging.warning("No subpage links found.")
            return pd.DataFrame()

        xlsx_links = [item for sublist in
                      await asyncio.gather(*[find_xlsx_links(subpage, client) for subpage in subpage_links])
                      for item in sublist]
        if not xlsx_links:
            logging.warning("No xlsx links found.")
            return pd.DataFrame()

        all_data = []
        for xlsx_url, _ in tqdm(xlsx_links, desc="Processing files"):
            df = await process_xlsx(xlsx_url, client)
            if not df.empty:
                valid_columns = [col for col in selected_columns.keys() if col in df.columns]
                if valid_columns:
                    df = df[valid_columns].rename(columns=selected_columns)
                    df = standardize_dataframe(df, schema)
                    # Only append if DataFrame has non-NA data for measurement columns
                    measurement_cols = [col for col in df.columns if col not in ['id', 'date', 'lat', 'lon']]
                    if measurement_cols and not df[measurement_cols].isna().all().all():
                        all_data.append(df)
                    else:
                        logging.info(f"Skipped empty or all-NA DataFrame from {xlsx_url}")

        if not all_data:
            logging.warning("No valid data collected from any file.")
            return pd.DataFrame()

        final_df = pd.concat(all_data, ignore_index=True)
        final_df.dropna(how='all', inplace=True)

        unique_points = final_df[['id', 'lat', 'lon']].drop_duplicates()
        coordinates = prepare_coordinates(coordinates=unique_points, spatial_range=spatial_range, level=level)
        if coordinates is None or coordinates.empty:
            logging.info("No coordinates within spatial range.")
            return pd.DataFrame()

        valid_ids = coordinates['id'].unique()
        final_df = final_df[final_df['id'].isin(valid_ids)]

        time_from, time_to = pd.to_datetime(time_range[0]), pd.to_datetime(time_range[1])
        final_df = final_df[(final_df['date'] >= time_from) & (final_df['date'] <= time_to)]

        # Select numeric columns based on data_range
        category_columns = {col for col, cat in DATA_ALIASES.items() if cat in data_range}
        available_columns = [col for col in category_columns if col in final_df.columns]
        if not available_columns:
            logging.warning("No data columns found for the requested categories.")
            return pd.DataFrame()

        # Ensure numeric columns
        final_df[available_columns] = final_df[available_columns].apply(pd.to_numeric, errors='coerce')

        final_df = final_df[['id', 'date'] + available_columns]
        final_df = final_df.merge(coordinates[['id', 'S2CELL']], on='id')

        # Set MultiIndex
        final_df = final_df.set_index(['date', 'S2CELL'])

        # Pivot the DataFrame asynchronously
        final_df_pivot = final_df.pivot_table(index='date', columns='S2CELL')
        return final_df_pivot

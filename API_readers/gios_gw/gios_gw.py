import asyncio
import httpx
import pandas as pd
import numpy as np
import logging
import nest_asyncio
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from io import BytesIO
from tqdm.asyncio import tqdm
from pyproj import Transformer
from gios_gw_mappings.gios_gw_mapping import selected_columns

# Apply nest_asyncio for interactive environments.
nest_asyncio.apply()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize transformer for coordinate conversion.
transformer = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)
URL = 'https://mjwp.gios.gov.pl/wyniki-badan/wyniki-badan-2023.html'


async def find_subpage_links(url: str, client: httpx.AsyncClient) -> list:
    """Fetch the main page and extract subpage links that contain 'wyniki-badan'."""
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
    """Fetch a subpage and extract all .xlsx file links along with a cleaned file name."""
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
    """Download and read an Excel file into a DataFrame using a thread pool."""
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
    """Convert coordinates using the pyproj transformer, vectorized for performance."""
    try:
        if 'PUWG 1992 X' in df.columns and 'PUWG 1992 Y' in df.columns:
            coords = transformer.transform(df['PUWG 1992 X'].values, df['PUWG 1992 Y'].values)
            df['lat'], df['lon'] = coords
            df = df.drop(columns=["PUWG 1992 X", "PUWG 1992 Y"])
    except Exception as e:
        logging.error(f"Error converting coordinates: {e}")
    return df


def convert_to_float(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize string representations of numbers directly on DataFrame."""
    for col in df.select_dtypes(include=['object']).columns:
        if col not in ['Range of Captured Aquifer Layer', 'date']:
            df[col] = df[col].str.replace(',', '.').str.replace('<', '').astype(float, errors='ignore')
    return df


async def read_data(url: str) -> pd.DataFrame:
    all_data = []
    async with httpx.AsyncClient(timeout=30) as client:
        subpage_links = await find_subpage_links(url, client)
        if not subpage_links:
            logging.warning("No subpage links found. Exiting.")
            return pd.DataFrame()

        xlsx_links = [item for sublist in
                      await asyncio.gather(*[find_xlsx_links(subpage, client) for subpage in subpage_links]) for item in
                      sublist]
        logging.info(f"Total xlsx files found: {len(xlsx_links)}")
        if not xlsx_links:
            logging.warning("No xlsx links found. Exiting.")
            return pd.DataFrame()

        for xlsx_url, _ in tqdm(xlsx_links, desc="Processing files"):
            df = await process_xlsx(xlsx_url, client)
            if not df.empty:
                valid_columns = [col for col in selected_columns.keys() if col in df.columns]
                if valid_columns:
                    df = df[valid_columns].rename(columns=selected_columns)
                    df = convert_coords(df)
                    df = convert_to_float(df)

                    if 'id' in df.columns:
                        df['id'] = pd.to_numeric(df['id'], errors='coerce').fillna(0).astype(int)

                    if 'year' in df.columns:
                        df['year'] = pd.to_datetime(df['year'], format='%Y', errors='coerce')

                    # Clean "Type of Measurement Point".
                    df.replace({
                        "n.o.": np.nan, "b.d.": np.nan, "brak danych": np.nan,
                        "st. wiercona": "well", "st. kopana": "well",
                        "piezometr": "piezometer", "źródło": "spring",
                        "łata wodowskazowa": "water level gauge",
                        "szyb kopalniany": "mineshaft", "otw badawczy": "test hole"
                    }, inplace=True)

                    # Date parsing and fallback logic
                    if 'year' in df.columns:
                        year_dates = pd.to_datetime(df['year'], format='%Y', errors='coerce')
                    else:
                        year_dates = None

                    if 'date' in df.columns:
                        sample_dates = pd.to_datetime(df['date'], errors='coerce', dayfirst=True)
                        df['date'] = sample_dates.where(sample_dates.notna(), other=year_dates)
                    elif year_dates is not None:
                        df['date'] = year_dates

                    df.drop(columns=["year"], inplace=True, errors='ignore')

                    if not df.isna().all().all():
                        all_data.append(df)

    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        final_df.dropna(how='all', inplace=True)
        if 'id' in final_df.columns:
            final_df = final_df.sort_values(by="id").reset_index(drop=True)
        if 'id' in final_df.columns:
            final_df = final_df[['id'] + [col for col in final_df.columns if col != 'id']]
        logging.info(f"Final DataFrame shape: {final_df.shape}")
        return final_df
    else:
        logging.warning("No data was collected from any file.")
        return pd.DataFrame()


async def main():
    final_data = await read_data(URL)
    if final_data.empty:
        logging.info("The final DataFrame is empty.")
    else:
        logging.info(f"Final DataFrame has {final_data.shape[0]} rows and {final_data.shape[1]} columns.")
        print(final_data.head())


if __name__ == "__main__":
    asyncio.run(main())
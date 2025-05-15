import asyncio
import httpx
from bs4 import BeautifulSoup
import pandas as pd
from io import StringIO
from urllib.parse import urljoin
from tqdm.asyncio import tqdm as async_tqdm  # tqdm-compatible async wrapper

# URL of the website containing the dataset
url = 'https://data.gov.ua/dataset/surface-water-monitoring'

# Async function to download a file from a given URL and return the content
async def download_file_content(client, url):
    response = await client.get(url)
    response.raise_for_status()  # Ensure we notice bad responses
    return response.content

# Function to clean CSV content
def load_and_clean_data(csv_content):
    try:
        df = pd.read_csv(StringIO(csv_content.decode('UTF-8-SIG')), delimiter=';', encoding='UTF-8-SIG',
                         on_bad_lines='skip')
        df.drop(df.columns[[1, 2, 3, 4]], axis=1, inplace=True)

        # Convert 'Controle_Date' to datetime format (yyyy-mm-dd)
        df['Controle_Date'] = pd.to_datetime(df['Controle_Date'], format='%Y-%m-%d', errors='coerce')

        # Drop any unnamed columns
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]

        return df
    except Exception as e:
        print(f"Failed to read CSV content: {e}")
        return None

# Async function to scrape the website, download CSV files, clean them, and return a combined DataFrame
async def read_data(base_url):
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
        dfs = []

        async def process_csv(csv_url):
            csv_content = await download_file_content(client, csv_url)
            return load_and_clean_data(csv_content)

        for coro in async_tqdm.as_completed([process_csv(url) for url in csv_links], desc="Processing CSV files"):
            cleaned_df = await coro
            if cleaned_df is not None:
                dfs.append(cleaned_df)

    # Combine all DataFrames into a single DataFrame
    combined_df = pd.concat(dfs, ignore_index=True)

    # Add custom headers if the number of columns matches
    custom_headers = ['point_id', 'lat', 'lon', 'date', 'nitrogen', 'BOD5', 'suspended_solids', 'oxygen',
                      'sulfate', 'chloride', 'ammonium', 'nitrate', 'nitrite', 'phosphate', 'SPAR', 'permanganate',
                      'COD', 'phytoplankton', 'altrazine', 'simazine']

    if len(combined_df.columns) == len(custom_headers):
        combined_df.columns = custom_headers
    else:
        print("Warning: Number of columns does not match the number of custom headers.")

    # Sort the combined DataFrame by 'point_id' and 'date'
    combined_df_sorted = combined_df.sort_values(by=['point_id', 'date'], ascending=True)

    return combined_df_sorted


# Run the async main routine and get the result
if __name__ == "__main__":
    combined_df_sorted = asyncio.run(read_data(url))

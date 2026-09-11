import pandas as pd
import aiohttp
import aiofiles
import asyncio
from bs4 import BeautifulSoup
import requests
from pathlib import Path
import json
import logging
from datetime import datetime
import time

logger = logging.getLogger(__name__)

# Constants
BASE_URL = "https://opendata.chmi.cz/meteorology/climate/historical/data/daily/"
DOWNLOAD_DIR = Path("downloaded_json")
DOWNLOAD_DIR.mkdir(exist_ok=True, parents=True)
BATCH_SIZE = 5
FINAL_COLS = ['station_ID', 'date', 'lat', 'lon', 'precipitation [mm]', 'temperature [°c]']
CURRENT_DATE = datetime.now().strftime('%Y-%m-%dT00:00:00Z')


async def fetch_json_files():
    """Fetch or load cached JSON file list with timeout"""
    cache_file = Path("json_files_list.txt")
    if cache_file.exists():
        with open(cache_file, 'r') as f:
            return [line.strip() for line in f]

    try:
        # Add timeout to requests.get (e.g., 10 seconds)
        response = requests.get(BASE_URL, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes
        soup = BeautifulSoup(response.text, 'html.parser')
        json_files = [link['href'] for link in soup.find_all('a') if link.get('href', '').endswith('.json')]
        with open(cache_file, 'w') as f:
            f.write('\n'.join(json_files))
        return json_files
    except requests.exceptions.Timeout:
        logger.warning("Timeout occurred while fetching JSON file list.")
        return []
    except requests.exceptions.RequestException as e:
        logger.warning("Error fetching JSON file list: %s", e)
        return []


async def download_file(session, url, filepath):
    """Download single file with retry logic and timeout"""
    max_attempts = 3
    attempt = 1

    while attempt <= max_attempts:
        try:
            if not filepath.exists():
                # Set timeout for aiohttp request (e.g., 30 seconds total)
                timeout = aiohttp.ClientTimeout(total=30)
                async with session.get(url, timeout=timeout) as resp:
                    resp.raise_for_status()
                    content = await resp.read()
                    async with aiofiles.open(filepath, 'wb') as f:
                        await f.write(content)
                logger.debug("Downloaded: %s", filepath.name)
            return
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("Attempt %s failed for %s: %s", attempt, url, e)
            if attempt == max_attempts:
                logger.error("Max attempts reached for %s. Giving up.", url)
                raise
            attempt += 1
            await asyncio.sleep(2 ** attempt)  # Exponential backoff


async def download_missing_files(json_files):
    """Download all missing files concurrently with progress and batching"""
    async with aiohttp.ClientSession() as session:
        tasks = []
        total_files = len(json_files)
        semaphore = asyncio.Semaphore(BATCH_SIZE)  # Limit concurrent downloads

        async def bounded_download(url, filepath):
            async with semaphore:  # Limit concurrency
                await download_file(session, url, filepath)

        for i, f in enumerate(json_files, 1):
            filepath = DOWNLOAD_DIR / f
            url = BASE_URL + f
            try:
                filepath.parent.mkdir(parents=True, exist_ok=True)
                tasks.append(bounded_download(url, filepath))
            except Exception as e:
                logger.warning("Error preparing task for %s: %s", f, e)

        if tasks:
            for i, task in enumerate(asyncio.as_completed(tasks), 1):
                try:
                    await task
                    logger.debug("Download progress: %s/%s", i, total_files)
                except Exception as e:
                    logger.warning("Task failed: %s", e)
        else:
            logger.info("No files to download.")


async def load_json(file_path):
    """Load JSON file asynchronously"""
    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
        return json.loads(await f.read())


def process_metadata(meta_loc_data):
    """Process metadata into DataFrame"""
    header = meta_loc_data['data']['data']['header'].split(',')
    values = meta_loc_data['data']['data']['values']

    loc_df = pd.DataFrame(values, columns=header)
    loc_df = loc_df[['WSI', 'BEGIN_DATE', 'END_DATE', 'GEOGR1', 'GEOGR2']].rename(
        columns={
            'WSI': 'wsi',
            'BEGIN_DATE': 'begin_date',
            'END_DATE': 'end_date',
            'GEOGR1': 'lon',
            'GEOGR2': 'lat'
        }
    )

    for date_col in ['begin_date', 'end_date']:
        loc_df[date_col] = pd.to_datetime(
            loc_df[date_col].where(~loc_df[date_col].str.contains('3999'), '2262-01-01T00:00:00Z')
        )

    return loc_df


async def process_file(filepath, loc_df):
    """Extract and merge raw data from a single file"""
    start_time = time.time()
    try:
        data = await load_json(filepath)
        header = data['data']['data']['header'].split(',')
        values = data['data']['data']['values']

        if not values:
            logger.debug("Skipping %s: No data values found", filepath.name)
            return pd.DataFrame(columns=['station', 'element', 'dt', 'val', 'lat', 'lon'])

        df = pd.DataFrame(values, columns=header)
        df = df.rename(columns={
            'STATION': 'station',
            'ELEMENT': 'element',
            'DT': 'dt',
            'VAL': 'val'
        })[['station', 'element', 'dt', 'val']]

        if df.empty or df[['station', 'element', 'dt', 'val']].replace('', pd.NA).isna().all().all():
            logger.debug("Skipping %s: All columns empty or NA", filepath.name)
            return pd.DataFrame(columns=['station', 'element', 'dt', 'val', 'lat', 'lon'])

        df = df[df['element'].isin(['SRA', 'T'])]
        if df.empty:
            logger.debug("Skipping %s: No 'SRA' or 'T' elements found", filepath.name)
            return pd.DataFrame(columns=['station', 'element', 'dt', 'val', 'lat', 'lon'])

        df['dt'] = pd.to_datetime(df['dt'], errors='coerce')
        df['dt'] = df['dt'].where(df['dt'].dt.year <= datetime.now().year, pd.to_datetime(CURRENT_DATE))
        df['val'] = pd.to_numeric(df['val'], errors='coerce')

        # Merge with location data immediately
        merged_df = (df.merge(loc_df, left_on='station', right_on='wsi', how='left')
                     .query('dt >= begin_date and dt <= end_date')
                     .drop(['wsi', 'begin_date', 'end_date'], axis=1))

        logger.debug(
            "Processed: %s in %.2fs (Rows: %s)",
            filepath.name,
            time.time() - start_time,
            len(merged_df),
        )
        return merged_df

    except Exception as e:
        logger.warning("Error processing %s: %s", filepath.name, e)
        return pd.DataFrame(columns=['station', 'element', 'dt', 'val', 'lat', 'lon'])


async def process_batch(files, loc_df):
    """Process batch of files and collect raw data"""
    semaphore = asyncio.Semaphore(5)
    async with semaphore:
        start_time = time.time()
        total_files = len(files)
        batch_dfs = []
        tasks = [process_file(f, loc_df) for f in files]
        for i, task in enumerate(asyncio.as_completed(tasks), 1):
            df = await task
            if not df.empty and not df.isna().all().all():
                batch_dfs.append(df)
            logger.debug(
                "Batch progress: %s/%s (Collected rows: %s)",
                i,
                total_files,
                sum(len(d) for d in batch_dfs),
            )
        batch_df = pd.concat(batch_dfs, ignore_index=True) if batch_dfs else pd.DataFrame(
            columns=['station', 'element', 'dt', 'val', 'lat', 'lon'])
        logger.debug(
            "Batch completed in %.2fs (Total rows: %s)",
            time.time() - start_time,
            len(batch_df),
        )
    return batch_df


async def read_data(metadata_loc_file, max_files=None) -> pd.DataFrame:
    """Main execution function with single final pivot and aggregation"""
    start_time = time.time()
    meta_loc = await load_json(metadata_loc_file)
    loc_df = process_metadata(meta_loc)
    logger.debug("Metadata processed in %.2fs", time.time() - start_time)

    json_files = await fetch_json_files()

    if max_files is not None:
        json_files = json_files[:max_files]
        logger.info("Limited to %s files for testing.", len(json_files))

    await download_missing_files(json_files)

    filepaths = [DOWNLOAD_DIR / f for f in json_files]
    batches = [filepaths[i:i + BATCH_SIZE] for i in range(0, len(filepaths), BATCH_SIZE)]

    logger.info("Total batches to process: %s", len(batches))
    all_dfs = []
    for i, batch in enumerate(batches):
        batch_start = time.time()
        batch_df = await process_batch(batch, loc_df)
        if not batch_df.empty:
            all_dfs.append(batch_df)
        logger.debug(
            "Completed batch %s/%s in %.2fs (Cumulative time: %.2fs)",
            i + 1,
            len(batches),
            time.time() - batch_start,
            time.time() - start_time,
        )

    # Merge all data once
    merge_start = time.time()
    merged_df = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame(
        columns=['station', 'element', 'dt', 'val', 'lat', 'lon'])
    logger.debug(
        "Merged all data in %.2fs (Rows: %s)",
        time.time() - merge_start,
        len(merged_df),
    )

    # Single pivot and aggregation
    if not merged_df.empty:
        pivot_start = time.time()
        result = (merged_df.pivot(index=['station', 'dt', 'lat', 'lon'],
                                  columns='element',
                                  values='val')
                  .reset_index()
                  .rename(columns={'SRA': 'precipitation [mm]', 'T': 'temperature [°c]'}))
        logger.debug("Final pivot took %.2fs", time.time() - pivot_start)

        for col in FINAL_COLS[4:]:
            if col not in result:
                result[col] = pd.NA

        result['date'] = result['dt'].dt.date
        agg_start = time.time()
        final_df = (result.groupby(['station', 'date', 'lat', 'lon'], observed=True)
            .agg({'precipitation [mm]': 'sum', 'temperature [°c]': 'mean'})
            .reset_index()
            .rename(columns={'station': 'station_ID'})[FINAL_COLS])
        logger.debug("Final aggregation took %.2fs", time.time() - agg_start)
    else:
        final_df = pd.DataFrame(columns=FINAL_COLS)

    logger.info("Final shape: %s", final_df.shape)
    logger.info("Total processing time: %.2fs", time.time() - start_time)
    final_df.to_csv('CHMI_merged_data.csv', index=False)
    return final_df


if __name__ == "__main__":
    final_df = asyncio.run(read_data('dly-0-20000-0-11406.json'))
    print(final_df.head())

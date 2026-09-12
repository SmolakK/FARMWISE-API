import pandas as pd
import httpx
import asyncio
import zipfile
import io
import logging
from typing import Optional
from farmwise_api.core.utils.coordinates_to_cells import prepare_coordinates
from farmwise_api.adapters.API_readers.epa_ireland.epa_ireland_mappings.epa_ireland_mapping import DATA_ALIASES, GLOBAL_MAPPING
from farmwise_api.adapters.mappings.units import GROUNDWATER_LEVEL_COLUMN
from farmwise_api.adapters.mappings.data_source_mapping import WITHIN_SOURCE_AGGREGATION_METHODS
from farmwise_api.core.within_source_aggregation import aggregate_to_s2
from farmwise_api.core.utils.paths import adapter_data

logger = logging.getLogger(__name__)

coordinates = adapter_data("epa_ireland", "constants", "EPA_coordinates.csv")
initial_df = pd.read_csv(coordinates, sep=',', header=0)


async def process_link(client: httpx.AsyncClient, row: pd.Series) -> Optional[pd.DataFrame]:
    id = row['id']
    link = row['download_link']

    try:
        logger.debug("Downloading data for %s from %s", id, link)
        async with client.stream('GET', link) as response:
            response.raise_for_status()
            content = await response.aread()

        with zipfile.ZipFile(io.BytesIO(content)) as z:
            csv_filename = z.namelist()[0]  # Assumes one CSV per ZIP
            with z.open(csv_filename) as csv_file:
                df = pd.read_csv(
                    csv_file,
                    skiprows=7,
                    sep=';',
                    usecols=[0, 1],
                    names=['timestamp', 'groundwater level [m OD Malin]'],
                    header=0,
                    parse_dates=['timestamp']
                )

                df['id'] = id
                df['lat'] = row['lat']
                df['lon'] = row['lon']

                return df

    except Exception as e:
        logger.warning("Error processing %s from %s: %s", id, link, e)
        return None


# Async function to fetch all data
async def fetch_all_data():
    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = []
        for _, row in initial_df.iterrows():
            link = row['download_link']
            id = row['id']

            if pd.isna(link) or not isinstance(link, str) or not link.endswith('.zip'):
                logger.debug(
                    "Skipping %s: Invalid or missing download link", id
                )
                continue

            tasks.append(process_link(client, row))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results


async def read_data(
    spatial_range,
    time_range,
    data_range,
    level,
    within_source_aggregation_methods=None,
) -> pd.DataFrame:
    logger.info("DOWNLOADING: EPA GROUNDWATER QUANTITY DATA")
    results = await fetch_all_data()
    all_data = []

    # Process each result and apply initial filters
    for result in results:
        if result is None:
            continue
        df = result

        # Check if DataFrame has valid data before appending
        if (
                not df.empty
                and not df['groundwater level [m OD Malin]'].isna().all()
        ):
            all_data.append(df)

    # Handle case where no data is collected
    if not all_data:
        return pd.DataFrame()

    # Concatenate all collected DataFrames
    final_df = pd.concat(all_data, ignore_index=True)

    # Rename 'timestamp' to 'Timestamp'
    final_df = final_df.rename(
        columns={'timestamp': 'Timestamp'}
    )

    # Prepare coordinates for spatial filtering
    unique_points = final_df[['id', 'lat', 'lon']].drop_duplicates()
    coordinates = prepare_coordinates(coordinates=unique_points, spatial_range=spatial_range, level=level)

    # Handle case where coordinates are empty or None
    if coordinates is None or coordinates.empty:
        return pd.DataFrame()

    # Filter DataFrame based on valid IDs from coordinates
    valid_ids = coordinates['id'].unique()
    final_df = final_df[final_df['id'].isin(valid_ids)]

    # Apply additional time filter to ensure consistency
    time_from, time_to = pd.to_datetime(time_range[0]), pd.to_datetime(time_range[1])
    final_df = final_df[(final_df['Timestamp'] >= time_from) & (final_df['Timestamp'] <= time_to)]

    # Select numeric columns based on data_range
    category_columns = {col for col, cat in DATA_ALIASES.items() if cat in data_range}
    available_columns = [col for col in category_columns if col in final_df.columns]
    if not available_columns:
        logger.warning("No data columns found for the requested categories.")
        return pd.DataFrame()

    # Define measurement columns
    measurement_columns = available_columns
    final_df = final_df[['id', 'Timestamp'] + measurement_columns]

    # Merge with coordinates to include S2CELL
    final_df = final_df.merge(coordinates[['id', 'S2CELL']], on='id')

    final_df.Timestamp = pd.to_datetime(final_df.Timestamp).dt.date

    final_df = aggregate_to_s2(
        final_df.drop(columns=['id']),
        logical_data_types=data_range,
        methods=(within_source_aggregation_methods
                 or WITHIN_SOURCE_AGGREGATION_METHODS),
        column_data_types=DATA_ALIASES,
    )
    final_df = final_df.rename(
        GLOBAL_MAPPING,
        axis=1,
    )

    return final_df.reset_index().pivot(
        index='Timestamp',
        columns='S2CELL',
        values=[GROUNDWATER_LEVEL_COLUMN],
    )

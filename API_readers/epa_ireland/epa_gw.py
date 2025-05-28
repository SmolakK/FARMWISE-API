import pandas as pd
import httpx
import asyncio
import zipfile
import io
import logging
from typing import Optional, Any
from utils.coordinates_to_cells import prepare_coordinates
from API_readers.epa_ireland.epa_ireland_mappings.epa_ireland_mapping import DATA_ALIASES

coordinates = 'API_readers/epa_ireland/constants/EPA_coordinates.csv'
initial_df = pd.read_csv(coordinates, sep=',', header=0)


async def process_link(client: httpx.AsyncClient, row: pd.Series) -> Optional[pd.DataFrame]:
    id = row['id']
    link = row['download_link']

    try:
        print(f"Downloading data for {id} from {link}")
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
                    names=['timestamp', 'groundwater level [m]'],
                    header=0,
                    parse_dates=['timestamp']
                )
                df['id'] = id
                df['lat'] = row['lat']
                df['lon'] = row['lon']

                # Calculate depth to groundwater
                df['groundwater depth [m b.g.l]'] = row['measuring_point_height'] - df['groundwater level [m]']

                return df

    except Exception as e:
        print(f"Error processing {id} from {link}: {str(e)}")
        return None


# Async function to fetch all data
async def fetch_all_data() -> tuple[BaseException | Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = []
        for _, row in initial_df.iterrows():
            link = row['download_link']
            id = row['id']

            if pd.isna(link) or not isinstance(link, str) or not link.endswith('.zip'):
                print(f"Skipping {id}: Invalid or missing download link")
                continue

            tasks.append(process_link(client, row))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results


async def read_data(spatial_range, time_range, data_range, level):
    print("DOWNLOADING: EPA GROUNDWATER QUANTITY DATA")
    results = await fetch_all_data()
    all_data = []

    # Process each result and apply initial filters
    for result in results:
        if result is None:
            continue
        df = result

        # Check if DataFrame has valid data before appending
        if not df.empty and not df[['groundwater level [m]', 'groundwater depth [m b.g.l]']].isna().all().all():
            all_data.append(df)

    # Handle case where no data is collected
    if not all_data:
        return pd.DataFrame()

    # Concatenate all collected DataFrames
    final_df = pd.concat(all_data, ignore_index=True)

    # Drop 'groundwater level [m]' and rename 'timestamp' to 'date'
    final_df = final_df.drop('groundwater level [m]', axis=1)
    final_df = final_df.rename(columns={'timestamp': 'date'})

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
    final_df = final_df[(final_df['date'] >= time_from) & (final_df['date'] <= time_to)]

    # Select numeric columns based on data_range
    category_columns = {col for col, cat in DATA_ALIASES.items() if cat in data_range}
    available_columns = [col for col in category_columns if col in final_df.columns]
    if not available_columns:
        logging.warning("No data columns found for the requested categories.")
        return pd.DataFrame()

    # Define measurement columns
    measurement_columns = ['groundwater depth [m b.g.l]']
    final_df = final_df[['id', 'date'] + measurement_columns]

    # Merge with coordinates to include S2CELL
    final_df = final_df.merge(coordinates[['id', 'S2CELL']], on='id')

    # Set index and pivot the DataFrame
    final_df = final_df.set_index(['date', 'S2CELL'])
    final_df_pivot = final_df.pivot_table(index='date', columns='S2CELL', values=measurement_columns)

    return final_df_pivot

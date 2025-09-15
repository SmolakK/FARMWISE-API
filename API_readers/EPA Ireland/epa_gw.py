import pandas as pd
import httpx
import asyncio
import zipfile
import io
from typing import Optional, Any

coordinates = 'EPA_coordinates.csv'
column_names = ['station_id', 'station_name', 'lat', 'lon', 'station_link', 'download_link', 'measuring_point_height']
# Load initial coordinates data with explicit column names
initial_df = pd.read_csv(coordinates, sep=',', names=column_names, header=0)
required_columns = ['download_link', 'station_id', 'lat', 'lon', 'measuring_point_height']


async def process_link(client: httpx.AsyncClient, row: pd.Series) -> Optional[pd.DataFrame]:
    station_id = row['station_id']
    link = row['download_link']

    try:
        print(f"Downloading data for {station_id} from {link}")
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
                    header=0
                )
                df['station_id'] = station_id
                df['lat'] = row['lat']
                df['lon'] = row['lon']

                # Calculate depth to groundwater
                df['groundwater depth [m]'] = row['measuring_point_height'] - df['groundwater level [m]']

                return df

    except Exception as e:
        print(f"Error processing {station_id} from {link}: {str(e)}")
        return None


# Async function to fetch all data
async def fetch_all_data() -> tuple[BaseException | Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = []
        for _, row in initial_df.iterrows():
            link = row['download_link']
            station_id = row['station_id']

            if pd.isna(link) or not isinstance(link, str) or not link.endswith('.zip'):
                print(f"Skipping {station_id}: Invalid or missing download link")
                continue

            tasks.append(process_link(client, row))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results


def main() -> pd.DataFrame:
    results = asyncio.run(fetch_all_data())
    valid_dfs = [df for df in results if isinstance(df, pd.DataFrame)]

    if valid_dfs:
        final_df = pd.concat(valid_dfs, ignore_index=True)
        final_df = final_df[['station_id', 'lat', 'lon', 'timestamp', 'groundwater depth [m]']]
    else:
        print("No valid data retrieved. Creating empty DataFrame.")
        final_df = pd.DataFrame(columns=['station_id', 'lat', 'lon', 'timestamp', 'groundwater depth [m]'])

    final_df.to_csv('output.csv', index=False)
    return final_df



if __name__ == "__main__":
    result_df = main()


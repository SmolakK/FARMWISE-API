# import pandas as pd
# import httpx
# import asyncio
# import io
# import zipfile
# from typing import Tuple
#
# # Base URL template
# BASE_URL = "https://cli.fusio.net/cli/climate_data/webdata/mly{}.zip"
#
# # Headers to mimic a browser
# HEADERS = {
#     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
# }
#
#
# def generate_links(csv_file: str) -> pd.DataFrame:
#     try:
#         df = pd.read_csv(
#             csv_file,
#             dtype={"station name": int},
#             on_bad_lines="warn",
#             engine="python"
#         )
#     except pd.errors.ParserError as e:
#         print(f"Error reading CSV: {e}")
#         df = pd.read_csv(
#             csv_file,
#             usecols=["station name", "latitude", "longitude"],
#             dtype={"station name": int},
#             on_bad_lines="skip"
#         )
#
#     selected_df = df[["station name", "latitude", "longitude"]].copy()
#     selected_df["download_link"] = selected_df["station name"].apply(
#         lambda x: BASE_URL.format(int(x)) if not pd.isna(x) else "Invalid station name"
#     )
#     return selected_df
#
#
# async def check_link(client: httpx.AsyncClient, url: str) -> Tuple[str, int]:
#     try:
#         response = await client.head(url, headers=HEADERS, timeout=10)
#         return url, response.status_code
#     except httpx.RequestError as e:
#         print(f"Error checking {url}: {e}")
#         return url, 0
#
#
# async def download_and_process(client: httpx.AsyncClient, row: pd.Series) -> pd.DataFrame:
#     url = row["download_link"]
#     station_id = row["station name"]
#     lat = row["latitude"]
#     lon = row["longitude"]
#
#     try:
#         response = await client.get(url, headers=HEADERS, timeout=10)
#         response.raise_for_status()
#
#         with zipfile.ZipFile(io.BytesIO(response.content)) as z:
#             csv_name = f"mly{station_id}.csv"
#             if csv_name not in z.namelist():
#                 print(f"CSV {csv_name} not found in {url}")
#                 return pd.DataFrame()
#
#             with z.open(csv_name) as f:
#                 lines = f.read().decode("utf-8").splitlines()
#                 # Dynamically find the header row
#                 for i, line in enumerate(lines):
#                     if line.startswith("year,month"):
#                         skip = i
#                         break
#                 else:
#                     print(f"No data header found in {csv_name}")
#                     return pd.DataFrame()
#
#                 df = pd.read_csv(
#                     io.StringIO("\n".join(lines)),
#                     skiprows=skip,
#                     engine="python",
#                     on_bad_lines="skip"
#                 )
#
#                 df["date"] = pd.to_datetime(df[["year", "month"]].assign(day=1))
#                 processed_df = df[["date", "rain"]].copy()
#                 processed_df["id"] = station_id
#                 processed_df["lat"] = lat
#                 processed_df["lon"] = lon
#                 processed_df["precipitation [mm]"] = processed_df["rain"]
#                 processed_df = processed_df[["id", "lat", "lon", "date", "precipitation [mm]"]]
#
#                 print(f"Processed data for station {station_id}")
#                 return processed_df
#
#     except (httpx.RequestError, zipfile.BadZipFile, pd.errors.ParserError) as e:
#         print(f"Failed to process {url}: {e}")
#         return pd.DataFrame()
#
#
# async def process_working_links(df: pd.DataFrame) -> pd.DataFrame:
#     # Explicitly filter for working links
#     working_df = df[df["status"] == 200].copy()
#     if working_df.empty:
#         print("No working links (status 200) found.")
#         return pd.DataFrame()
#
#     print(f"\nProcessing {len(working_df)} working links:")
#     print(working_df[["station name", "download_link", "status"]])
#
#     async with httpx.AsyncClient() as client:
#         tasks = [download_and_process(client, row) for _, row in working_df.iterrows()]
#         results = await asyncio.gather(*tasks)
#
#     combined_df = pd.concat([df for df in results if not df.empty], ignore_index=True)
#     return combined_df
#
#
# async def main_async():
#     csv_file = "Irish_StationDetails.csv"
#     df = generate_links(csv_file)
#
#     # Check link statuses
#     links = df["download_link"].tolist()
#     async with httpx.AsyncClient() as client:
#         tasks = [check_link(client, link) for link in links]
#         status_results = await asyncio.gather(*tasks)
#     status_df = pd.DataFrame(status_results, columns=["download_link", "status"])
#     df_with_status = df.merge(status_df, on="download_link", how="left")
#
#     # Process only working links
#     combined_df = await process_working_links(df_with_status)
#
#     # Display results
#     print("\nStations with Link Status:")
#     print(df_with_status)
#
#     if not combined_df.empty:
#         print("\nCombined Precipitation Data:")
#         print(combined_df)
#         print(f"\nTotal rows: {len(combined_df)}")
#     else:
#         print("\nNo valid data was processed.")
#
#
# def main():
#     asyncio.run(main_async())
#
#
# if __name__ == "__main__":
#     main()

import pandas as pd
import httpx
import asyncio
import io
import zipfile
from typing import Tuple
import re

# Base URL template (daily data)
BASE_URL = "https://cli.fusio.net/cli/climate_data/webdata/mly{}.zip"

# Headers to mimic a browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def generate_links(csv_file: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(
            csv_file,
            dtype={"station name": int},
            on_bad_lines="warn",
            engine="python"
        )
    except pd.errors.ParserError as e:
        print(f"Error reading CSV: {e}")
        df = pd.read_csv(
            csv_file,
            usecols=["station name", "latitude", "longitude"],
            dtype={"station name": int},
            on_bad_lines="skip"
        )

    selected_df = df[["station name", "latitude", "longitude"]].copy()
    selected_df["download_link"] = selected_df["station name"].apply(
        lambda x: BASE_URL.format(int(x)) if not pd.isna(x) else "Invalid station name"
    )
    return selected_df

async def check_link(client: httpx.AsyncClient, url: str) -> Tuple[str, int]:
    try:
        response = await client.head(url, headers=HEADERS, timeout=10)
        return url, response.status_code
    except httpx.RequestError as e:
        print(f"Error checking {url}: {e}")
        return url, 0


async def download_and_process(client: httpx.AsyncClient, row: pd.Series) -> pd.DataFrame:
    url = row["download_link"]
    station_id = row["station name"]
    lat = row["latitude"]
    lon = row["longitude"]

    try:
        response = await client.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            csv_name = f"mly{station_id}.csv"
            if csv_name not in z.namelist():
                print(f"CSV {csv_name} not found in {url}")
                return pd.DataFrame()

            with z.open(csv_name) as f:
                lines = f.read().decode("utf-8").splitlines()
                for i, line in enumerate(lines):
                    if line.startswith("year,month"):
                        skip = i
                        break
                else:
                    print(f"No data header found in {csv_name}")
                    return pd.DataFrame()

                df = pd.read_csv(
                    io.StringIO("\n".join(lines)),
                    skiprows=skip,
                    engine="python",
                    on_bad_lines="skip"
                )

                df["date"] = pd.to_datetime(df[["year", "month"]].assign(day=1))
                processed_df = df[["date", "rain"]].copy()
                processed_df["id"] = station_id
                processed_df["lat"] = lat
                processed_df["lon"] = lon
                processed_df["precipitation [mm]"] = processed_df["rain"]
                processed_df = processed_df[["id", "lat", "lon", "date", "precipitation [mm]"]]

                print(f"Processed data for station {station_id}")
                return processed_df

    except httpx.RequestError as e:
        print(f"Failed to process {url} (HTTP error): {e}")
        return pd.DataFrame()
    except (zipfile.BadZipFile, pd.errors.ParserError) as e:
        print(f"Failed to process {url} (Zip/CSV error): {e}")
        with z.open(csv_name) as f:
            lines = f.read().decode("utf-8").splitlines()
            print(f"First 10 lines of {csv_name}:")
            for j, line in enumerate(lines[:10], 1):
                print(f"Line {j}: {line}")
        return pd.DataFrame()

async def process_working_links(df: pd.DataFrame) -> pd.DataFrame:
    working_df = df[df["status"] == 200].copy()
    if working_df.empty:
        print("No working links (status 200) found.")
        return pd.DataFrame()

    print(f"\nProcessing {len(working_df)} working links:")
    print(working_df[["station name", "download_link", "status"]])

    async with httpx.AsyncClient() as client:
        tasks = [download_and_process(client, row) for _, row in working_df.iterrows()]
        results = await asyncio.gather(*tasks)

    combined_df = pd.concat([df for df in results if not df.empty], ignore_index=True)
    return combined_df

async def main_async():
    csv_file = "EPA_ireland_stations.csv"
    df = generate_links(csv_file)

    # Check link statuses
    links = df["download_link"].tolist()
    async with httpx.AsyncClient() as client:
        tasks = [check_link(client, link) for link in links]
        status_results = await asyncio.gather(*tasks)
    status_df = pd.DataFrame(status_results, columns=["download_link", "status"])
    df_with_status = df.merge(status_df, on="download_link", how="left")

    # Process only working links
    combined_df = await process_working_links(df_with_status)

    # Display results
    print("\nStations with Link Status:")
    print(df_with_status)

    if not combined_df.empty:
        print("\nCombined Precipitation Data:")
        print(combined_df)
        print(f"\nTotal rows: {len(combined_df)}")
    else:
        print("\nNo valid data was processed.")

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()

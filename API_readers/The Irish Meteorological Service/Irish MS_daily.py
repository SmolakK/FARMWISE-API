import pandas as pd
import httpx
import asyncio
import io
import zipfile
from typing import Tuple
import re
from tqdm.asyncio import tqdm

BASE_URL = "https://cli.fusio.net/cli/climate_data/webdata/dly{}.zip"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}


def generate_links(csv_file: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(
            csv_file,
            dtype={"station name": str},
            on_bad_lines="warn",
            engine="python"
        )
    except pd.errors.ParserError:
        df = pd.read_csv(
            csv_file,
            usecols=["station name", "latitude", "longitude"],
            dtype={"station name": str},
            on_bad_lines="warn"
        )

    selected_df = df[["station name", "latitude", "longitude"]].copy()
    selected_df["download_link"] = selected_df["station name"].apply(
        lambda x: BASE_URL.format(int(x)) if pd.notna(x) and x.strip() else "Invalid station name"
    )
    return selected_df


async def check_link(client: httpx.AsyncClient, url: str) -> Tuple[str, int]:
    try:
        response = await client.head(url, headers=HEADERS, timeout=30)
        return url, response.status_code
    except httpx.RequestError:
        return url, 0


async def download_and_process(client: httpx.AsyncClient, row: pd.Series) -> pd.DataFrame:
    url = row["download_link"]
    station_id = row["station name"]
    lat = row["latitude"]
    lon = row["longitude"]

    for attempt in range(3):
        try:
            response = await client.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()

            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                csv_name = f"dly{station_id}.csv"
                if csv_name not in z.namelist():
                    return pd.DataFrame()

                with z.open(csv_name) as f:
                    lines = f.read().decode("utf-8").splitlines()
                    date_pattern = re.compile(r"^\d{2}-[a-z]{3}-\d{4}", re.IGNORECASE)
                    header_idx = None
                    for i, line in enumerate(lines):
                        if date_pattern.match(line.split(",")[0]):
                            header_idx = i - 1
                            break
                    else:
                        return pd.DataFrame()

                    df = pd.read_csv(
                        io.StringIO("\n".join(lines[header_idx:])),
                        engine="python",
                        on_bad_lines="skip"
                    )
                    if "date" not in df.columns or "rain" not in df.columns:
                        return pd.DataFrame()

                    df["date"] = pd.to_datetime(df["date"], format="%d-%b-%Y", errors="coerce")
                    processed_df = df[["date", "rain"]].copy()
                    processed_df["id"] = station_id
                    processed_df["lat"] = lat
                    processed_df["lon"] = lon
                    processed_df["precipitation [mm]"] = processed_df["rain"]
                    processed_df = processed_df[["id", "lat", "lon", "date", "precipitation [mm]"]]
                    return processed_df

        except httpx.RequestError:
            if attempt == 2:
                return pd.DataFrame()
            await asyncio.sleep(1)
        except (zipfile.BadZipFile, pd.errors.ParserError):
            return pd.DataFrame()


async def process_working_links(df: pd.DataFrame) -> pd.DataFrame:
    working_df = df[df["status"] == 200].copy()
    if working_df.empty:
        return pd.DataFrame()

    async with httpx.AsyncClient() as client:
        tasks = [download_and_process(client, row) for _, row in working_df.iterrows()]
        results = await tqdm.gather(*tasks, desc="Processing stations")

    valid_dfs = [result for result in results if isinstance(result, pd.DataFrame) and not result.empty]
    return pd.concat(valid_dfs, ignore_index=True) if valid_dfs else pd.DataFrame()


async def read_data() -> pd.DataFrame:
    csv_file = "EPA_ireland_stations.csv"
    df = generate_links(csv_file)

    async with httpx.AsyncClient() as client:
        tasks = [check_link(client, link) for link in df["download_link"]]
        status_results = await tqdm.gather(*tasks, desc="Checking links")
    status_df = pd.DataFrame(status_results, columns=["download_link", "status"])
    df_with_status = df.merge(status_df, on="download_link", how="left")

    combined_df = await process_working_links(df_with_status)
    return combined_df


def main():
    asyncio.run(read_data())


if __name__ == "__main__":
    main()

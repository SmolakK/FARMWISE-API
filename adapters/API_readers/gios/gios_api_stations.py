"""Build the static GIOŚ station-coordinate file.

This is a maintenance command, not a runtime adapter. Importing this module
does not perform network requests.
"""

from pathlib import Path

import pandas as pd
from tqdm import tqdm

from adapters.API_readers.gios.gios_utils import (
    extract_data,
    fetch_and_parse,
    generate_urls,
)
from core.utils.name_to_coordinates import get_coordinates

BASE_URL = "https://www.gios.gov.pl/chemizm_gleb/index.php?mod=pomiary&w="
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "constants" / "gios_coordinates.csv"


def build_station_file(output_path: Path = DEFAULT_OUTPUT) -> pd.DataFrame:
    """Download GIOŚ station names, geocode them, and persist a CSV file."""
    all_data = []
    for url in tqdm(generate_urls(BASE_URL), desc="Fetching URLs"):
        soup = fetch_and_parse(url)
        if soup is not None:
            all_data.extend(extract_data(soup))

    stations = pd.DataFrame(all_data)
    if stations.empty:
        return stations

    tqdm.pandas(desc="Fetching Coordinates")
    stations["coordinates"] = stations["name"].progress_apply(get_coordinates)
    stations[["lat", "lon"]] = pd.DataFrame(
        stations["coordinates"].tolist(),
        index=stations.index,
    )
    stations.drop(columns=["coordinates"], inplace=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    stations.to_csv(output_path, index=False)
    return stations


if __name__ == "__main__":
    result = build_station_file()
    print(f"Saved {len(result)} stations to {DEFAULT_OUTPUT}")

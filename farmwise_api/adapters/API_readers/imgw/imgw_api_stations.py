"""Build the static IMGW meteorological station-coordinate file."""

from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

from farmwise_api.core.utils.name_to_coordinates import get_coordinates
from farmwise_api.core.utils.access_policy import require_private_noncommercial_imgw

URL = (
    "https://danepubliczne.imgw.pl/data/"
    "dane_pomiarowo_obserwacyjne/dane_meteorologiczne/wykaz_stacji.csv"
)
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "constants" / "imgw_coordinates.csv"


def build_station_file(output_path: Path = DEFAULT_OUTPUT) -> pd.DataFrame:
    require_private_noncommercial_imgw()
    response = requests.get(URL, timeout=60)
    response.raise_for_status()
    response.encoding = "windows-1250"
    stations = pd.read_csv(
        StringIO(response.text),
        header=None,
        names=["Code", "Name", "Value"],
    )
    stations["Name"] = stations["Name"] + ",Poland"
    tqdm.pandas(desc="Processing")
    stations["coordinates"] = stations["Name"].progress_apply(get_coordinates)
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

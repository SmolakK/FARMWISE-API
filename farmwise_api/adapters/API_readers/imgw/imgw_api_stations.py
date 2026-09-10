"""Build the static IMGW meteorological station-coordinate file."""

from io import StringIO
from pathlib import Path

import pandas as pd
from geopy.extra.rate_limiter import RateLimiter
import requests
from tqdm import tqdm

from farmwise_api.core.utils.name_to_coordinates import get_coordinates
from farmwise_api.core.utils.access_policy import require_private_noncommercial_imgw

URL = (
    "https://danepubliczne.imgw.pl/data/"
    "dane_pomiarowo_obserwacyjne/dane_meteorologiczne/wykaz_stacji.csv"
)
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "constants" / "imgw_coordinates.csv"


def build_station_file(
    output_path: Path = DEFAULT_OUTPUT,
    *,
    synoptic_only: bool = True,
) -> pd.DataFrame:
    """Build coordinates for stations used by the daily synoptic adapter.

    The official station list also contains roughly two thousand climate and
    precipitation stations.  The adapter reads the ``dobowe/synop`` product,
    so geocoding those unrelated stations is both unnecessary and liable to
    exceed the public geocoder's rate limit.
    """
    require_private_noncommercial_imgw()
    response = requests.get(URL, timeout=60)
    response.raise_for_status()
    response.encoding = "windows-1250"
    stations = pd.read_csv(
        StringIO(response.text),
        header=None,
        names=["Code", "Name", "Value"],
    )
    if synoptic_only:
        station_class = pd.to_numeric(stations["Value"], errors="coerce")
        stations = stations.loc[station_class.between(0, 999)].copy()
    stations["Name"] = stations["Name"] + ",Poland"
    tqdm.pandas(desc="Processing")
    geocode = RateLimiter(
        get_coordinates,
        min_delay_seconds=1.1,
        swallow_exceptions=True,
    )
    stations["coordinates"] = stations["Name"].progress_apply(geocode)
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

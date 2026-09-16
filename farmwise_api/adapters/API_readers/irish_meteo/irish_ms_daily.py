import pandas as pd
from farmwise_api.core.utils.paths import adapter_cache
import httpx
import asyncio
import os
from uuid import uuid4
from pyproj import Transformer
from farmwise_api.core.utils.coordinates_to_cells import prepare_coordinates
from farmwise_api.adapters.API_readers.irish_meteo.irish_meteo_mappings.irish_meteo_mapping import GLOBAL_MAPPING
from farmwise_api.adapters.API_readers.irish_meteo.irish_meteo_mappings.irish_meteo_mapping import DATA_ALIASES
from farmwise_api.adapters.mappings.data_source_mapping import WITHIN_SOURCE_AGGREGATION_METHODS
from farmwise_api.core.within_source_aggregation import aggregate_to_s2

GRID_URL = (
    "https://clidata.met.ie/cli/grids_daily/latest/rain/"
    "IRL_DLY_RR_{year}_grid.csv.gz"
)

# The grid's daily totals are labelled with the day the morning-to-morning
# observation period starts, so most of each accumulation falls on the next
# UTC day. Output timestamps use that UTC day, consistent with ERA5 and the
# other daily sources. Evidence: paired with ERA5 over central Ireland (2018,
# four months), the grid value labelled D matched ERA5 day D+1 better than day
# D (Pearson r 0.63 vs 0.53, MAE 1.92 vs 2.06 mm). The window still straddles
# two UTC days, so no whole-day label can align it exactly.
GRID_TO_OUTPUT_DAY = pd.Timedelta(days=1)


async def read_data(
    spatial_range,
    time_range,
    data_range,
    level,
    within_source_aggregation_methods=None,
) -> pd.DataFrame:
    requested_start = pd.Timestamp(time_range[0])
    requested_end = pd.Timestamp(time_range[1])
    if requested_start > requested_end:
        raise ValueError("time_range start must not be after end")

    # Output day D is the grid column labelled D - 1, which may sit in the
    # previous year's file (1 January needs 31 December).
    grid_start = requested_start - GRID_TO_OUTPUT_DAY
    grid_end = requested_end - GRID_TO_OUTPUT_DAY

    yearly_frames = []
    async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
        for year in range(grid_start.year, grid_end.year + 1):
            dates = pd.date_range(
                max(grid_start, pd.Timestamp(year=year, month=1, day=1)),
                min(grid_end, pd.Timestamp(year=year, month=12, day=31)),
                freq="D",
            )
            grid_path = await _download_grid(client, year)
            yearly_frames.append(
                await asyncio.to_thread(
                    _read_grid_subset,
                    grid_path,
                    dates,
                    spatial_range,
                )
            )

    combined_df = pd.concat(yearly_frames, ignore_index=True)
    if combined_df.empty:
        return pd.DataFrame()
    combined_df["Timestamp"] = (
        pd.to_datetime(combined_df["Timestamp"]) + GRID_TO_OUTPUT_DAY
    ).dt.date
    combined_df = prepare_coordinates(combined_df, spatial_range, level)
    if combined_df is None or combined_df.empty:
        return pd.DataFrame()

    combined_df = aggregate_to_s2(
        combined_df[["Timestamp", "S2CELL", "precipitation [mm]"]],
        logical_data_types=data_range,
        methods=(within_source_aggregation_methods
                 or WITHIN_SOURCE_AGGREGATION_METHODS),
        column_data_types=DATA_ALIASES,
    )
    combined_df = combined_df.rename(GLOBAL_MAPPING, axis=1)

    return combined_df.reset_index().pivot(
        index='Timestamp',
        columns='S2CELL',
    )


async def _download_grid(client, year):
    """Download and cache one official Met Éireann annual rainfall grid."""
    filename = f"IRL_DLY_RR_{year}_grid.csv.gz"
    target = adapter_cache("irish_meteo") / filename
    if target.is_file():
        return target

    temporary = target.with_suffix(target.suffix + f".part-{uuid4().hex[:8]}")
    try:
        async with client.stream("GET", GRID_URL.format(year=year)) as response:
            response.raise_for_status()
            with open(temporary, "wb") as output:
                async for chunk in response.aiter_bytes():
                    output.write(chunk)
        os.replace(temporary, target)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def _read_grid_subset(path, dates, spatial_range):
    """Read requested days and bbox from a TM65 annual rainfall grid."""
    date_columns = {f"X{date:%Y%m%d}" for date in dates}
    requested_columns = {"east", "north", *date_columns}
    north, south, east, west = spatial_range

    to_tm65 = Transformer.from_crs("EPSG:4326", "EPSG:29902", always_xy=True)
    corners = [
        to_tm65.transform(lon, lat)
        for lon in (west, east)
        for lat in (south, north)
    ]
    eastings, northings = zip(*corners)
    projected_west, projected_east = min(eastings) - 1000, max(eastings) + 1000
    projected_south = min(northings) - 1000
    projected_north = max(northings) + 1000

    selected = []
    for chunk in pd.read_csv(
        path,
        compression="gzip",
        usecols=lambda column: column in requested_columns,
        chunksize=10_000,
    ):
        subset = chunk[
            chunk["east"].between(projected_west, projected_east)
            & chunk["north"].between(projected_south, projected_north)
        ]
        if not subset.empty:
            selected.append(subset)
    if not selected:
        return pd.DataFrame(
            columns=["lat", "lon", "Timestamp", "precipitation [mm]"]
        )

    frame = pd.concat(selected, ignore_index=True)
    to_wgs84 = Transformer.from_crs("EPSG:29902", "EPSG:4326", always_xy=True)
    frame["lon"], frame["lat"] = to_wgs84.transform(
        frame["east"].to_numpy(), frame["north"].to_numpy()
    )
    frame = frame[
        frame["lat"].between(south, north)
        & frame["lon"].between(west, east)
    ]
    frame = frame.melt(
        id_vars=["lat", "lon"],
        value_vars=sorted(date_columns),
        var_name="Timestamp",
        value_name="precipitation [mm]",
    )
    frame["Timestamp"] = pd.to_datetime(
        frame["Timestamp"].str.removeprefix("X"),
        format="%Y%m%d",
    ).dt.date
    # Values are published as tenths of a millimetre (e.g. 123 = 12.3 mm).
    frame["precipitation [mm]"] = (
        pd.to_numeric(frame["precipitation [mm]"], errors="coerce") / 10
    )
    return frame.dropna(subset=["precipitation [mm]"])

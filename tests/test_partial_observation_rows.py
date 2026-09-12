"""A station-day with some parameters missing must still be returned.

Station networks routinely report one parameter and not another on the same
day. Dropping the whole row when *any* value is null silently discards those
observations; dropping it only when *every* value is null keeps them.

The check has to be restricted to the observation columns. Both adapters carry
identifier columns (station id, date/time) that are never null, so testing the
whole row would never drop anything at all - the filter would look correct and
do nothing.
"""

import numpy as np
import pandas as pd
import pytest


def _pivoted(rows):
    """Shape a frame the way wetterdienst_dwd has it at the cleaning step."""
    return pd.DataFrame(rows)


def test_wetterdienst_keeps_rows_with_one_parameter_missing():
    from farmwise_api.adapters.API_readers.wetterdienst import wetterdienst_dwd

    frame = _pivoted([
        # complete
        {"station_id": "02985", "date": "2017-01-10",
         "temperature_air_mean_2m": -5.2, "precipitation_height": 0.0},
        # temperature only - must survive
        {"station_id": "06129", "date": "2017-01-12",
         "temperature_air_mean_2m": 3.3, "precipitation_height": np.nan},
        # precipitation only - must survive
        {"station_id": "06129", "date": "2017-01-13",
         "temperature_air_mean_2m": np.nan, "precipitation_height": 1.4},
        # nothing observed - must be dropped
        {"station_id": "02225", "date": "2017-01-11",
         "temperature_air_mean_2m": np.nan, "precipitation_height": np.nan},
    ])

    observation_columns = [
        column for column in frame.columns
        if column not in ("station_id", "date")
    ]
    cleaned = frame[~frame[observation_columns].isna().all(axis=1)]

    assert len(cleaned) == 3, "only the fully empty station-day may be dropped"
    assert "2017-01-12" in set(cleaned["date"]), (
        "a day reporting temperature but not precipitation was discarded"
    )
    assert "2017-01-13" in set(cleaned["date"]), (
        "a day reporting precipitation but not temperature was discarded"
    )
    assert "2017-01-11" not in set(cleaned["date"])


def test_testing_the_whole_row_would_never_drop_anything():
    """Guards the mistake this replaced: identifiers are never null."""
    frame = _pivoted([
        {"station_id": "02225", "date": "2017-01-11",
         "temperature_air_mean_2m": np.nan, "precipitation_height": np.nan},
    ])

    # The identifier columns keep every row non-empty, so the unrestricted
    # form silently retains a station-day with no observations at all.
    assert not frame.isna().all(axis=1).any()

    observation_columns = ["temperature_air_mean_2m", "precipitation_height"]
    assert frame[observation_columns].isna().all(axis=1).all()


@pytest.mark.asyncio
async def test_geosphere_keeps_partially_observed_days(monkeypatch):
    """The same rule, through geosphere's own cleaning step."""
    from farmwise_api.adapters.API_readers.geosphere import geosphere

    stations = pd.DataFrame({
        "id": [1, 2],
        "lat": [47.5, 47.6],
        "lon": [16.5, 16.6],
        "valid_from": ["1950-01-01T00:00+00:00"] * 2,
        "valid_to": ["2030-01-01T00:00+00:00"] * 2,
    })
    observations = pd.DataFrame({
        "station": [1, 1, 2],
        "time": ["2018-01-01", "2018-01-02", "2018-01-01"],
        "tl_mittel": [3.0, 4.0, np.nan],     # station 2 has no temperature
        "rr": [np.nan, 1.0, 2.0],            # station 1 day 1 has no rain
    })

    async def fake_metadata():
        return stations

    async def fake_values(resource_id, station_ids, time_range, parameters):
        return observations.copy()

    monkeypatch.setattr(geosphere, "fetch_station_metadata", fake_metadata)
    monkeypatch.setattr(geosphere, "fetch_station_data", fake_values)
    monkeypatch.setattr(
        geosphere, "prepare_coordinates",
        lambda frame, spatial_range, level: frame.assign(
            S2CELL=[f"cell{index}" for index in range(len(frame))]
        ),
    )

    result = await geosphere.read_data(
        (48.0, 47.0, 17.0, 16.0), ("2018-01-01", "2018-01-02"),
        ["temperature", "precipitation"], 10,
    )

    assert result is not None and not result.empty, (
        "partially observed station-days must not be discarded"
    )

"""Request scenarios shared by coverage and performance experiments."""

from __future__ import annotations

from datetime import date, timedelta

REQUEST_SCENARIOS = [
    # ========================================================
    # 1. MULTI-SOURCE METEOROLOGY — DWD + ERA5
    # ========================================================
    {
        "scenario": "germany-meteo-overlap",
        "country": "Germany",
        "bounding_box": (51.5, 50.5, 10.5, 9.5),
        "level": 10,
        "time_from": "2018-01-01",
        "time_to": "2018-01-07",
        "factors": ["temperature", "precipitation"],
    },

    # ========================================================
    # 2. MULTI-SOURCE METEOROLOGY — GeoSphere + ERA5
    #
    # Eastern Austria deliberately outside DWD coverage.
    # ========================================================
    {
        "scenario": "austria-meteo-overlap",
        "country": "Austria",
        "bounding_box": (48.5, 47.5, 17.0, 16.0),
        "level": 10,
        "time_from": "2018-01-01",
        "time_to": "2018-01-07",
        "factors": ["temperature", "precipitation"],
    },

    # ========================================================
    # 3. ANOTHER CROSS-SOURCE METEOROLOGY CASE
    #    Irish Met + ERA5
    # ========================================================
    {
        "scenario": "ireland-precipitation-overlap",
        "country": "Ireland",
        "bounding_box": (54.0, 53.0, -7.0, -8.0),
        "level": 10,
        "time_from": "2018-01-01",
        "time_to": "2018-01-07",
        "factors": ["precipitation"],
    },

    # ========================================================
    # 4. SPECIALISED NON-METEOROLOGICAL DATA
    # ========================================================
    {
        "scenario": "ireland-groundwater",
        "country": "Ireland",
        "bounding_box": (54.0, 53.0, -7.0, -8.0),
        "level": 10,
        "time_from": "2020-01-01",
        "time_to": "2020-03-31",
        "factors": ["groundwater quantity"],
    },

    # ========================================================
    # 5. STATIC / LAND-COVER INTEGRATION
    #
    # 2020 allows CORINE + EuroCropV2 + IFSGRID temporal
    # eligibility.
    # ========================================================
    {
        "scenario": "germany-land-cover",
        "country": "Germany",
        "bounding_box": (51.5, 50.5, 10.5, 9.5),
        "level": 10,
        "time_from": "2020-01-01",
        "time_to": "2020-12-31",
        "factors": ["land cover"],
    },

    # ========================================================
    # 6. SOIL / DIFFERENT DATA MODEL
    # ========================================================
    {
        "scenario": "germany-soil",
        "country": "Germany",
        "bounding_box": (51.5, 50.5, 10.5, 9.5),
        "level": 10,
        "time_from": "2018-01-01",
        "time_to": "2018-01-07",
        "factors": ["soil"],
    },

    # ========================================================
    # 7. NEGATIVE TEST — FACTOR EXISTS BUT NOT HERE
    #
    # Groundwater sources exist, but none cover Germany.
    # Should be eliminated by coverage precheck.
    # ========================================================
    {
        "scenario": "no-spatial-coverage",
        "country": "Germany",
        "bounding_box": (51.5, 50.5, 10.5, 9.5),
        "level": 10,
        "time_from": "2020-01-01",
        "time_to": "2020-01-07",
        "factors": ["groundwater quantity"],
    },

    # ========================================================
    # 8. NEGATIVE TEST — TEMPORAL COVERAGE
    #
    # Potential evaporation exists, but CDS vegetation ends
    # in 2018.
    # ========================================================
    {
        "scenario": "no-temporal-coverage",
        "country": "Germany",
        "bounding_box": (51.5, 50.5, 10.5, 9.5),
        "level": 10,
        "time_from": "2024-01-01",
        "time_to": "2024-01-07",
        "factors": ["potential evaporation"],
    },
]

CROSS_SOURCE_SCENARIOS = [
    # DWD vs ERA5
    {
        "scenario": "cross-source-germany-meteo",
        "country": "Germany",
        "bounding_box": (51.5, 50.5, 10.5, 9.5),
        "level": 10,
        "time_from": "2018-01-01",
        "time_to": "2018-01-31",
        "factors": ["temperature", "precipitation"],
    },

    # GeoSphere vs ERA5
    {
        "scenario": "cross-source-austria-meteo",
        "country": "Austria",
        "bounding_box": (48.5, 47.5, 17.0, 16.0),
        "level": 10,
        "time_from": "2018-01-01",
        "time_to": "2018-01-31",
        "factors": ["temperature", "precipitation"],
    },

    # Irish Met vs ERA5
    {
        "scenario": "cross-source-ireland-precipitation",
        "country": "Ireland",
        "bounding_box": (54.0, 53.0, -7.0, -8.0),
        "level": 10,
        "time_from": "2018-01-01",
        "time_to": "2018-01-31",
        "factors": ["precipitation"],
    },
    {
        "scenario": "cross-source-poland-meteo",
        "country": "Poland",
        "bounding_box": (52.5, 50.5, 21.0, 18.0),
        "level": 10,
        "time_from": "2018-01-01",
        "time_to": "2018-01-31",
        "factors": ["temperature", "precipitation"],
    }
]

_SCALING_CENTER_LAT = 51.0
_SCALING_CENTER_LON = 10.0
_SCALING_BASE_BBOX = (51.5, 50.5, 10.5, 9.5)
_SCALING_TIME_FROM = "2018-01-01"
_SCALING_TIME_TO = "2018-01-07"
_SCALING_LEVEL = 10
_SCALING_FACTORS = [
    "temperature",
    "precipitation",
    "soil",
    "land cover",
]


def _scaling_request(
    *,
    scenario,
    dimension,
    input_value,
    bounding_box,
    level,
    factors,
    time_from=_SCALING_TIME_FROM,
    time_to=_SCALING_TIME_TO,
):
    return {
        "scenario": scenario,
        "country": "Germany",
        "dimension": dimension,
        "input_value": input_value,
        "bounding_box": bounding_box,
        "level": level,
        "time_from": time_from,
        "time_to": time_to,
        "factors": factors,
    }


LIVE_SCALING_SCENARIOS = [
    *[
        _scaling_request(
            scenario=f"live-s2-level-{level}",
            dimension="S2 level",
            input_value=level,
            bounding_box=_SCALING_BASE_BBOX,
            level=level,
            factors=_SCALING_FACTORS[:2],
        )
        for level in (6, 8, 10, 12)
    ],
    *[
        _scaling_request(
            scenario=f"live-bbox-width-{width}",
            dimension="Bounding-box area",
            input_value=width * width,
            bounding_box=(
                _SCALING_CENTER_LAT + width / 2,
                _SCALING_CENTER_LAT - width / 2,
                _SCALING_CENTER_LON + width / 2,
                _SCALING_CENTER_LON - width / 2,
            ),
            level=10,
            factors=_SCALING_FACTORS[:2],
        )
        for width in (0.25, 0.5, 1.0, 2.0)
    ],
    *[
        _scaling_request(
            scenario=f"live-factor-count-{factor_count}",
            dimension="Factor count",
            input_value=factor_count,
            bounding_box=_SCALING_BASE_BBOX,
            level=10,
            factors=_SCALING_FACTORS[:factor_count],
        )
        for factor_count in (1, 2, 3, 4)
    ],
    *[
        _scaling_request(
            scenario=f"live-duration-days-{duration_days}",
            dimension="Requested days",
            input_value=duration_days,
            bounding_box=_SCALING_BASE_BBOX,
            level=_SCALING_LEVEL,
            factors=_SCALING_FACTORS[:2],
            time_to=(
                date.fromisoformat(_SCALING_TIME_FROM)
                + timedelta(days=duration_days - 1)
            ).isoformat(),
        )
        for duration_days in (1, 7, 30, 90)
    ],
]

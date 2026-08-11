"""Request scenarios shared by coverage and performance experiments."""

from __future__ import annotations


REQUEST_SCENARIOS = [
    {
        "scenario": "poland-temperature",
        "country": "Poland",
        "bounding_box": (54.84, 49.00, 24.15, 14.12),
        "level": 6,
        "time_from": "2018-01-01",
        "time_to": "2018-01-07",
        "factors": ["temperature"],
    },
    {
        "scenario": "germany-meteo",
        "country": "Germany",
        "bounding_box": (55.10, 47.20, 15.10, 5.80),
        "level": 8,
        "time_from": "2010-06-01",
        "time_to": "2010-06-30",
        "factors": ["temperature", "precipitation"],
    },
    {
        "scenario": "austria-precipitation",
        "country": "Austria",
        "bounding_box": (49.10, 46.30, 17.20, 9.50),
        "level": 10,
        "time_from": "2024-04-01",
        "time_to": "2024-04-14",
        "factors": ["precipitation"],
    },
    {
        "scenario": "ireland-groundwater",
        "country": "Ireland",
        "bounding_box": (55.40, 51.40, -6.00, -10.50),
        "level": 12,
        "time_from": "2020-01-01",
        "time_to": "2020-03-31",
        "factors": ["groundwater quantity"],
    },
    {
        "scenario": "france-water-quality",
        "country": "France",
        "bounding_box": (51.10, 41.30, 9.55, -5.15),
        "level": 9,
        "time_from": "2021-01-01",
        "time_to": "2021-12-31",
        "factors": ["surface water quality"],
    },
    {
        "scenario": "europe-land-cover",
        "country": "Europe subset",
        "bounding_box": (60.00, 45.00, 25.00, -5.00),
        "level": 7,
        "time_from": "2015-01-01",
        "time_to": "2015-12-31",
        "factors": ["land cover"],
    },
]


_SCALING_CENTER_LAT = 51.0
_SCALING_CENTER_LON = 10.0
_SCALING_BASE_BBOX = (51.5, 50.5, 10.5, 9.5)
_SCALING_FACTORS = [
    "temperature",
    "precipitation",
    "soil",
    "land cover",
]


def _scaling_request(
    *, scenario, dimension, input_value, bounding_box, level, factors
):
    return {
        "scenario": scenario,
        "country": "Germany",
        "dimension": dimension,
        "input_value": input_value,
        "bounding_box": bounding_box,
        "level": level,
        "time_from": "2018-01-01",
        "time_to": "2018-01-07",
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
]


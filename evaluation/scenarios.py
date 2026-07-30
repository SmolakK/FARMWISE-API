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


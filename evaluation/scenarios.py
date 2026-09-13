"""Scenario definitions and fixed settings for the empirical evaluation.

Everything that defines *what* is measured lives here, so that a collection
can store its complete configuration next to its results (see
``evaluation_config``). The collectors in ``collect_empirical`` decide only
*how* the scenarios are executed.

Experiments
-----------
coverage
    ``REQUEST_SCENARIOS`` - positive and negative spatial/temporal coverage
    cases, each run with the registry-based coverage pre-check and with a
    factor-only routing baseline (``COVERAGE_MODES``).
cross-source
    ``CROSS_SOURCE_SCENARIOS`` - national sources against ERA5 for four
    regions, each in four seasonal months (``SEASONAL_PERIODS``).
scaling
    ``LIVE_SCALING_SCENARIOS`` - one-dimension-at-a-time sweeps of S2 level,
    spatial extent and temporal extent with a fixed factor set.
quality overhead
    ``QUALITY_OVERHEAD_SCENARIO`` - one representative request with quality
    assessment off and on (``QUALITY_MODES``).
"""

from __future__ import annotations

from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Execution settings
# ---------------------------------------------------------------------------

RANDOM_SEED = 42
SCALING_REPEATS = 10
SCALING_WARMUPS = 1
COVERAGE_REPEATS = 3
COVERAGE_WARMUPS = 1
QUALITY_OVERHEAD_REPEATS = 10
QUALITY_OVERHEAD_WARMUPS = 1
REQUEST_TIMEOUT_SECONDS = 600
# Interval of the background process-RSS sampler. Peaks shorter than this can
# be missed; see evaluation/README.md.
RSS_SAMPLING_INTERVAL_SECONDS = 0.05

# ---------------------------------------------------------------------------
# Coverage pre-check experiment
# ---------------------------------------------------------------------------

REQUEST_SCENARIOS = [
    # Multi-source meteorology - DWD + ERA5.
    {
        "scenario": "germany-meteo-overlap",
        "country": "Germany",
        "bounding_box": (51.5, 50.5, 10.5, 9.5),
        "level": 10,
        "time_from": "2018-01-01",
        "time_to": "2018-01-07",
        "factors": ["temperature", "precipitation"],
    },
    # Multi-source meteorology - GeoSphere + ERA5. Eastern Austria lies
    # deliberately outside DWD coverage.
    {
        "scenario": "austria-meteo-overlap",
        "country": "Austria",
        "bounding_box": (48.5, 47.5, 17.0, 16.0),
        "level": 10,
        "time_from": "2018-01-01",
        "time_to": "2018-01-07",
        "factors": ["temperature", "precipitation"],
    },
    # Irish Met + ERA5.
    {
        "scenario": "ireland-precipitation-overlap",
        "country": "Ireland",
        "bounding_box": (54.0, 53.0, -7.0, -8.0),
        "level": 10,
        "time_from": "2018-01-01",
        "time_to": "2018-01-07",
        "factors": ["precipitation"],
    },
    # Specialised non-meteorological data.
    {
        "scenario": "ireland-groundwater",
        "country": "Ireland",
        "bounding_box": (54.0, 53.0, -7.0, -8.0),
        "level": 10,
        "time_from": "2020-01-01",
        "time_to": "2020-03-31",
        "factors": ["groundwater quantity"],
    },
    # Static / land-cover integration. 2020 allows CORINE + EuroCropV2 +
    # IFSGRID temporal eligibility.
    {
        "scenario": "germany-land-cover",
        "country": "Germany",
        "bounding_box": (51.5, 50.5, 10.5, 9.5),
        "level": 10,
        "time_from": "2020-01-01",
        "time_to": "2020-12-31",
        "factors": ["land cover"],
    },
    # Soil - a different data model.
    {
        "scenario": "germany-soil",
        "country": "Germany",
        "bounding_box": (51.5, 50.5, 10.5, 9.5),
        "level": 10,
        "time_from": "2018-01-01",
        "time_to": "2018-01-07",
        "factors": ["soil"],
    },
    # Negative case - the factor exists, but no groundwater source covers
    # Germany. Should be eliminated by the coverage pre-check.
    {
        "scenario": "no-spatial-coverage",
        "country": "Germany",
        "bounding_box": (51.5, 50.5, 10.5, 9.5),
        "level": 10,
        "time_from": "2020-01-01",
        "time_to": "2020-01-07",
        "factors": ["groundwater quantity"],
    },
    # Negative case - factors and area are supported, but no source reaches
    # back to 1900 (the earliest coverage starts in 1941), so every candidate
    # is rejected on temporal grounds alone. A request before any record
    # exists keeps the case valid as sources come and go.
    {
        "scenario": "no-temporal-coverage",
        "country": "Germany",
        "bounding_box": (51.5, 50.5, 10.5, 9.5),
        "level": 10,
        "time_from": "1900-01-01",
        "time_to": "1900-01-07",
        "factors": ["temperature", "precipitation"],
    },
]

# "precheck": FARMWISE as shipped - sources are dispatched only when the
# registry says they overlap the request in space, time and factor.
# "factor-only": baseline - every enabled source that provides a requested
# factor is dispatched, regardless of its spatial and temporal coverage.
COVERAGE_MODES = ("precheck", "factor-only")

# ---------------------------------------------------------------------------
# Cross-source agreement experiment
# ---------------------------------------------------------------------------

SEASONAL_PERIODS = {
    "January": ("2018-01-01", "2018-01-31"),
    "April": ("2018-04-01", "2018-04-30"),
    "July": ("2018-07-01", "2018-07-31"),
    "October": ("2018-10-01", "2018-10-31"),
}

_CROSS_SOURCE_REGIONS = [
    {
        "region": "germany-meteo",
        "country": "Germany",
        "bounding_box": (51.5, 50.5, 10.5, 9.5),
        "factors": ["temperature", "precipitation"],
        "required_sources": ["DWD", "ERA5"],
    },
    {
        "region": "austria-meteo",
        "country": "Austria",
        "bounding_box": (48.5, 47.5, 17.0, 16.0),
        "factors": ["temperature", "precipitation"],
        "required_sources": ["GeoSphere", "ERA5"],
    },
    {
        "region": "ireland-precipitation",
        "country": "Ireland",
        "bounding_box": (54.0, 53.0, -7.0, -8.0),
        "factors": ["precipitation"],
        "required_sources": ["Met Éireann", "ERA5"],
    },
    # The two-degree box contains several IMGW synoptic stations and, at S2
    # level 10, shares cells with the ERA5 grid for direct paired comparison.
    {
        "region": "poland-imgw-era5",
        "country": "Poland",
        "bounding_box": (52.5, 50.5, 21.0, 18.0),
        "factors": ["temperature", "precipitation"],
        "required_sources": ["IMGW", "ERA5"],
    },
]

CROSS_SOURCE_LEVEL = 10

CROSS_SOURCE_SCENARIOS = [
    {
        "scenario": f"cross-source-{region['region']}-{period.lower()}",
        "region": region["region"],
        "period": period,
        "country": region["country"],
        "bounding_box": region["bounding_box"],
        "level": CROSS_SOURCE_LEVEL,
        "time_from": time_from,
        "time_to": time_to,
        "factors": list(region["factors"]),
        "required_sources": list(region["required_sources"]),
    }
    for region in _CROSS_SOURCE_REGIONS
    for period, (time_from, time_to) in SEASONAL_PERIODS.items()
]

# ---------------------------------------------------------------------------
# Scaling experiment
# ---------------------------------------------------------------------------

# One fixed factor set for every sweep, so each sweep changes exactly one
# request dimension. Both factors are served by the same backends (DWD and
# ERA5) over the German base box. A factor-count sweep is deliberately absent:
# adding factors adds adapters and data types, which confounds workload size
# with backend and processing differences.
SCALING_FACTORS = ("temperature", "precipitation")
SCALING_COUNTRY = "Germany"
SCALING_CENTER = (51.0, 10.0)  # (lat, lon)
SCALING_BASE_WIDTH_DEG = 1.0
SCALING_BASE_LEVEL = 10
SCALING_TIME_FROM = "2018-01-01"
SCALING_BASE_DURATION_DAYS = 7

SCALING_LEVELS = (6, 8, 10, 12)
SCALING_WIDTHS_DEG = (0.25, 0.5, 1.0, 2.0)
SCALING_DURATIONS_DAYS = (1, 7, 30, 90)

SCALING_DIMENSIONS = ("S2 level", "Spatial extent", "Temporal extent")


def centred_bounding_box(width_deg, center=SCALING_CENTER):
    """Square (N, S, E, W) box of ``width_deg`` degrees around ``center``."""
    lat, lon = center
    half = width_deg / 2
    return (lat + half, lat - half, lon + half, lon - half)


def inclusive_end_date(time_from, duration_days):
    """ISO end date such that [time_from, end] spans ``duration_days`` days."""
    start = date.fromisoformat(time_from)
    return (start + timedelta(days=duration_days - 1)).isoformat()


def _scaling_request(*, dimension, input_value, width_deg, level, duration_days):
    return {
        "scenario": f"scaling-{dimension.lower().replace(' ', '-')}-{input_value}",
        "country": SCALING_COUNTRY,
        "dimension": dimension,
        "input_value": input_value,
        "width_deg": width_deg,
        "bounding_box": centred_bounding_box(width_deg),
        "level": level,
        "time_from": SCALING_TIME_FROM,
        "time_to": inclusive_end_date(SCALING_TIME_FROM, duration_days),
        "factors": list(SCALING_FACTORS),
    }


LIVE_SCALING_SCENARIOS = [
    *[
        _scaling_request(
            dimension="S2 level",
            input_value=level,
            width_deg=SCALING_BASE_WIDTH_DEG,
            level=level,
            duration_days=SCALING_BASE_DURATION_DAYS,
        )
        for level in SCALING_LEVELS
    ],
    *[
        _scaling_request(
            dimension="Spatial extent",
            input_value=width,
            width_deg=width,
            level=SCALING_BASE_LEVEL,
            duration_days=SCALING_BASE_DURATION_DAYS,
        )
        for width in SCALING_WIDTHS_DEG
    ],
    *[
        _scaling_request(
            dimension="Temporal extent",
            input_value=days,
            width_deg=SCALING_BASE_WIDTH_DEG,
            level=SCALING_BASE_LEVEL,
            duration_days=days,
        )
        for days in SCALING_DURATIONS_DAYS
    ],
]

# ---------------------------------------------------------------------------
# Quality-assessment overhead experiment
# ---------------------------------------------------------------------------

# The scaling base request: one mid-sized, two-backend case.
QUALITY_OVERHEAD_SCENARIO = {
    **_scaling_request(
        dimension="Quality overhead",
        input_value="base",
        width_deg=SCALING_BASE_WIDTH_DEG,
        level=SCALING_BASE_LEVEL,
        duration_days=SCALING_BASE_DURATION_DAYS,
    ),
    "scenario": "quality-overhead-base",
}

# (assess_quality, persist_quality_reports); "on" matches the server defaults.
QUALITY_MODES = {
    "off": (False, False),
    "on": (True, True),
}


def evaluation_config() -> dict:
    """Complete, JSON-serialisable description of the configured experiments."""
    return {
        "random_seed": RANDOM_SEED,
        "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
        "rss_sampling_interval_seconds": RSS_SAMPLING_INTERVAL_SECONDS,
        "coverage": {
            "repeats": COVERAGE_REPEATS,
            "warmups_per_scenario_and_mode": COVERAGE_WARMUPS,
            "modes": list(COVERAGE_MODES),
            "assess_quality": False,
            "separate_api": True,
            "scenarios": REQUEST_SCENARIOS,
        },
        "cross_source": {
            "repeats": 1,
            "assess_quality": True,
            "separate_api": True,
            "seasonal_periods": SEASONAL_PERIODS,
            "scenarios": CROSS_SOURCE_SCENARIOS,
        },
        "scaling": {
            "repeats": SCALING_REPEATS,
            "warmups_per_scenario": SCALING_WARMUPS,
            "assess_quality": False,
            "persist_quality_reports": False,
            "separate_api": False,
            "factors": list(SCALING_FACTORS),
            "dimensions": list(SCALING_DIMENSIONS),
            "scenarios": LIVE_SCALING_SCENARIOS,
        },
        "quality_overhead": {
            "repeats": QUALITY_OVERHEAD_REPEATS,
            "warmups_per_mode": QUALITY_OVERHEAD_WARMUPS,
            "modes": {name: {"assess_quality": a, "persist_quality_reports": p}
                      for name, (a, p) in QUALITY_MODES.items()},
            "separate_api": False,
            "scenario": QUALITY_OVERHEAD_SCENARIO,
        },
    }

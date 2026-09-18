"""
Country configuration for the Eionet CDR Nitrates Directive adapter.

Deliveries are published per country, and often per region, as separate
envelopes. Adding a country or a reporting cycle is a configuration change.
"""

from __future__ import annotations

import json
import logging
from typing import Iterator

from farmwise_api.core.utils.country_bboxes import return_country_bboxes
from farmwise_api.core.utils.merge_bboxes import merge_bounding_boxes
from farmwise_api.core.utils.paths import adapter_data

logger = logging.getLogger("farmwise.eionet_nid")

CONFIG_PARTS = ("eionet_nid", "constants", "eionet_nid_countries.json")

# North below South, so spatial_ranges_overlap never matches this sentinel.
_EMPTY_BBOX = (-90.0, 90.0, -180.0, 180.0)
_EMPTY_PERIOD = ("1900-01-01", "1900-01-01")

_REQUIRED_REPORT_KEYS = ("period", "stations", "concentrations")


def load_countries() -> dict:
    """Return the raw country configuration, or an empty mapping on failure."""
    try:
        with open(adapter_data(*CONFIG_PARTS), "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as error:  # noqa: BLE001
        logger.warning("Could not load Eionet NiD country configuration: %s", error)
        return {}


def iter_reports(countries=None) -> Iterator[dict]:
    """
    Yield one flattened entry per configured report.

    :param countries: optional country names to restrict the result, spelled as
        in ``return_country_bboxes()``.
    """
    wanted = set(countries) if countries is not None else None

    for country, entry in load_countries().items():
        if wanted is not None and country not in wanted:
            continue

        for report in entry.get("reports", []):
            missing = [key for key in _REQUIRED_REPORT_KEYS if not report.get(key)]
            if missing:
                logger.warning(
                    "Skipping Eionet NiD report for %s: missing %s",
                    country, ", ".join(missing),
                )
                continue

            period = report["period"]
            if not isinstance(period, (list, tuple)) or len(period) != 2:
                logger.warning(
                    "Skipping Eionet NiD report for %s: period must be a "
                    "[start, end] pair, got %r.", country, period,
                )
                continue

            yield {
                "country": country,
                "country_code": entry.get("country_code", ""),
                "label": report.get("label", country),
                "period": tuple(period),
                "stations": report["stations"],
                "concentrations": report["concentrations"],
            }


def configured_country_bboxes() -> dict:
    """Return ``{country name: bounding box}`` for every configured country."""
    reference = return_country_bboxes()
    resolved = {}

    for country in load_countries():
        bbox = reference.get(country)
        if bbox is None:
            logger.warning(
                "Eionet NiD country %r has no reference bounding box and is "
                "ignored.", country,
            )
            continue
        resolved[country] = bbox

    return resolved


def registry_coverage():
    """
    Compute the API_PATH_RANGES coverage from the configuration.

    Maintenance helper: run it after adding a country and copy the result into
    the registry entry. Country boxes over-approximate a delivery covering only
    part of a country.
    """
    bboxes = list(configured_country_bboxes().values())
    periods = [report["period"] for report in iter_reports()]

    if not bboxes or not periods:
        logger.warning("Eionet NiD configuration resolves to no coverage.")
        return _EMPTY_BBOX, _EMPTY_PERIOD

    return (
        merge_bounding_boxes(bboxes),
        (min(start for start, _ in periods), max(end for _, end in periods)),
    )

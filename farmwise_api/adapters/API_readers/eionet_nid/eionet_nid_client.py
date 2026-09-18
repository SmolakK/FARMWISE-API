"""
Client for Nitrates Directive groundwater deliveries on the Eionet CDR.

Joins the two tables of each configured report into one station-level frame:
``NiD_GW_Stat`` (station reference) and ``NiD_GW_Conc`` (nitrate statistics).
Knows nothing about S2 cells or the adapter contract, so it can be called
directly to work with the raw delivery.
"""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET

import httpx
import pandas as pd

from farmwise_api.adapters.API_readers.eionet_nid.eionet_nid_config import iter_reports

logger = logging.getLogger("farmwise.eionet_nid")

DEFAULT_TIMEOUT = 60.0

# Unique within a delivery only: the Eionet data dictionary (table 7761)
# declares the formal key as (CountryCode, ND_NatStatCode, ND_StationType).
# Never join on it across reports.
JOIN_KEY = "ND_NatStatCode"

STATION_COLUMNS = {
    "ND_NatStatCode": "ND_NatStatCode",
    "ND_NatStatName": "ND_NatStatName",
    "Longitude": "lon",
    "Latitude": "lat",
    # Same station under another reference system, most likely the previous
    # reporting cycle. Unused until an earlier cycle is configured.
    "ND_NatStatCodeND": "ND_NatStatCodeND",
}

# Everything from NiD_GW_Conc except CountryCode and the join key.
CONCENTRATION_COLUMNS = (
    "ND_StationType",
    "ND_BeginDate",
    "ND_EndDate",
    "ND_NoOfSamples",
    "ND_MaxValue",
    "ND_TrendValue",
    "ND_AvgAnnValue",
)

NUMERIC_COLUMNS = (
    "lon",
    "lat",
    "ND_NoOfSamples",
    "ND_MaxValue",
    "ND_TrendValue",
    "ND_AvgAnnValue",
)

DATE_COLUMNS = ("ND_BeginDate", "ND_EndDate")


def _ensure_xml(content: bytes, label: str, url: str) -> None:
    """
    Reject a response that is not the table.

    The CDR serves restricted files as an HTML error page with HTTP 200, which
    ``raise_for_status`` does not catch. Accepts XML with or without a prolog
    or a byte order mark.
    """
    # Checked first: an error page may be XHTML and start with an XML prolog.
    if b"Unauthorized" in content[:8192]:
        raise ValueError(
            f"Eionet report {label!r} is access restricted by the data provider "
            f"({url}). Only authorised Reportnet users can download it."
        )

    head = content.lstrip(b"\xef\xbb\xbf").lstrip()
    lowered = head[:512].lower()
    is_html = lowered.startswith(b"<!doctype html") or lowered.startswith(b"<html")
    if head.startswith(b"<") and not is_html:
        return

    raise ValueError(
        f"Eionet report {label!r} did not return XML ({url}). "
        "The envelope may have been withdrawn or the URL may be wrong."
    )


def _parse_rows(content: bytes) -> pd.DataFrame:
    """Parse a delivery table into a DataFrame, one row per record."""
    records = [
        {child.tag.split("}")[-1]: (child.text or "").strip() for child in row}
        for row in ET.fromstring(content)
    ]
    return pd.DataFrame(records)


async def _fetch(client: httpx.AsyncClient, url: str, label: str) -> pd.DataFrame:
    response = await client.get(url)
    response.raise_for_status()
    _ensure_xml(response.content, label, url)
    return _parse_rows(response.content)


def _deduplicate_stations(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    """
    Guarantee one station reference per join key.

    Only the right-hand side of the join can fan out, so the concentration
    sheet is left untouched: a station reported under two station types keeps
    both measurements.
    """
    duplicates = int(frame[JOIN_KEY].duplicated().sum())
    if not duplicates:
        return frame

    logger.warning(
        "Eionet report %r: NiD_GW_Stat declares %d duplicate %s values; keeping "
        "the first reference of each so the join cannot fan out.",
        label, duplicates, JOIN_KEY,
    )
    return frame.drop_duplicates(subset=[JOIN_KEY])


def _join(stations: pd.DataFrame, concentrations: pd.DataFrame, label: str) -> pd.DataFrame:
    """Join both sheets on ND_NatStatCode, keeping the requested columns."""
    # Raised rather than tolerated: get_stations turns it into a skipped report,
    # whereas a frame without coordinates would fail deeper in the adapter.
    for column in (JOIN_KEY, "Longitude", "Latitude"):
        if column not in stations.columns:
            raise ValueError(
                f"Eionet report {label!r}: NiD_GW_Stat has no {column} column."
            )
    if JOIN_KEY not in concentrations.columns:
        raise ValueError(
            f"Eionet report {label!r}: NiD_GW_Conc has no {JOIN_KEY} column."
        )

    stations = _deduplicate_stations(stations, label)

    kept = {
        source: target
        for source, target in STATION_COLUMNS.items()
        if source in stations.columns
    }
    measures = [
        column for column in CONCENTRATION_COLUMNS if column in concentrations.columns
    ]

    joined = concentrations[[JOIN_KEY] + measures].merge(
        stations[list(kept)].rename(columns=kept), on=JOIN_KEY, how="inner"
    )

    unmatched = len(concentrations) - len(joined)
    if unmatched:
        logger.warning(
            "Eionet report %r: %d concentration rows have no matching station.",
            label, unmatched,
        )

    return joined


def _coerce(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert measurements to numbers and reporting bounds to dates."""
    for column in NUMERIC_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in DATE_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


async def _read_report(client: httpx.AsyncClient, report: dict) -> pd.DataFrame:
    label = report["label"]

    # Both sheets are awaited to completion before raising, so a failing
    # request cannot leave its sibling in flight when the client closes.
    stations, concentrations = await asyncio.gather(
        _fetch(client, report["stations"], label),
        _fetch(client, report["concentrations"], label),
        return_exceptions=True,
    )
    for result in (stations, concentrations):
        if isinstance(result, BaseException):
            raise result

    frame = _coerce(_join(stations, concentrations, label))
    frame["country"] = report["country"]
    frame["report_label"] = label
    # Declared cycle, as opposed to the per-station first and last sample dates.
    frame["period_start"] = pd.Timestamp(report["period"][0])
    frame["period_end"] = pd.Timestamp(report["period"][1])
    return frame


async def get_stations(countries=None, timeout: float = DEFAULT_TIMEOUT) -> pd.DataFrame:
    """
    Download and join every configured report into one station-level frame.

    An unreadable report - restricted, withdrawn, or malformed - is reported
    and skipped so the remaining ones still return.

    :param countries: optional country names to restrict the download.
    :param timeout: per-request timeout in seconds.
    :return: one row per station and reporting cycle, empty when nothing is
        readable.
    """
    reports = list(iter_reports(countries))
    if not reports:
        return pd.DataFrame()

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        results = await asyncio.gather(
            *(_read_report(client, report) for report in reports),
            return_exceptions=True,
        )

    frames = []
    for report, result in zip(reports, results):
        if isinstance(result, BaseException):
            logger.warning("Skipping Eionet report %r: %s", report["label"], result)
            continue
        frames.append(result)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

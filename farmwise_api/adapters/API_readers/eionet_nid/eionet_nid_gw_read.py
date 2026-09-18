"""
Eionet CDR Nitrates Directive adapter: groundwater nitrate statistics.

A delivery reports one aggregated statistic per station over a four-year
reporting cycle, not a time series, so each station contributes a single
observation stamped at the end of that cycle.
"""

from __future__ import annotations

import logging

import pandas as pd

from farmwise_api.adapters.API_readers.eionet_nid.eionet_nid_client import get_stations
from farmwise_api.adapters.API_readers.eionet_nid.eionet_nid_config import (
    configured_country_bboxes,
)
from farmwise_api.adapters.API_readers.eionet_nid.eionet_nid_mappings.eionet_nid_mapping import (
    DATA_ALIASES,
    GLOBAL_MAPPING,
)
from farmwise_api.adapters.mappings.data_source_mapping import (
    WITHIN_SOURCE_AGGREGATION_METHODS,
)
from farmwise_api.core.utils.coordinates_to_cells import prepare_coordinates
from farmwise_api.core.utils.overlap_checks import spatial_ranges_overlap
from farmwise_api.core.within_source_aggregation import aggregate_to_s2

logger = logging.getLogger("farmwise.eionet_nid")

# A sample count is meaningful summed over the stations of a cell, not averaged.
COLUMN_AGGREGATIONS = {"ND_NoOfSamples": "sum"}


def _select_countries(spatial_range):
    """
    Return the configured countries whose bounding box meets the request.

    Coarse filter deciding which deliveries are worth downloading. Tests for
    intersection, never containment, so it cannot discard a station that
    ``prepare_coordinates`` would have kept.
    """
    return [
        country
        for country, bbox in configured_country_bboxes().items()
        if spatial_ranges_overlap(spatial_range, bbox)
    ]


def _within_reporting_window(frame, time_range):
    """
    Keep the stations whose sampling window meets the requested time range.

    Sample dates are optional and may be blank, parsing to NaT and comparing
    False, which would filter a whole delivery away; the declared cycle is used
    as a fallback.
    """
    time_from, time_to = pd.to_datetime(time_range[0]), pd.to_datetime(time_range[1])

    missing = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
    begin = frame["ND_BeginDate"] if "ND_BeginDate" in frame.columns else missing
    end = frame["ND_EndDate"] if "ND_EndDate" in frame.columns else missing

    begin = begin.fillna(frame["period_start"])
    end = end.fillna(frame["period_end"])

    return frame[(begin <= time_to) & (end >= time_from)]


async def read_data(
    spatial_range,
    time_range,
    data_range,
    level,
    within_source_aggregation_methods=None,
):
    """
    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param time_range: A tuple containing the start and end dates, as 'YYYY-MM-DD' strings.
    :param data_range: A list of requested data types, e.g. ['groundwater quality'].
    :param level: S2Cell level.
    :param within_source_aggregation_methods: Optional override of the per-data-type
        aggregation policy applied when several stations share an S2 cell.
    :return: A pandas DataFrame indexed by timestamp, with (measurement, S2CELL)
        columns, or an empty DataFrame when nothing matches.
    """
    # A bare string would be iterated character by character below.
    if isinstance(data_range, str):
        data_range = [data_range]

    measurement_columns = [
        column for column, data_type in DATA_ALIASES.items() if data_type in data_range
    ]
    if not measurement_columns:
        logger.warning("No Eionet NiD columns match the requested data types.")
        return pd.DataFrame()

    countries = _select_countries(spatial_range)
    if not countries:
        return pd.DataFrame()

    print("DOWNLOADING: EIONET NITRATES DIRECTIVE GROUNDWATER DATA")
    frame = await get_stations(countries)
    if frame.empty:
        return pd.DataFrame()

    frame = _within_reporting_window(frame, time_range)
    if frame.empty:
        return pd.DataFrame()

    # Dated at the end of the declared cycle rather than at the station's last
    # sample date, which is an artefact of field logistics and would scatter
    # the stations of one cell across distinct timestamps.
    frame = frame.assign(Timestamp=frame["period_end"])

    # Cells are assigned on the frame itself: ND_NatStatCode is only unique
    # nationally, so joining a station table back on it would cross-join
    # same-code stations of different countries.
    frame = prepare_coordinates(
        coordinates=frame, spatial_range=spatial_range, level=level
    )
    if frame is None or frame.empty:
        return pd.DataFrame()

    available = [column for column in measurement_columns if column in frame.columns]
    if not available:
        return pd.DataFrame()

    frame = frame[["Timestamp", "S2CELL"] + available]
    frame.Timestamp = pd.to_datetime(frame.Timestamp).dt.date

    frame = aggregate_to_s2(
        frame,
        logical_data_types=data_range,
        methods=(within_source_aggregation_methods
                 or WITHIN_SOURCE_AGGREGATION_METHODS),
        column_data_types=DATA_ALIASES,
        column_aggregations=COLUMN_AGGREGATIONS,
    )
    frame = frame.rename(GLOBAL_MAPPING, axis=1)

    # Station identity and the reporting bounds are dropped: they cannot
    # survive S2 aggregation, and harmonization coerces columns to numbers.
    return frame.reset_index().pivot(
        index="Timestamp",
        columns="S2CELL",
        values=[GLOBAL_MAPPING[column] for column in available],
    )

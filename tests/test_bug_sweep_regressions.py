"""Regression tests for defects found in the pre-submission review."""

import ast
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from farmwise_api.adapters.API_readers.gios.gios_mappings import gios_mapping
from farmwise_api.adapters.API_readers.hubeau.hubeau_mappings import (
    hubeau_mapping_sw_quality,
    hubeau_mapping_wq,
)
from farmwise_api.adapters.mappings.data_source_mapping import API_PATH_RANGES
from farmwise_api.core.harmonization import harmonize_data
from farmwise_api.core.main_call import read_data
from farmwise_api.core.utils.overlap_checks import (
    resolve_range_date,
    time_ranges_overlap,
)
from farmwise_api.server.schemas import ReadDataRequest


def test_relative_range_dates_resolve_at_call_time():
    today = datetime.combine(date.today(), datetime.min.time())
    assert resolve_range_date("today") == today
    assert resolve_range_date("today-5d") == today - timedelta(days=5)
    assert resolve_range_date("2020-01-01") == datetime(2020, 1, 1)


def test_no_source_range_is_frozen_to_a_calendar_date_at_import():
    # A long-running server imported "today" once; ranges must stay relative.
    ends = {str(ranges[1][1]) for ranges in API_PATH_RANGES.values()}
    assert date.today().isoformat() not in ends


def test_relative_range_overlaps_a_recent_request():
    recent = (date.today() - timedelta(days=1)).isoformat()
    assert time_ranges_overlap(("2020-01-01", "today"), (recent, recent))


@pytest.mark.asyncio
async def test_read_data_rejects_reversed_time_range():
    with pytest.raises(ValueError, match="must not be after"):
        await read_data(
            bounding_box=(52.3, 52.2, 21.1, 21.0),
            level=10,
            time_from="2024-02-01",
            time_to="2024-01-01",
            factors=["temperature"],
        )


@pytest.mark.parametrize(
    "time_from,time_to",
    [("2024-02-01", "2024-01-01"), ("2024-1-15", "2024-01-10")],
)
def test_schema_rejects_reversed_time_range(time_from, time_to):
    with pytest.raises(ValidationError, match="must not be after"):
        ReadDataRequest(
            bounding_box=(35.0, 34.0, -117.0, -118.0),
            level=10,
            time_from=time_from,
            time_to=time_to,
            factors=["temperature"],
        )


def test_schema_orders_unpadded_dates_by_value():
    request = ReadDataRequest(
        bounding_box=(35.0, 34.0, -117.0, -118.0),
        level=10,
        time_from="2024-1-5",
        time_to="2024-01-10",
        factors=["temperature"],
    )
    assert request.time_from == "2024-1-5"


def test_categorical_duplicate_timestamps_collapse_to_a_class_not_a_mean():
    stamp = pd.Timestamp("2018-01-01")
    frame = pd.DataFrame(
        {("land cover class", "cell"): [211, 312, 211]},
        index=pd.DatetimeIndex([stamp, stamp, stamp]),
    )
    frame.columns = pd.MultiIndex.from_tuples(frame.columns)

    result = harmonize_data(
        [("corine", frame, ["land cover"])],
        source_weights={},
        data_type_methods={"land cover": "mode"},
    )

    assert result.iloc[0, 0] == 211


def test_gios_soil_parameter_labels_are_unique():
    assert len(gios_mapping.PARAMETER_VALUES) == len(set(gios_mapping.PARAMETER_VALUES))
    assert len(gios_mapping.PARAMETER_SELECTION) == len(
        set(gios_mapping.PARAMETER_SELECTION)
    )


@pytest.mark.parametrize(
    "module", [gios_mapping, hubeau_mapping_wq, hubeau_mapping_sw_quality]
)
def test_mapping_dict_literals_have_no_duplicate_keys(module):
    # A repeated key in a dict literal silently keeps only the last value.
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            assert len(keys) == len(set(keys))


@pytest.mark.parametrize(
    "module", [hubeau_mapping_wq, hubeau_mapping_sw_quality]
)
def test_hubeau_labels_use_valid_micrograms(module):
    assert not [label for label in module.MAPPING.values() if "mµg" in label]


def test_gios_groundwater_mapping_keys_agree():
    # A renamed column missing from the schema is dropped by reindex, and one
    # missing from DATA_ALIASES is never selected: pH, Novaluron and
    # Bifenthrin were all silently absent from results this way.
    from farmwise_api.adapters.API_readers.gios_gw.gios_gw_mappings.gios_gw_mapping import (
        DATA_ALIASES,
        schema,
        selected_columns,
    )

    bookkeeping = {"PUWG 1992 X", "PUWG 1992 Y", "date", "year", "id",
                   "Type of Measurement Point"}
    measurements = set(selected_columns.values()) - bookkeeping
    assert measurements <= set(schema)
    assert measurements == set(DATA_ALIASES)


@pytest.mark.parametrize(
    "box",
    [
        (50.5, 51.5, 10.5, 9.5),    # north and south swapped
        (-10.0, 10.0, 10.5, 9.5),   # inverted latitude band
        (51.5, 50.5, 9.5, 10.5),    # east and west swapped
        (95.0, 50.0, 10.0, 9.0),    # latitude out of range
        (51.5, 50.5, 10.5),         # not four values
    ],
)
def test_malformed_bounding_boxes_are_rejected_before_dispatch(box):
    # The overlap test assumes N >= S and E >= W; with swapped values it
    # reported overlaps that do not exist and dispatched those sources.
    from farmwise_api.core.main_call import plan_source_dispatch

    with pytest.raises(ValueError, match="bounding_box"):
        plan_source_dispatch(box, "2018-01-01", "2018-01-07", ["land cover"])


@pytest.mark.asyncio
async def test_read_data_rejects_a_malformed_bounding_box():
    with pytest.raises(ValueError, match="bounding_box"):
        await read_data(
            bounding_box=(50.5, 51.5, 10.5, 9.5), level=10,
            time_from="2018-01-01", time_to="2018-01-07", factors=["temperature"],
        )


def test_precheck_dispatches_exactly_when_every_requirement_holds():
    import random
    from datetime import date as _date

    from farmwise_api.adapters.mappings.data_source_mapping import API_PATH_RANGES
    from farmwise_api.core.main_call import plan_source_dispatch

    factors = sorted({f for ranges in API_PATH_RANGES.values() for f in ranges[2]})
    rng = random.Random(7)
    for _ in range(500):
        lat = sorted(rng.uniform(-30, 80) for _ in range(2))
        lon = sorted(rng.uniform(-70, 60) for _ in range(2))
        start = _date(1900, 1, 1) + timedelta(days=rng.randint(0, 46000))
        end = start + timedelta(days=rng.randint(0, 4000))
        plan = plan_source_dispatch(
            (lat[1], lat[0], lon[1], lon[0]), start.isoformat(), end.isoformat(),
            rng.sample(factors, rng.randint(1, 3)),
        )
        for decision in plan:
            assert decision["dispatched"] == bool(
                not decision["disabled_reason"]
                and decision["spatial_overlap"]
                and decision["temporal_overlap"]
                and decision["factor_overlap"]
            ), decision


@pytest.mark.parametrize(
    "time_from, time_to, expected",
    [
        ("1985-01-01", "1985-12-31", False),  # before the first CORINE edition
        ("2018-06-01", "2018-06-30", True),
        ("2020-06-01", "2020-06-30", True),   # after 2018: the 2018 edition is carried forward
    ],
)
def test_static_corine_layer_is_valid_from_its_first_edition_onward(time_from, time_to, expected):
    from farmwise_api.core.main_call import plan_source_dispatch

    plan = plan_source_dispatch(
        (54.0, 51.0, 12.0, 8.0), time_from, time_to, ["land cover"], disabled_sources={}
    )
    corine = next(row for row in plan if row["source"].endswith("corine.corine_read"))
    assert corine["temporal_overlap"] is expected
    assert corine["dispatched"] is expected


def test_static_layers_serving_the_latest_edition_have_an_open_end():
    from farmwise_api.adapters.mappings.data_source_mapping import LATEST_EDITION_ONWARD

    for suffix in ("corine.corine_read", "soilgrids.soilgrids_call", "eea.eea_read"):
        source = next(s for s in API_PATH_RANGES if s.endswith(suffix))
        assert API_PATH_RANGES[source][1][1] == LATEST_EDITION_ONWARD

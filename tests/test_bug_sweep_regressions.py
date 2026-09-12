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

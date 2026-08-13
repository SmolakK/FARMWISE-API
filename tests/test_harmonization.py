from datetime import date

import pandas as pd
import pytest

from farmwise_api.adapters.mappings.data_source_mapping import (
    API_PATH_RANGES,
    DATA_SOURCE_WEIGHTS,
    DATA_TYPE_HARMONIZATION_METHODS,
    DISABLED_API_SOURCES,
    PUBLIC_SERVER_API_PATH_RANGES,
    PUBLIC_SERVER_DISABLED_SOURCES,
    WITHIN_SOURCE_AGGREGATION_METHODS,
)
from farmwise_api.core.harmonization import (
    harmonize_data,
    resolve_data_type,
    validate_harmonization_methods,
    validate_source_weights,
)


def test_mapping_configures_every_current_source_and_data_type():
    configured_types = {
        data_type
        for ranges in API_PATH_RANGES.values()
        for data_type in ranges[2]
    }

    assert set(DATA_SOURCE_WEIGHTS) == set(API_PATH_RANGES)
    assert configured_types <= set(DATA_TYPE_HARMONIZATION_METHODS)
    assert "default" in DATA_TYPE_HARMONIZATION_METHODS
    assert configured_types <= set(WITHIN_SOURCE_AGGREGATION_METHODS)
    assert "default" in WITHIN_SOURCE_AGGREGATION_METHODS


def test_egdi_is_excluded_from_public_dispatch():
    egdi_sources = {
        "farmwise_api.adapters.API_readers.egdi.egdi_read_hc",
        "farmwise_api.adapters.API_readers.egdi.egdi_read_d10",
    }

    assert egdi_sources.isdisjoint(API_PATH_RANGES)
    assert egdi_sources <= set(DISABLED_API_SOURCES)


def test_protected_and_private_sources_are_restricted_by_context():
    correctiv = "farmwise_api.adapters.API_readers.correctiv.correctiv_read"
    imgw_sources = {
        "farmwise_api.adapters.API_readers.imgw.imgw_api_synop_daily",
        "farmwise_api.adapters.API_readers.imgw_hydro.imgw_api_hydro_daily",
    }

    assert correctiv not in API_PATH_RANGES
    assert correctiv in DISABLED_API_SOURCES
    assert imgw_sources <= set(API_PATH_RANGES)
    assert imgw_sources <= set(PUBLIC_SERVER_DISABLED_SOURCES)
    assert imgw_sources.isdisjoint(PUBLIC_SERVER_API_PATH_RANGES)


def _frame(values, columns, dates=("2024-01-01",)):
    return pd.DataFrame(
        values,
        index=pd.to_datetime(dates),
        columns=pd.MultiIndex.from_tuples(columns, names=["factor", "cell"]),
    )


def test_harmonize_data_selects_method_per_data_type():
    columns = [("Temperature [C]", "cell-1"), ("Precipitation [mm]", "cell-1")]
    source_frames = [
        ("source.a", _frame([[10.0, 2.0]], columns), ("temperature", "precipitation")),
        ("source.b", _frame([[20.0, 8.0]], columns), ("temperature", "precipitation")),
    ]

    result = harmonize_data(
        source_frames,
        source_weights={"source.a": 3.0, "source.b": 1.0},
        data_type_methods={
            "default": "mean",
            "temperature": "weighted_mean",
            "precipitation": "max",
        },
    )

    assert result.loc["2024-01-01", ("Temperature [C]", "cell-1")] == 12.5
    assert result.loc["2024-01-01", ("Precipitation [mm]", "cell-1")] == 8.0
    assert result.columns.names == ["factor", "cell"]


def test_weighted_mean_renormalizes_weights_for_missing_values():
    columns = [("Temperature [C]", "cell-1")]
    source_frames = [
        (
            "source.a",
            _frame([[10.0], [None]], columns, ("2024-01-01", "2024-01-02")),
            ("temperature",),
        ),
        (
            "source.b",
            _frame([[20.0], [20.0]], columns, ("2024-01-01", "2024-01-02")),
            ("temperature",),
        ),
    ]

    result = harmonize_data(
        source_frames,
        source_weights={"source.a": 3.0, "source.b": 1.0},
        data_type_methods={"default": "weighted_mean"},
    )

    assert result.iloc[0, 0] == 12.5
    assert result.iloc[1, 0] == 20.0


def test_harmonize_data_normalizes_date_and_timestamp_indexes():
    columns = [("Temperature [C]", "cell-1")]
    timestamp_frame = _frame([[10.0]], columns, ("2024-01-01",))
    date_frame = pd.DataFrame(
        [[20.0]],
        index=pd.Index([date(2024, 1, 2)], name="Timestamp"),
        columns=pd.MultiIndex.from_tuples(columns),
    )

    result = harmonize_data(
        [
            ("source.timestamp", timestamp_frame, ("temperature",)),
            ("source.date", date_frame, ("temperature",)),
        ],
        source_weights={},
        data_type_methods={"temperature": "mean"},
    )

    assert isinstance(result.index, pd.DatetimeIndex)
    assert result.index.tolist() == [
        pd.Timestamp("2024-01-01"),
        pd.Timestamp("2024-01-02"),
    ]


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("mean", 4.0),
        ("median", 5.0),
        ("weighted_median", 5.0),
        ("min", 1.0),
        ("max", 6.0),
        ("sum", 12.0),
        ("priority", 5.0),
    ],
)
def test_numeric_harmonization_methods(method, expected):
    column = [("Measurement", "cell-1")]
    source_frames = [
        ("source.a", _frame([[1.0]], column), ("custom",)),
        ("source.b", _frame([[5.0]], column), ("custom",)),
        ("source.c", _frame([[6.0]], column), ("custom",)),
    ]

    result = harmonize_data(
        source_frames,
        source_weights={"source.a": 1.0, "source.b": 4.0, "source.c": 1.0},
        data_type_methods={"custom": method},
    )

    assert result.iloc[0, 0] == expected


@pytest.mark.parametrize(
    ("method", "expected"),
    [("mode", "forest"), ("weighted_mode", "field")],
)
def test_categorical_harmonization_methods(method, expected):
    column = [("Land cover", "cell-1")]
    source_frames = [
        ("source.a", _frame([["forest"]], column), ("land cover",)),
        ("source.b", _frame([["forest"]], column), ("land cover",)),
        ("source.c", _frame([["field"]], column), ("land cover",)),
    ]

    result = harmonize_data(
        source_frames,
        source_weights={"source.a": 1.0, "source.b": 1.0, "source.c": 3.0},
        data_type_methods={"land cover": method},
    )

    assert result.iloc[0, 0] == expected


def test_zero_weights_exclude_sources():
    column = [("Temperature", "cell-1")]
    source_frames = [
        ("source.a", _frame([[10.0]], column), ("temperature",)),
        ("source.b", _frame([[100.0]], column), ("temperature",)),
    ]

    result = harmonize_data(
        source_frames,
        source_weights={"source.a": 1.0, "source.b": 0.0},
        data_type_methods={"temperature": "weighted_mean"},
    )

    assert result.iloc[0, 0] == 10.0


def test_resolve_data_type_prefers_column_then_single_source_type():
    methods = {
        "default": "mean",
        "water": "mean",
        "surface water quality": "median",
        "groundwater quantity": "weighted_mean",
    }

    assert (
        resolve_data_type(
            ("Surface Water Quality - nitrate", "cell"),
            ("groundwater quantity",),
            methods,
        )
        == "surface water quality"
    )
    assert (
        resolve_data_type(
            ("Depth [m]", "cell"),
            ("groundwater quantity",),
            methods,
        )
        == "groundwater quantity"
    )


@pytest.mark.parametrize(
    "weights",
    [
        {"source": -1},
        {"source": float("inf")},
        {"source": "high"},
        {"source": True},
    ],
)
def test_validate_source_weights_rejects_invalid_values(weights):
    with pytest.raises(ValueError, match="Weight for source"):
        validate_source_weights(weights)


def test_validate_harmonization_methods_accepts_alias_and_rejects_unknown():
    assert validate_harmonization_methods(
        {"temperature": "weighted average"}
    ) == {"temperature": "weighted_mean"}

    with pytest.raises(ValueError, match="Unknown harmonization method"):
        validate_harmonization_methods({"temperature": "random"})

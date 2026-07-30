import pandas as pd
import pytest

from adapters.mappings.data_source_mapping import (
    API_PATH_RANGES,
    DATA_SOURCE_WEIGHTS,
    DATA_TYPE_HARMONIZATION_METHODS,
)
from core.harmonization import (
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

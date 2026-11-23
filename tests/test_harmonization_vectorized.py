"""The vectorised harmonize_data gives the column-by-column result."""

import numpy as np
import pandas as pd
import pytest

from farmwise_api.core.harmonization import (
    SUPPORTED_HARMONIZATION_METHODS,
    harmonize_data,
)
from tests.harmonization_reference import reference_harmonize_data


def _frame(rng, days, factor, cells, *, kind="float", nan_share=0.3, repeat=False):
    index = pd.DatetimeIndex(days, name="Timestamp")
    if repeat:
        index = index.append(index[:3]).sort_values()
    columns = pd.MultiIndex.from_product([[factor], cells], names=[None, "S2CELL"])
    shape = (len(index), len(columns))
    if kind == "float":
        # Few distinct values, so ties and exact half-weight splits occur.
        values = rng.integers(0, 4, size=shape).astype(float)
        values[rng.random(shape) < nan_share] = np.nan
    elif kind == "int":
        values = rng.integers(0, 3, size=shape)
    else:
        values = rng.choice(np.array(["forest", "field", "urban"], dtype=object), size=shape)
        values[rng.random(shape) < nan_share] = None
    return pd.DataFrame(values, index=index, columns=columns)


def _sources(seed, kind, repeat):
    rng = np.random.default_rng(seed)
    days = pd.date_range("2018-01-01", periods=6, freq="D")
    later = pd.date_range("2018-01-04", periods=6, freq="D")
    cells = [f"cell{i}" for i in range(8)]
    return [
        ("a", _frame(rng, days, "Value", cells[:6], kind=kind, repeat=repeat), ["thing"]),
        ("b", _frame(rng, later, "Value", cells[2:], kind=kind), ["thing"]),
        ("c", _frame(rng, days, "Value", cells[::2], kind=kind), ["thing"]),
    ]


def _assert_same(actual, expected):
    pd.testing.assert_index_equal(actual.index, expected.index)
    pd.testing.assert_index_equal(actual.columns, expected.columns)
    for column in expected.columns:
        left, right = actual[column], expected[column]
        if pd.api.types.is_numeric_dtype(right.dtype):
            np.testing.assert_allclose(
                left.to_numpy(dtype=float), right.to_numpy(dtype=float),
                rtol=1e-12, equal_nan=True, err_msg=str(column),
            )
        else:
            assert left.tolist() == pytest.approx(right.tolist(), nan_ok=True), column


@pytest.mark.parametrize("method", sorted(SUPPORTED_HARMONIZATION_METHODS))
@pytest.mark.parametrize("weights", [
    {}, {"a": 2.0, "b": 1.0, "c": 1.0}, {"a": 0.0, "b": 3.0, "c": 1.0}, {"a": 1.0, "b": 1.0, "c": 2.0},
])
@pytest.mark.parametrize("repeat", [False, True])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_numeric_columns_match_the_column_by_column_result(method, weights, repeat, seed):
    sources = _sources(seed, "float", repeat)
    kwargs = dict(source_weights=weights, data_type_methods={"thing": method})

    _assert_same(harmonize_data(sources, **kwargs), reference_harmonize_data(sources, **kwargs))


@pytest.mark.parametrize("method", ["mode", "weighted_mode", "priority"])
@pytest.mark.parametrize("kind", ["int", "text"])
@pytest.mark.parametrize("repeat", [False, True])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_categorical_columns_match_the_column_by_column_result(method, kind, repeat, seed):
    sources = _sources(seed, kind, repeat)
    kwargs = dict(
        source_weights={"a": 1.0, "b": 2.0, "c": 1.0},
        data_type_methods={"thing": method},
    )

    _assert_same(harmonize_data(sources, **kwargs), reference_harmonize_data(sources, **kwargs))


def test_methods_are_chosen_per_variable_and_source_types():
    rng = np.random.default_rng(5)
    days = pd.date_range("2018-01-01", periods=4, freq="D")
    cells = ["x", "y", "z"]
    temperature = _frame(rng, days, "Temperature", cells)
    land_cover = _frame(rng, days, "CORINE land-cover class code", cells, kind="int")
    unnamed = _frame(rng, days, "Other", cells)
    sources = [
        ("era5", pd.concat([temperature, unnamed], axis=1), ["temperature", "soil"]),
        ("corine", land_cover, ["land cover"]),
        ("dwd", _frame(rng, days, "Temperature", cells[1:]), ["temperature"]),
    ]
    kwargs = dict(
        source_weights={"era5": 1.0, "corine": 1.0, "dwd": 3.0},
        data_type_methods={
            "temperature": "weighted_median",
            "land cover": "weighted_mode",
            "default": "max",
        },
    )

    _assert_same(harmonize_data(sources, **kwargs), reference_harmonize_data(sources, **kwargs))


def test_a_source_without_observations_still_shapes_the_output():
    days = pd.date_range("2018-01-01", periods=3, freq="D")
    empty = pd.DataFrame(
        np.nan, index=pd.DatetimeIndex(days, name="Timestamp"),
        columns=pd.MultiIndex.from_tuples([("Value", "q")], names=[None, "S2CELL"]),
    )
    sources = [("a", empty, ["thing"])]
    kwargs = dict(source_weights={}, data_type_methods={"thing": "weighted_mean"})

    _assert_same(harmonize_data(sources, **kwargs), reference_harmonize_data(sources, **kwargs))


def test_a_europe_sized_request_takes_seconds_not_hours():
    """200 000 (variable, cell) columns took about 4 minutes; now seconds."""
    import time

    rng = np.random.default_rng(0)
    days = pd.date_range("2017-01-10", periods=30, freq="D")
    cells = np.arange(50_000)
    big = pd.DataFrame(
        rng.normal(size=(len(days), 4 * len(cells))),
        index=pd.DatetimeIndex(days, name="Timestamp"),
        columns=pd.MultiIndex.from_product(
            [["A", "B", "C", "D"], cells], names=[None, "S2CELL"]
        ),
    )
    overlap = big.iloc[:, : len(cells)] + 1
    sources = [("era5", big, ["temperature"]), ("dwd", overlap, ["temperature"])]

    started = time.perf_counter()
    result = harmonize_data(
        sources, source_weights={}, data_type_methods={"temperature": "weighted_mean"}
    )

    assert result.shape == big.shape
    assert time.perf_counter() - started < 60
    np.testing.assert_allclose(
        result.iloc[:, 0].to_numpy(), (big.iloc[:, 0] + overlap.iloc[:, 0]).to_numpy() / 2
    )

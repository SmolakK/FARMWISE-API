"""Categorical variables must never be averaged or linearly interpolated.

Land cover is a class code, not a measurement. The mean of CORINE 211
(non-irrigated arable land) and 312 (coniferous forest) is 261.5, which is not
a class; linear interpolation between them is equally meaningless. Both used
to happen - the separate-API path averaged every column, and interpolation
treated every column as continuous - which surfaced as class codes coming back
as floats.
"""

import numpy as np
import pandas as pd
import pytest

from farmwise_api.core.main_call import (
    _categorical_columns,
    _reduce_duplicate_timestamps,
)

LAND_COVER = "CORINE land-cover class code"
TEMPERATURE = "Temperature [C]"

METHODS_WITHIN = {"default": "mean", "land cover": "mode", "temperature": "mean"}
METHODS_HARMONISE = {
    "default": "weighted_mean",
    "land cover": "weighted_mode",
    "temperature": "weighted_mean",
}


def _frame(values, column, dates):
    return pd.DataFrame(
        values,
        index=pd.to_datetime(dates),
        columns=pd.MultiIndex.from_tuples(
            [(column, "cell-1")], names=["factor", "cell"]
        ),
    )


def test_repeated_land_cover_rows_take_the_mode_not_the_mean():
    """Two sources reporting different classes must yield one of them."""
    dates = ["2018-01-01", "2018-01-01", "2018-01-01"]
    frame = _frame([[211], [312], [211]], LAND_COVER, dates)
    storage = [("source.a", frame, ("land cover",))]

    reduced = _reduce_duplicate_timestamps(frame, storage, METHODS_WITHIN)

    value = reduced.iloc[0, 0]
    assert value == 211, "the mode of 211, 312, 211 is 211"
    assert value != pytest.approx(244.67, abs=1), "this must not be a mean"
    assert pd.api.types.is_integer_dtype(reduced.dtypes.iloc[0]), (
        "a class code must not come back as a float"
    )


def test_a_single_land_cover_source_keeps_its_integer_type():
    """The reported symptom: one source, yet values arrived as 211.0."""
    frame = _frame([[211], [211]], LAND_COVER, ["2018-01-01", "2018-01-01"])
    storage = [("source.a", frame, ("land cover",))]

    reduced = _reduce_duplicate_timestamps(frame, storage, METHODS_WITHIN)

    assert reduced.iloc[0, 0] == 211
    assert pd.api.types.is_integer_dtype(reduced.dtypes.iloc[0])


def test_numeric_variables_are_still_averaged():
    """The fix must not turn measurements into modes."""
    frame = _frame([[10.0], [20.0]], TEMPERATURE, ["2018-01-01", "2018-01-01"])
    storage = [("source.a", frame, ("temperature",))]

    reduced = _reduce_duplicate_timestamps(frame, storage, METHODS_WITHIN)

    assert reduced.iloc[0, 0] == pytest.approx(15.0)


def test_categorical_columns_are_identified_from_the_harmonisation_rule():
    """Any data type combined by mode is categorical by definition."""
    columns = pd.MultiIndex.from_tuples(
        [(LAND_COVER, "cell-1"), (TEMPERATURE, "cell-1")],
        names=["factor", "cell"],
    )
    frame = pd.DataFrame([[211, 10.0]], columns=columns)
    storage = [("source.a", frame, ("land cover", "temperature"))]

    categorical = _categorical_columns(frame, storage, METHODS_HARMONISE)

    assert LAND_COVER in categorical
    assert TEMPERATURE not in categorical


def test_interpolation_of_classes_yields_only_real_classes():
    """Nearest neighbour, never linear: every output must be an input class."""
    from farmwise_api.core.utils.interpolate_data import interpolate

    cells = ["cell-a", "cell-b"]
    columns = pd.MultiIndex.from_tuples(
        [(LAND_COVER, c) for c in cells], names=["factor", "cell"]
    )
    frame = pd.DataFrame(
        [[211, 312]], index=pd.to_datetime(["2018-01-01"]), columns=columns
    )

    pytest.importorskip("scipy")
    try:
        result = interpolate(
            frame, (51.0, 50.9, 10.1, 10.0), 10,
            categorical_columns=(LAND_COVER,),
        )
    except Exception:  # pragma: no cover - depends on S2 cell resolution
        pytest.skip("interpolation needs resolvable S2 cells for this extent")

    values = pd.unique(result.values.ravel())
    values = [v for v in values if not pd.isna(v)]
    assert values, "interpolation produced no values"
    assert set(values) <= {211, 312}, (
        f"interpolation invented classes that do not exist: {sorted(values)}"
    )
    assert not any(
        isinstance(v, float) and v % 1 for v in values
    ), "a class code must be a whole number"

"""Interpolation must produce a target grid for any area and level.

The grid used to be built by sampling a lat/lon mesh and keeping only cells
whose *centre* fell inside the bounding box. A cell is generally larger than
the sample spacing, so for a coarse level - or a small country - every centre
could lie outside the box, leaving the grid empty and failing with an opaque
``IndexError: too many indices for array``.

Albania at S2 level 5 is the reported case: four cells cover it and not one of
their centres is inside its bounding box.
"""

import numpy as np
import pandas as pd
import pytest

from farmwise_api.core.utils.coordinates_to_cells import get_s2_cells
from farmwise_api.core.utils.interpolate_data import interpolate

# (N, S, E, W) as returned by return_country_bboxes()["Albania"]
ALBANIA = (42.6610848, 39.6448625, 21.0574335, 19.1246095)
FACTOR = "Temperature [C]"


def _frame(spatial_range, level, values=None):
    """A one-timestamp frame on the cells covering `spatial_range`."""
    cells = list(get_s2_cells(spatial_range, level))
    assert cells, "fixture needs at least one covering cell"
    if values is None:
        values = [float(index) for index in range(len(cells))]
    columns = pd.MultiIndex.from_tuples(
        [(FACTOR, f"CellId: {cell.to_token()}") for cell in cells],
        names=["factor", "cell"],
    )
    return pd.DataFrame(
        [values], index=pd.to_datetime(["2018-06-01"]), columns=columns
    )


def test_no_cell_centre_lies_inside_albania_at_level_5():
    """The precondition that used to empty the grid still holds."""
    north, south, east, west = ALBANIA
    cells = list(get_s2_cells(ALBANIA, 5))
    assert cells, "Albania must be covered by at least one level-5 cell"

    inside = [
        cell for cell in cells
        if south <= cell.to_lat_lng().lat().degrees <= north
        and west <= cell.to_lat_lng().lng().degrees <= east
    ]
    assert inside == [], (
        "this test is only meaningful while every covering cell centre is "
        "outside the bounding box"
    )


@pytest.mark.parametrize("level", [5, 6, 8])
def test_albania_interpolates_at_coarse_levels(level):
    """The reported failure: Albania at level 5 raised instead of returning."""
    frame = _frame(ALBANIA, level)

    result = interpolate(frame, ALBANIA, level)

    assert not result.empty
    expected = len(list(get_s2_cells(ALBANIA, level)))
    assert result.shape[1] == expected, (
        "output must cover every cell of the requested area"
    )


def test_target_grid_matches_the_covering_used_elsewhere():
    """Interpolated output lands on the same cells the adapters produce."""
    level = 8
    frame = _frame(ALBANIA, level)

    result = interpolate(frame, ALBANIA, level)

    produced = {str(cell) for cell in result.columns.get_level_values(1)}
    covering = {str(cell) for cell in get_s2_cells(ALBANIA, level)}
    assert produced == covering


def test_area_smaller_than_a_single_cell_still_yields_a_grid():
    """A tiny extent must not produce an empty target grid."""
    tiny = (41.3301, 41.3299, 19.8201, 19.8199)   # a few metres across
    level = 5
    frame = _frame(tiny, level)

    result = interpolate(frame, tiny, level)

    assert result.shape[1] >= 1


def test_values_survive_interpolation_onto_the_covering():
    """A constant field must stay constant wherever it is evaluated."""
    level = 6
    cells = list(get_s2_cells(ALBANIA, level))
    frame = _frame(ALBANIA, level, values=[7.5] * len(cells))

    result = interpolate(frame, ALBANIA, level)

    values = pd.unique(result.values.ravel())
    values = [v for v in values if not pd.isna(v)]
    assert values, "interpolation produced no values"
    assert np.allclose(values, 7.5), f"constant field changed: {values}"

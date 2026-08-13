from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from affine import Affine

from farmwise_api.adapters.API_readers.eea import eea_read


@pytest.mark.asyncio
async def test_eea_read_data_expands_raster_values_over_requested_dates(
    monkeypatch,
):
    monkeypatch.setattr(eea_read, "adapter_data", lambda *_args: "raster.tif")
    monkeypatch.setattr(
        eea_read,
        "read_raster_window",
        lambda *_args: (
            np.array([[1.0, np.nan], [2.0, 2.0]]),
            Affine.translation(16.0, 51.0) * Affine.scale(0.5, -0.5),
        ),
    )

    def prepare(frame, _spatial_range, _level):
        return frame.assign(S2CELL=["cell-a", "cell-b", "cell-b"])

    monkeypatch.setattr(eea_read, "prepare_coordinates", prepare)

    result = await eea_read.read_data(
        (51.0, 49.0, 18.0, 16.0),
        ("2018-01-01", "2018-01-02"),
        ["land cover"],
        10,
    )

    assert result.index.tolist() == list(pd.date_range("2018-01-01", periods=2))
    assert result.shape[1] == 2
    assert set(result.iloc[0].tolist()) == {1.0, 2.0}


@pytest.mark.asyncio
async def test_eea_read_data_returns_empty_frame_for_nodata(monkeypatch):
    monkeypatch.setattr(eea_read, "adapter_data", lambda *_args: "raster.tif")
    monkeypatch.setattr(
        eea_read,
        "read_raster_window",
        lambda *_args: (
            np.array([[np.nan]]),
            Affine.translation(16.0, 51.0) * Affine.scale(0.5, -0.5),
        ),
    )

    result = await eea_read.read_data(
        (51.0, 49.0, 18.0, 16.0),
        ("2020-01-01", "2020-01-02"),
        ["land cover"],
        10,
    )

    assert result.empty


def test_read_raster_window_reprojects_and_converts_nodata(monkeypatch):
    source = MagicMock()
    source.crs = "EPSG:3035"
    source.transform = Affine.identity()
    source.nodata = -9999
    source.read.return_value = np.array([[1, -9999], [2, 3]])
    source.window_transform.return_value = Affine.identity()
    context = MagicMock()
    context.__enter__.return_value = source
    monkeypatch.setattr(eea_read.rasterio, "open", MagicMock(return_value=context))
    monkeypatch.setattr(
        eea_read, "transform_bounds", lambda *_args: (0.0, 0.0, 2.0, 2.0)
    )
    monkeypatch.setattr(
        eea_read,
        "from_bounds",
        lambda *_args, **_kwargs: SimpleNamespace(width=2, height=2),
    )
    monkeypatch.setattr(
        eea_read.rasterio.transform,
        "array_bounds",
        lambda *_args: (0.0, 0.0, 2.0, 2.0),
    )
    destination_transform = Affine.scale(1.0, -1.0)
    monkeypatch.setattr(
        eea_read,
        "calculate_default_transform",
        lambda *_args: (destination_transform, 2, 2),
    )

    def reproject(source, destination, **_kwargs):
        destination[:] = source

    monkeypatch.setattr(eea_read, "reproject", reproject)

    data, transform = eea_read.read_raster_window(
        "raster.tif", (51.0, 49.0, 18.0, 16.0)
    )

    assert transform == destination_transform
    assert np.isnan(data[0, 1])
    assert data[1, 1] == 3

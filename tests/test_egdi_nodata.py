import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from farmwise_api.adapters.API_readers.egdi import egdi_read_d10, egdi_read_hc


@pytest.mark.asyncio
@pytest.mark.parametrize("module", [egdi_read_d10, egdi_read_hc])
async def test_egdi_nodata_pixels_are_not_averaged(module, tmp_path, monkeypatch):
    # One 2x2 degree raster over a single S2 cell: three valid scores and one
    # nodata pixel. The nodata value must not be averaged in as a score.
    path = tmp_path / "egdi.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=2, width=2, count=1, dtype="float32",
        crs="EPSG:4326", transform=from_origin(15.0, 51.0, 0.01, 0.01),
        nodata=-9999.0,
    ) as dst:
        dst.write(np.array([[4, 6], [8, -9999]], dtype="float32"), 1)
    monkeypatch.setattr(module, "adapter_data", lambda *_parts: path)

    result = await module.read_data(
        (51.0, 50.98, 15.02, 15.0), ("2020-01-01", "2020-01-01"),
        ["hydraulic conductivity"], 5,
    )

    values = result.to_numpy().ravel()
    values = values[~np.isnan(values)]
    assert values.size and np.allclose(values, 6.0)

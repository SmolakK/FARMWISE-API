import base64
from io import BytesIO

import numpy as np
import pandas as pd
import pytest
from PIL import Image
from s2sphere import CellId, LatLng

from farmwise_api.core.utils import map_ploter


def _dataset(value=5.0):
    cell = CellId.from_lat_lng(LatLng.from_degrees(51.0, 17.0)).parent(10)
    columns = pd.MultiIndex.from_tuples([("temperature", cell)])
    return pd.DataFrame(
        [[value]],
        index=pd.to_datetime(["2024-01-01"]),
        columns=columns,
    )


def test_create_raster_builds_float_raster_and_bounds():
    raster, parameter, bounds = map_ploter.create_raster(
        _dataset(), pd.Timestamp("2024-01-01"), "temperature", pixel_size=0.01
    )

    assert parameter == "temperature"
    assert raster.dtype == np.float32
    assert np.isfinite(raster).any()
    minx, miny, maxx, maxy = bounds
    assert minx < maxx
    assert miny < maxy


def test_create_raster_rejects_parameter_without_values():
    with pytest.raises(ValueError, match="No valid polygons"):
        map_ploter.create_raster(
            _dataset(np.nan), pd.Timestamp("2024-01-01"), "temperature"
        )


def test_raster_to_png_base64_returns_transparent_png():
    raster = np.array([[0.0, np.nan], [5.0, 10.0]], dtype=float)

    data_url = map_ploter.raster_to_png_base64(
        raster, vmin=0.0, vmax=10.0, downsample=1
    )

    prefix, encoded = data_url.split(",", 1)
    image = Image.open(BytesIO(base64.b64decode(encoded)))
    assert prefix == "data:image/png;base64"
    assert image.format == "PNG"
    assert image.mode == "RGBA"
    assert image.getpixel((1, 0))[3] == 0


def test_encode_image_to_base64_handles_present_and_missing_file(tmp_path):
    image_path = tmp_path / "logo.bin"
    image_path.write_bytes(b"logo")

    assert map_ploter.encode_image_to_base64(image_path) == base64.b64encode(
        b"logo"
    ).decode("utf-8")
    assert map_ploter.encode_image_to_base64(tmp_path / "missing.png") is None
    assert map_ploter.encode_image_to_base64(None) is None


def test_create_folium_map_embeds_controls_and_overlay(monkeypatch):
    dataset = _dataset()
    monkeypatch.setattr(
        map_ploter,
        "create_raster",
        lambda *_args, **_kwargs: (
            np.array([[1.0, 2.0]], dtype=float),
            "temperature",
            (16.0, 50.0, 18.0, 52.0),
        ),
    )
    monkeypatch.setattr(
        map_ploter,
        "raster_to_png_base64",
        lambda *_args, **_kwargs: "data:image/png;base64,ZmFrZQ==",
    )

    html = map_ploter.create_folium_map(
        dataset, custom_title_prefix="Test FARMWISE", downsample_factor=1
    )

    assert "Test FARMWISE" in html
    assert "overlay_0_0" in html
    assert "temperature" in html
    assert "2024-01-01" in html


def test_create_folium_map_rejects_empty_dates():
    dataset = _dataset().iloc[0:0]

    with pytest.raises(ValueError, match="no dates"):
        map_ploter.create_folium_map(dataset)


def test_create_folium_map_rejects_data_without_valid_rasters(monkeypatch):
    dataset = _dataset(np.nan)

    with pytest.raises(ValueError, match="No valid rasters"):
        map_ploter.create_folium_map(dataset)


def test_default_tile_layer_is_the_one_that_survives_network_filtering():
    """OpenTopoMap is the default: tile.openstreetmap.org and cartocdn are blocked
    on some institutional networks, leaving users with a blank map."""
    import pandas as pd
    from s2sphere import CellId, LatLng

    from farmwise_api.core.utils.map_ploter import create_folium_map

    cell = CellId.from_lat_lng(LatLng.from_degrees(52.0, 19.0)).parent(10)
    frame = pd.DataFrame(
        [[5.0]],
        index=pd.to_datetime(["2024-01-01"]),
        columns=pd.MultiIndex.from_tuples([("Temperature [C]", cell)]),
    )

    html = create_folium_map(frame, downsample_factor=1)

    # Leaflet stacks base layers in insertion order, so the default must be
    # added last to sit on top of providers the viewer's network may block.
    assert html.rindex("opentopomap.org") > html.rindex("basemaps.cartocdn.com"), (
        "OpenTopoMap must be added last so it is painted above the others"
    )
    # and the initialiser must drop the unselected layers.
    assert "updateBaseLayer();" in html.split("function initializeMap")[1].split("function getTileLayerName")[0]
    assert 'value="Topographic" id="tile_Topographic" checked' in html
    assert 'value="OpenStreetMap" id="tile_OpenStreetMap" ' in html

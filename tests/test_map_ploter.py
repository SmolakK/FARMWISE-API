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


def test_create_folium_map_does_not_warn_for_days_without_values(caplog):
    """Sparse days are normal; one warning per empty day flooded the server log."""
    cell = CellId.from_lat_lng(LatLng.from_degrees(51.0, 17.0)).parent(10)
    dataset = pd.DataFrame(
        {("temperature", cell): [5.0] + [np.nan] * 30},
        index=pd.date_range("2024-01-01", periods=31),
    )
    dataset.columns = pd.MultiIndex.from_tuples(dataset.columns)

    with caplog.at_level("WARNING", logger=map_ploter.logger.name):
        html = map_ploter.create_folium_map(dataset, downsample_factor=1)

    assert "overlay_0_0" in html
    assert "overlay_0_1" not in html
    assert not caplog.records


def _grid_dataset(days=4, level=10, params=("temperature", "rain")):
    rng = np.random.default_rng(3)
    cells = list(dict.fromkeys(
        CellId.from_lat_lng(LatLng.from_degrees(lat, lon)).parent(level)
        for lat in np.arange(50.0, 51.0, 0.05)
        for lon in np.arange(16.0, 17.5, 0.05)
    ))
    columns = pd.MultiIndex.from_product([list(params), cells])
    values = rng.normal(size=(days, len(columns)))
    values[rng.random(values.shape) < 0.2] = np.nan
    return pd.DataFrame(
        values, index=pd.date_range("2024-01-01", periods=days), columns=columns
    ), cells, level


def test_each_pixel_takes_the_value_of_the_cell_under_its_centre():
    dataset, cells, level = _grid_dataset()
    values = dataset["temperature"].to_numpy()
    interior, touched, (minx, miny, maxx, maxy) = map_ploter._cell_layout(cells, {})
    raster = map_ploter._fill_layout(values[0], interior, touched)

    height, width = raster.shape
    by_cell = dict(zip(cells, values[0]))
    rng = np.random.default_rng(0)
    checked = 0
    for row, col in zip(rng.integers(0, height, 400), rng.integers(0, width, 400)):
        lon = minx + (col + 0.5) * (maxx - minx) / width
        lat = maxy - (row + 0.5) * (maxy - miny) / height
        cell = CellId.from_lat_lng(LatLng.from_degrees(lat, lon)).parent(level)
        if cell not in by_cell or np.isnan(by_cell[cell]):
            continue
        assert raster[row, col] == pytest.approx(by_cell[cell], rel=1e-6)
        checked += 1
    assert checked > 100


def test_cells_are_rasterised_once_per_parameter_not_per_day(monkeypatch):
    """Rasterising every cell for every day took ~12 min/day on Germany+Poland."""
    dataset, _cells, _level = _grid_dataset(days=12)
    calls = []
    real = map_ploter.rasterize
    monkeypatch.setattr(
        map_ploter, "rasterize", lambda *a, **k: calls.append(1) or real(*a, **k)
    )

    html = map_ploter.create_folium_map(dataset, downsample_factor=1)

    assert len(calls) == 2 * 2  # interior + touched layout, for each of 2 parameters
    assert "overlay_1_11" in html


def test_colour_table_matches_the_colormap():
    from matplotlib import colormaps

    index = np.arange(256, dtype=np.uint8)
    expected = (colormaps.get_cmap("viridis")(index) * 255).astype(np.uint8)
    np.testing.assert_array_equal(map_ploter._colour_table("viridis")[index], expected)

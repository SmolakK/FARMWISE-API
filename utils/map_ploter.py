import os
import json
from io import BytesIO

import base64
import numpy as np
import pandas as pd
from PIL import Image
from s2sphere import Cell, LatLng
from shapely.geometry import Polygon, MultiPolygon
from rasterio.features import rasterize
from rasterio.transform import from_bounds

import folium
from folium import plugins

from tqdm import tqdm
# ==============================
#   RASTER CREATION UTILITIES
# ==============================

def create_raster(dataset, day, param, pixel_size=0.01):
    """
    Optimized Create a raster from S2 cells for a given day and parameter.
    """

    # Get series indexed by cell IDs, drop NaNs early
    series = dataset.loc[day, param].dropna()

    if series.empty:
        raise ValueError(f"No valid polygons for {day} - {param}")

    polygons = []
    values = []

    # Preallocate bounds (lon/lat)
    minx = 1e9
    miny = 1e9
    maxx = -1e9
    maxy = -1e9

    append_poly = polygons.append
    append_val = values.append

    for cell_id, value in series.items():

        cell = Cell(cell_id)

        # Pre-allocate 4 vertices (no list comprehension)
        coords = []
        for i in range(4):
            p = cell.get_vertex(i)
            latlng = LatLng.from_point(p)
            x = latlng.lng().degrees
            y = latlng.lat().degrees
            coords.append((x, y))

            # Update bounds inline
            if x < minx: minx = x
            if y < miny: miny = y
            if x > maxx: maxx = x
            if y > maxy: maxy = y

        append_poly(Polygon(coords))
        append_val(float(value))

    # Raster grid geometry
    width = int(np.ceil((maxx - minx) / pixel_size))
    height = int(np.ceil((maxy - miny) / pixel_size))
    transform_affine = from_bounds(minx, miny, maxx, maxy, width, height)

    # Rasterize polygons
    shapes = list(zip(polygons, values))
    raster = rasterize(
        shapes=shapes,
        out_shape=(height, width),
        transform=transform_affine,
        fill=np.nan,
        dtype="float32",
        all_touched=True
    )

    return raster, param, (minx, miny, maxx, maxy)


def raster_to_png_base64(raster, vmin, vmax, colormap='viridis', downsample=4):
    """
    Convert a raster to an RGBA PNG image and return as base64 data URL.

    Parameters
    ----------
    raster : np.ndarray
    vmin, vmax : float
        Global min/max used for normalization.
    colormap : str
        Matplotlib colormap name.
    downsample : int
        Subsampling factor (for performance).

    Returns
    -------
    data_url : str
        "data:image/png;base64,...."
    """
    # Downsample to reduce size
    if downsample > 1:
        raster = raster[::downsample, ::downsample]

    # Normalize values to 0–255
    raster_normalized = np.zeros_like(raster, dtype=np.uint8)
    valid_mask = ~np.isnan(raster)

    if valid_mask.any() and vmin < vmax:
        valid_values = raster[valid_mask]
        normalized = ((valid_values - vmin) / (vmax - vmin) * 255).clip(0, 255)
        raster_normalized[valid_mask] = normalized.astype(np.uint8)

    # Map to RGBA using matplotlib
    from matplotlib import cm as mpl_cm
    cmap = mpl_cm.get_cmap(colormap)
    rgba_image = cmap(raster_normalized)
    rgba_image[~valid_mask] = [0, 0, 0, 0]  # transparent where NaN

    img = Image.fromarray((rgba_image * 255).astype(np.uint8))

    buffer = BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')

    return f"data:image/png;base64,{img_str}"


def encode_image_to_base64(image_path):
    """Convert an image file to base64 (no data URL prefix)."""
    if not image_path:
        return None
    try:
        with open(image_path, 'rb') as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    except FileNotFoundError:
        print(f"Warning: Image file '{image_path}' not found.")
        return None


# ==============================
#        MAIN MAP CREATOR
# ==============================

def create_folium_map(
    dataset,
    output_file='folium_map.html',
    downsample_factor=4,
    custom_title_prefix="FARMWISE API",
    opacity=0.7,
    logo_left=None,
    logo_right=None
):
    """
    Create an interactive Folium map with:
    - parameter radio buttons
    - base map radio buttons
    - date slider
    - dynamic legend
    - S2-based raster overlays rendered as PNGs

    Parameters
    ----------
    dataset : pd.DataFrame
        MultiIndex columns (level 0 = parameter, level 1 = S2 cell id), index = dates
    output_file : str
        Output HTML file path
    downsample_factor : int
        Downsampling factor for rasters
    custom_title_prefix : str
        Title text shown in the top header bar
    opacity : float
        Overlay opacity for ImageOverlay
    logo_left, logo_right : str or None
        Paths to optional logo images
    """
    print(f"Generating map with Folium (downsampling by {downsample_factor}x)...")

    # ---- Basic index/parameter extraction ----
    dates_index = dataset.index.tolist()
    if not dates_index:
        raise ValueError("Dataset has no dates in index.")

    # Convert dates to ISO strings for JS
    def to_iso(d):
        if isinstance(d, pd.Timestamp):
            return d.date().isoformat()
        return str(d)

    dates_str = [to_iso(d) for d in dates_index]

    parameters = dataset.columns.get_level_values(0).unique().tolist()
    if not parameters:
        raise ValueError("Dataset has no parameters in columns.")

    # ---- 1st pass: compute global bounds & per-parameter min/max ----
    print("Calculating parameter ranges...")

    param_ranges = {param: {'min': float('inf'), 'max': float('-inf')} for param in parameters}
    all_bounds = []

    for day in tqdm(dates_index, total=len(dates_index)):
        for param in parameters:

            # --- Fast skip: if no data, don't call rasterization ---
            s = dataset.loc[day, param]
            if s.isna().all():
                continue

            try:
                raster, _, bounds = create_raster(dataset, day, param)
            except Exception as e:
                print(f"  Skipping {day} - {param}: {e}")
                continue

            all_bounds.append(bounds)

            # --- Fast min/max using masked array ---
            if np.isnan(raster).all():
                continue

            # Compute min/max from raster
            vmin = float(np.nanmin(raster))
            vmax = float(np.nanmax(raster))

            # Inline update (faster than Python min/max)
            if vmin < param_ranges[param]['min']:
                param_ranges[param]['min'] = vmin
            if vmax > param_ranges[param]['max']:
                param_ranges[param]['max'] = vmax

    # Handle params with no data at all
    for param, rng in param_ranges.items():
        if rng['min'] == float('inf') or rng['max'] == float('-inf'):
            rng['min'] = 0.0
            rng['max'] = 0.0

    print("\nParameter ranges:")
    for param, rng in param_ranges.items():
        print(f"  {param}: {rng['min']:.2f} - {rng['max']:.2f}")

    if not all_bounds:
        raise ValueError("No valid rasters produced; check dataset content.")

    # Global bounds for centering map
    all_minx = min(b[0] for b in all_bounds)
    all_miny = min(b[1] for b in all_bounds)
    all_maxx = max(b[2] for b in all_bounds)
    all_maxy = max(b[3] for b in all_bounds)

    center_lat = (all_miny + all_maxy) / 2.0
    center_lon = (all_minx + all_maxx) / 2.0

    # ---- Create base map (no default tiles to avoid duplicates) ----
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=9,
        tiles=None,
        control_scale=True
    )

    tile_layers = {
        'OpenStreetMap': folium.TileLayer(
            tiles='OpenStreetMap',
            name='OpenStreetMap'
        ),
        'Topographic': folium.TileLayer(
            tiles='https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
            attr='Map data: © OpenStreetMap contributors, SRTM | Map style: © OpenTopoMap',
            name='Topographic',
            max_zoom=17
        ),
        'Light Map': folium.TileLayer(
            tiles='CartoDB positron',
            name='Light Map'
        ),
        'Dark Map': folium.TileLayer(
            tiles='CartoDB dark_matter',
            name='Dark Map'
        )
    }

    for layer in tile_layers.values():
        layer.add_to(m)

    # ---- 2nd pass: create raster overlays & encode as base64 PNG ----
    print("\nGenerating overlay images...")
    overlay_data = {}

    for param_idx, param in tqdm(enumerate(parameters),total=len(parameters)):
        rng = param_ranges[param]
        vmin, vmax = rng['min'], rng['max']

        for date_idx, day in enumerate(dates_index):
            try:
                raster, _, bounds = create_raster(dataset, day, param)

                img_base64 = raster_to_png_base64(
                    raster,
                    vmin=vmin,
                    vmax=vmax,
                    downsample=downsample_factor
                )

                minx, miny, maxx, maxy = bounds
                # Leaflet wants [[lat_min, lon_min], [lat_max, lon_max]]
                bounds_latlon = [[miny, minx], [maxy, maxx]]

                layer_id = f"overlay_{param_idx}_{date_idx}"
                overlay_data[layer_id] = {
                    "image": img_base64,
                    "bounds": bounds_latlon,
                    "param_idx": param_idx,
                    "date_idx": date_idx,
                }

                print(f"  Processed: {day} - {param}")
            except Exception as e:
                print(f"  Error: {day} - {param}: {e}")

    # ---- Plugins ----
    plugins.Fullscreen().add_to(m)
    plugins.MousePosition().add_to(m)
    plugins.MeasureControl().add_to(m)

    # ---- Logos (optional) ----
    logo_left_b64 = encode_image_to_base64(logo_left)
    logo_right_b64 = encode_image_to_base64(logo_right)

    logo_left_html = (
        f'<img src="data:image/png;base64,{logo_left_b64}" '
        f'style="height: 80px;">'
        if logo_left_b64 else ''
    )
    logo_right_html = (
        f'<img src="data:image/png;base64,{logo_right_b64}" '
        f'style="height: 80px;">'
        if logo_right_b64 else ''
    )

    # ---- Build parameter radio buttons ----
    param_radios_html = ""
    for i, param in enumerate(parameters):
        checked = "checked" if i == 0 else ""
        param_radios_html += f'''
          <label style="display: flex; align-items: center; margin: 5px 0; cursor: pointer;">
              <input type="radio" name="parameter" value="{i}" {checked}
                     onchange="updateDataLayer()" style="margin-right: 8px;">
              <span style="font-size: 14px;">{param}</span>
          </label>
        '''

    # ---- Build base map radio buttons ----
    tile_radios_html = ""
    for name in tile_layers.keys():
        checked = "checked" if name == 'OpenStreetMap' else ""
        tile_id = name.replace(' ', '_')
        tile_radios_html += f'''
          <label style="display: flex; align-items: center; margin: 5px 0; cursor: pointer;">
              <input type="radio" name="baselayer" value="{name}" id="tile_{tile_id}" {checked}
                     onchange="updateBaseLayer()" style="margin-right: 8px;">
              <span style="font-size: 14px;">{name}</span>
          </label>
        '''

    # ---- Build JS-friendly data structures ----
    # overlayData: { "overlay_0_0": {image, bounds, param_idx, date_idx}, ... }
    overlay_js_data = json.dumps(overlay_data)

    # paramRanges: { "0": {min, max, name}, ... } keyed by param index
    param_ranges_js_dict = {}
    for i, param in enumerate(parameters):
        rng = param_ranges[param]
        param_ranges_js_dict[str(i)] = {
            "min": float(rng['min']),
            "max": float(rng['max']),
            "name": param,
        }
    param_ranges_js = json.dumps(param_ranges_js_dict)

    dates_js = json.dumps(dates_str)
    params_js = json.dumps(parameters)

    # ==============================
    #   CUSTOM HTML / JS CONTROLS
    # ==============================

    custom_controls = f'''
      <style>
          .leaflet-control-layers {{
              display: none !important;
          }}

          .custom-control-panel {{
              position: fixed;
              top: 120px;
              right: 10px;
              z-index: 1000;
              background: white;
              padding: 15px;
              border-radius: 8px;
              box-shadow: 0 2px 8px rgba(0,0,0,0.3);
              max-width: 280px;
              max-height: 500px;
              overflow-y: auto;
          }}
          .control-section {{
              margin-bottom: 15px;
          }}
          .control-section h3 {{
              margin: 0 0 10px 0;
              font-size: 16px;
              font-family: Arial, sans-serif;
              color: #333;
              border-bottom: 2px solid #4CAF50;
              padding-bottom: 5px;
          }}

          /* Legend styles */
          .legend-panel {{
              position: fixed;
              top: 120px;
              left: 10px;
              z-index: 1000;
              background: white;
              padding: 15px;
              border-radius: 8px;
              box-shadow: 0 2px 8px rgba(0,0,0,0.3);
              width: 200px;
          }}
          .legend-panel h3 {{
              margin: 0 0 10px 0;
              font-size: 16px;
              font-family: Arial, sans-serif;
              color: #333;
              border-bottom: 2px solid #4CAF50;
              padding-bottom: 5px;
          }}
          .legend-gradient {{
              width: 100%;
              height: 200px;
              background: linear-gradient(to top,
                  #440154, #472d7b, #3b528b, #2c728e,
                  #21918c, #28ae80, #5ec962, #addc30, #fde724);
              border: 1px solid #ccc;
              border-radius: 4px;
              margin: 10px 0;
          }}
          .legend-labels {{
              display: flex;
              flex-direction: column;
              justify-content: space-between;
              height: 200px;
              font-size: 12px;
              font-family: monospace;
          }}
          .legend-label {{
              display: flex;
              justify-content: space-between;
              align-items: center;
          }}
          .legend-tick {{
              width: 10px;
              height: 1px;
              background: #333;
              margin-right: 5px;
          }}
          .legend-param-name {{
              font-weight: bold;
              color: #4CAF50;
              margin-bottom: 5px;
              font-size: 13px;
          }}

          .date-slider-container {{
              position: fixed;
              bottom: 60px;
              left: 50%;
              transform: translateX(-50%);
              z-index: 1000;
              background: white;
              padding: 15px 30px;
              border-radius: 8px;
              box-shadow: 0 2px 8px rgba(0,0,0,0.3);
              min-width: 500px;
          }}
          .date-slider-container h3 {{
              margin: 0 0 10px 0;
              font-size: 16px;
              text-align: center;
              font-family: Arial, sans-serif;
              color: #333;
          }}
          .date-slider {{
              width: 100%;
              margin: 10px 0;
          }}
          .date-display {{
              text-align: center;
              font-size: 18px;
              font-weight: bold;
              color: #4CAF50;
              margin-top: 10px;
          }}
      </style>

      <!-- Legend Panel -->
      <div class="legend-panel">
          <h3>Legend</h3>
          <div class="legend-param-name" id="legendParamName">Parameter Name</div>
          <div style="display: flex; align-items: stretch;">
              <div class="legend-gradient"></div>
              <div class="legend-labels" id="legendLabels">
                  <div class="legend-label">
                      <div class="legend-tick"></div>
                      <span id="legendMax">Max</span>
                  </div>
                  <div class="legend-label">
                      <div class="legend-tick"></div>
                      <span id="legendMid">Mid</span>
                  </div>
                  <div class="legend-label">
                      <div class="legend-tick"></div>
                      <span id="legendMin">Min</span>
                  </div>
              </div>
          </div>
      </div>

      <!-- Right control panel -->
      <div class="custom-control-panel">
          <div class="control-section">
              <h3>Data Parameters</h3>
              {param_radios_html}
          </div>
          <div class="control-section">
              <h3>Base Map</h3>
              {tile_radios_html}
          </div>
      </div>

      <!-- Date slider -->
      <div class="date-slider-container">
          <h3>Select Date</h3>
          <input type="range" class="date-slider" id="dateSlider"
                 min="0" max="{len(dates_index) - 1}" value="0"
                 oninput="updateDataLayer()" step="1">
          <div class="date-display" id="dateDisplay">{dates_str[0]}</div>
      </div>

      <script>
          var overlayData = {overlay_js_data};
          var paramRanges = {param_ranges_js};
          var dates = {dates_js};
          var parameters = {params_js};

          var mapRef = null;
          var baseLayers = {{}};
          var currentOverlay = null;
          var currentParamIndex = 0;
          var currentDateIndex = 0;

          // Wait for map to be ready
          document.addEventListener('DOMContentLoaded', function() {{
              setTimeout(initializeMap, 500);
          }});

          function initializeMap() {{
              console.log('Initializing map...');

              // Find Folium map object on window
              for (var key in window) {{
                  if (window.hasOwnProperty(key)) {{
                      var val = window[key];
                      if (val && val._container &&
                          val._container.classList &&
                          val._container.classList.contains('folium-map')) {{
                          mapRef = val;
                          break;
                      }}
                  }}
              }}

              if (!mapRef) {{
                  console.error('Map not found, retrying...');
                  setTimeout(initializeMap, 500);
                  return;
              }}

              console.log('Map found.');

              // Store tile layers for switching
              mapRef.eachLayer(function(layer) {{
                  if (layer._url) {{
                      var tileName = getTileLayerName(layer);
                      if (tileName) {{
                          baseLayers[tileName] = layer;
                      }}
                  }}
              }});

              console.log('Base layers found:', Object.keys(baseLayers));

              updateLegend();
              updateDataLayer();
          }}

          function getTileLayerName(layer) {{
              if (!layer._url) return null;
              if (layer._url.indexOf('openstreetmap.org') !== -1) return 'OpenStreetMap';
              if (layer._url.indexOf('opentopomap.org') !== -1) return 'Topographic';
              if (layer._url.indexOf('cartocdn.com/light') !== -1 ||
                  layer._url.indexOf('cartodb.com/light') !== -1) return 'Light Map';
              if (layer._url.indexOf('cartocdn.com/dark') !== -1 ||
                  layer._url.indexOf('cartodb.com/dark') !== -1) return 'Dark Map';
              return null;
          }}

          function updateLegend() {{
              var key = String(currentParamIndex);
              var rangeInfo = paramRanges[key];
              if (!rangeInfo) return;

              var min = rangeInfo.min;
              var max = rangeInfo.max;
              var mid = (min + max) / 2.0;

              document.getElementById('legendParamName').textContent = rangeInfo.name;
              document.getElementById('legendMax').textContent = max.toFixed(2);
              document.getElementById('legendMid').textContent = mid.toFixed(2);
              document.getElementById('legendMin').textContent = min.toFixed(2);
          }}

          function updateDataLayer() {{
              if (!mapRef) {{
                  console.log('Map not ready yet');
                  return;
              }}

              // Parameter from radio
              var selectedParam = document.querySelector('input[name="parameter"]:checked');
              if (!selectedParam) {{
                  console.error('No parameter selected');
                  return;
              }}
              currentParamIndex = parseInt(selectedParam.value);

              updateLegend();

              // Date from slider
              var slider = document.getElementById('dateSlider');
              currentDateIndex = parseInt(slider.value);
              var selectedDate = dates[currentDateIndex];

              document.getElementById('dateDisplay').textContent = selectedDate;

              // Remove old overlay
              if (currentOverlay) {{
                  mapRef.removeLayer(currentOverlay);
                  currentOverlay = null;
              }}

              var targetLayerId = 'overlay_' + currentParamIndex + '_' + currentDateIndex;
              var overlayInfo = overlayData[targetLayerId];

              if (!overlayInfo) {{
                  console.error('No overlay data for:', targetLayerId);
                  return;
              }}

              currentOverlay = L.imageOverlay(
                  overlayInfo.image,
                  overlayInfo.bounds,
                  {{
                      opacity: {opacity},
                      interactive: false
                  }}
              );

              currentOverlay.addTo(mapRef);
          }}

          function updateBaseLayer() {{
              if (!mapRef) return;

              var selectedBase = document.querySelector('input[name="baselayer"]:checked');
              if (!selectedBase) return;
              selectedBase = selectedBase.value;

              for (var name in baseLayers) {{
                  if (!baseLayers.hasOwnProperty(name)) continue;
                  var layer = baseLayers[name];
                  if (!layer) continue;

                  if (name === selectedBase) {{
                      if (!mapRef.hasLayer(layer)) {{
                          mapRef.addLayer(layer);
                      }}
                  }} else {{
                      if (mapRef.hasLayer(layer)) {{
                          mapRef.removeLayer(layer);
                      }}
                  }}
              }}
          }}
      </script>
    '''

    # ---- Header bar ----
    header_html = f"""
      <div style="position: fixed;
                  top: 10px;
                  left: 50%;
                  transform: translateX(-50%);
                  z-index: 1000;
                  background: white;
                  padding: 15px 30px;
                  border-radius: 8px;
                  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                  display: flex;
                  align-items: center;
                  gap: 20px;">
          {logo_left_html}
          <h2 style="margin: 0; font-family: Arial, sans-serif; color: #333;">
              {custom_title_prefix}
          </h2>
          {logo_right_html}
      </div>
    """

    # ---- Watermark ----
    watermark_html = """
      <div style="position: fixed;
                  bottom: 20px;
                  left: 10px;
                  z-index: 1000;
                  background: rgba(255, 255, 255, 0.3);
                  padding: 8px 12px;
                  border-radius: 4px;
                  font-size: 11px;
                  color: rgba(0, 0, 0, 0.3);
                  pointer-events: none;">
          The FARMWISE API database was made by UPWR under Horizon Europe project No: 101135533
      </div>
    """

    # Attach custom HTML/JS to map
    m.get_root().html.add_child(folium.Element(header_html))
    m.get_root().html.add_child(folium.Element(custom_controls))
    m.get_root().html.add_child(folium.Element(watermark_html))

    html_string = m.get_root().render()

    file_size_mb = os.path.getsize(output_file) / 1024 / 1024
    print(f"\n✓ Saved Folium map to {output_file}")
    print(f"File size: {file_size_mb:.1f} MB")
    print(f"Total overlays: {len(overlay_data)}")

    return html_string

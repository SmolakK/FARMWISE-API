from s2sphere import CellId, LatLng, RegionCoverer, LatLngRect, Cell
from mappings.data_source_mapping import API_PATH_RANGES
from utils.overlap_checks import spatial_ranges_overlap, time_ranges_overlap
import importlib
import zarr

N = 56.0
S = 53.0
E = 22.2
W = 20.2
LEVEL = 16
TIME_FROM = '2017-01-01'
TIME_TO = '2019-04-22'
FACTORS = ['temperature', 'cloud cover']


def read_data(bounding_box, level, time_from, time_to, factors):
    data_storage = []
    north, south, east, west = bounding_box
    for k, v in API_PATH_RANGES.items():
        api_spatial_range = v[0]
        api_time_range = v[1]
        api_data_range = set(v[2])
        spatial_overlap = spatial_ranges_overlap(bounding_box, api_spatial_range)
        temporal_overlap = time_ranges_overlap((time_from, time_to), api_time_range)
        data_overlap = set(factors).intersection(api_data_range)
        if spatial_overlap and temporal_overlap and len(data_overlap) > 0:
            module = importlib.import_module(k)
            api_response_data = module.read_data(spatial_range=bounding_box, time_range=(time_from, time_to), data_range=factors,
                             level=level)
            data_storage.append(api_response_data) # TODO: comment, document, add function to join with coordinates, show some data
    nw = LatLng.from_degrees(north, west)
    se = LatLng.from_degrees(south, east)
    coverer = RegionCoverer()
    coverer.max_level = LEVEL
    coverer.min_level = LEVEL
    coverer.max_cells = 10_000  # FIXED not to crash
    rect_input = LatLngRect.from_point_pair(nw, se)
    covering = coverer.get_covering(rect_input)
    cell_ids = [int(cell_id.id()) for cell_id in covering]
    # Convert to Zarr array
    s_d_zarr = zarr.array(s_d_pivot)


read_data((N, S, E, W), LEVEL, TIME_FROM, TIME_TO, FACTORS)

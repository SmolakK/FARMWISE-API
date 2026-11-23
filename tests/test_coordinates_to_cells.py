import pandas as pd
import s2sphere
from farmwise_api.core.utils.coordinates_to_cells import prepare_coordinates


def test_prepare_coordinates_with_valid_data():
    # Input data
    coordinates = pd.DataFrame({
        'lat': [50.0, 49.5, 51.0],
        'lon': [14.0, 13.5, 15.0]
    })
    spatial_range = (51.5, 49.0, 15.5, 13.0)  # N, S, E, W
    level = 10

    # Call the function
    result = prepare_coordinates(coordinates, spatial_range, level)

    # Assert that the result is not None
    assert result is not None

    # Assert that the coordinates are limited to the spatial range
    for _, row in result.iterrows():
        assert 49.0 <= row.lat <= 51.5
        assert 13.0 <= row.lon <= 15.5

    # Assert that the S2CELL column exists
    assert 'S2CELL' in result.columns

    # Assert that S2CELL values are valid
    for cell_id in result['S2CELL']:
        assert isinstance(cell_id, s2sphere.CellId)


def test_prepare_coordinates_with_no_matching_coordinates():
    # Input data
    coordinates = pd.DataFrame({
        'lat': [52.0, 53.0, 54.0],  # Outside spatial range
        'lon': [16.0, 17.0, 18.0]   # Outside spatial range
    })
    spatial_range = (51.5, 49.0, 15.5, 13.0)  # N, S, E, W
    level = 10

    # Call the function
    result = prepare_coordinates(coordinates, spatial_range, level)

    # Assert that the result is None
    assert result is None


def test_prepare_coordinates_with_empty_dataframe():
    # Input data
    coordinates = pd.DataFrame(columns=['lat', 'lon'])  # Empty DataFrame
    spatial_range = (51.5, 49.0, 15.5, 13.0)  # N, S, E, W
    level = 10

    # Call the function
    result = prepare_coordinates(coordinates, spatial_range, level)

    # Assert that the result is None
    assert result is None


def test_prepare_coordinates_with_edge_case_coordinates():
    # Input data
    coordinates = pd.DataFrame({
        'lat': [51.5, 49.0],  # On the boundary of the spatial range
        'lon': [15.5, 13.0]   # On the boundary of the spatial range
    })
    spatial_range = (51.5, 49.0, 15.5, 13.0)  # N, S, E, W
    level = 10

    # Call the function
    result = prepare_coordinates(coordinates, spatial_range, level)

    # Assert that the result is not None
    assert result is not None

    # Assert that all coordinates are included
    assert len(result) == 2

    # Assert that the S2CELL column exists
    assert 'S2CELL' in result.columns

    # Assert that S2CELL values are valid
    for cell_id in result['S2CELL']:
        assert isinstance(cell_id, s2sphere.CellId)


def test_s2_cell_ids_match_s2sphere_everywhere():
    import numpy as np
    from farmwise_api.core.utils.coordinates_to_cells import s2_cell_ids

    rng = np.random.default_rng(7)
    # Random points on every cube face, plus poles, the antimeridian and
    # face edges, where the face choice and the projection are decided.
    lat = np.concatenate(
        [rng.uniform(-90, 90, 3000), [90, -90, 0, 0, 0, 45, -45, 35.26439]]
    ).astype(np.float32)
    lon = np.concatenate(
        [rng.uniform(-180, 180, 3000), [0, 0, 180, -180, 45, 45, -135, 45]]
    ).astype(np.float32)

    for level in (0, 1, 8, 13, 30):
        expected = [
            s2sphere.CellId.from_lat_lng(
                s2sphere.LatLng.from_degrees(float(a), float(b))
            ).parent(level).id()
            for a, b in zip(lat, lon)
        ]
        assert s2_cell_ids(lat, lon, level).tolist() == expected


def test_prepare_coordinates_shares_one_cell_object_per_cell():
    coordinates = pd.DataFrame({"lat": [50.0, 50.0001, 50.0], "lon": [14.0, 14.0001, 14.0]})

    result = prepare_coordinates(coordinates, (51.0, 49.0, 15.0, 13.0), 8)

    first, second, third = result["S2CELL"]
    assert first == second == third
    assert first is third

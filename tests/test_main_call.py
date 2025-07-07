import pytest
import pandas as pd
from s2sphere import CellId, LatLng
from unittest.mock import AsyncMock, MagicMock, patch

# Mock the API_PATH_RANGES dictionary
mock_api_path_ranges = {
    "mock_api_module": [
        (51.09, 50.00, 14.56, 14.14),  # Spatial range
        ('2017-01-01', '2017-01-15'),  # Temporal range
        ['temperature', 'precipitation']  # Data range
    ]
}

# Mock country bboxes
mock_country_bboxes = {
    'Poland': (51.09, 50.00, 14.56, 14.14),
    'Germany': (55.0, 47.0, 15.0, 5.0)
}

# Build real S2 cells
s2_cell_1 = CellId.from_lat_lng(LatLng.from_degrees(51.0, 14.5))
s2_cell_2 = CellId.from_lat_lng(LatLng.from_degrees(50.5, 14.2))


@pytest.mark.asyncio
@patch("mappings.data_source_mapping.API_PATH_RANGES", mock_api_path_ranges)
@patch("importlib.import_module")
@patch("utils.overlap_checks.spatial_ranges_overlap", return_value=True)
@patch("utils.overlap_checks.time_ranges_overlap", return_value=True)
@patch("utils.country_bboxes.return_country_bboxes", return_value=mock_country_bboxes)
async def test_read_data_with_bbox_and_country(mock_country_bboxes_func, mock_time_overlap, mock_spatial_overlap, mock_import_module):
    # Create MultiIndex for columns
    arrays = [
        ["Temperature", "Precipitation"],
        [s2_cell_1, s2_cell_2]
    ]
    multi_index = pd.MultiIndex.from_arrays(arrays)

    # Mock the API's `read_data` function
    mock_module = MagicMock()
    mock_module.read_data = AsyncMock(
        return_value=pd.DataFrame(
            data=[[5, 1.2], [6, 0.8]],
            index=pd.to_datetime(["2017-01-10", "2017-01-11"]),
            columns=multi_index
        )
    )
    mock_import_module.return_value = mock_module

    # Call the function under test
    from main_call import read_data
    result = await read_data(
        bounding_box=(51.09, 50.00, 14.56, 14.14),
        level=10,
        time_from="2017-01-10",
        time_to="2017-01-12",
        factors=["temperature", "precipitation"],
        separate_api=False,
        interpolation=False
    )

    # Assertions
    assert not result['data'].empty, "The result should not be empty"
    assert "Temperature" in result['data'].columns, "Temperature column is missing"
    assert "Precipitation" in result['data'].columns, "Precipitation column is missing"

    # --- Test with SINGLE COUNTRY ---
    result_single_country = await read_data(
        country="Poland",
        level=10,
        time_from="2017-01-10",
        time_to="2017-01-12",
        factors=["temperature", "precipitation"],
        separate_api=False,
        interpolation=False
    )

    # Assertions for single country
    assert result_single_country['data'] is not False, "The result should not be False (single country)"
    assert "Temperature" in result_single_country["data"].columns, "Temperature column is missing (single country)"
    assert "Precipitation" in result_single_country["data"].columns, "Precipitation column is missing (single country)"

    # --- Test with MULTIPLE COUNTRIES ---
    result_multi_country = await read_data(
        country=["Poland", "Germany"],
        level=10,
        time_from="2017-01-10",
        time_to="2017-01-12",
        factors=["temperature", "precipitation"],
        separate_api=False,
        interpolation=False
    )

    # Assertions for multiple countries
    assert result_multi_country['data'] is not False, "The result should not be False (multiple countries)"
    assert "Temperature" in result_multi_country["data"].columns, "Temperature column is missing (multiple countries)"
    assert "Precipitation" in result_multi_country["data"].columns, "Precipitation column is missing (multiple countries)"

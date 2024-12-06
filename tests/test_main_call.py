import pytest
import pandas as pd
from unittest.mock import AsyncMock, MagicMock, patch

# Mock the API_PATH_RANGES dictionary
mock_api_path_ranges = {
    "mock_api_module": [
        (51.09, 50.00, 14.56, 14.14),  # Spatial range
        ('2017-01-01', '2017-01-15'),  # Temporal range
        ['temperature', 'precipitation']  # Data range
    ]
}

@pytest.mark.asyncio
@patch("mappings.data_source_mapping.API_PATH_RANGES", mock_api_path_ranges)
@patch("importlib.import_module")
@patch("utils.overlap_checks.spatial_ranges_overlap", return_value=True)
@patch("utils.overlap_checks.time_ranges_overlap", return_value=True)
async def test_read_data(mock_time_overlap, mock_spatial_overlap, mock_import_module):
    # Mock the API's `read_data` function
    mock_module = MagicMock()
    mock_module.read_data = AsyncMock(
        return_value=pd.DataFrame({
            "Timestamp": ["2017-01-10", "2017-01-11"],
            "Temperature": [5, 6],
            "Precipitation": [1.2, 0.8]
        }).set_index("Timestamp")
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
    assert not result.empty, "The result should not be empty"
    assert "Temperature" in result.columns, "Temperature column is missing"
    assert "Precipitation" in result.columns, "Precipitation column is missing"
    mock_module.read_data.assert_awaited_once()
    mock_time_overlap.assert_called_once()
    mock_spatial_overlap.assert_called_once()

import pytest
import pandas as pd
import asyncio
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
@patch("core.main_call.API_PATH_RANGES", mock_api_path_ranges)
@patch("core.main_call.importlib.import_module")
@patch("core.main_call.spatial_ranges_overlap", return_value=True)
@patch("core.main_call.time_ranges_overlap", return_value=True)
@patch("core.main_call.COUNTRY_BBOXES", mock_country_bboxes)
async def test_read_data_with_bbox_and_country(mock_time_overlap, mock_spatial_overlap, mock_import_module):
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
    from core.main_call import read_data
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


@pytest.mark.asyncio
async def test_read_data_requires_country_or_bounding_box():
    from core.main_call import read_data

    with pytest.raises(ValueError, match="either a 'bounding_box' or a 'country'"):
        await read_data(
            level=10,
            time_from="2024-01-01",
            time_to="2024-01-02",
            factors=["temperature"],
        )


@pytest.mark.asyncio
async def test_read_data_rejects_unknown_country(monkeypatch):
    from core import main_call

    monkeypatch.setattr(main_call, "COUNTRY_BBOXES", {"Poland": (55, 49, 24, 14)})

    with pytest.raises(ValueError, match="Atlantis"):
        await main_call.read_data(
            country="Atlantis",
            level=10,
            time_from="2024-01-01",
            time_to="2024-01-02",
            factors=["temperature"],
        )


@pytest.mark.asyncio
async def test_read_data_skips_non_overlapping_sources(monkeypatch):
    from core import main_call

    monkeypatch.setattr(
        main_call,
        "API_PATH_RANGES",
        {"unused.adapter": [(55, 49, 24, 14), ("2020-01-01", "2030-01-01"), ["temperature"]]},
    )
    monkeypatch.setattr(main_call, "spatial_ranges_overlap", lambda *_args: False)
    import_module = MagicMock()
    monkeypatch.setattr(main_call.importlib, "import_module", import_module)

    result = await main_call.read_data(
        bounding_box=(55, 49, 24, 14),
        level=10,
        time_from="2024-01-01",
        time_to="2024-01-02",
        factors=["temperature"],
    )

    assert result.empty
    import_module.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [asyncio.TimeoutError(), RuntimeError("API failed")])
async def test_read_data_isolates_adapter_failures(monkeypatch, failure):
    from core import main_call

    monkeypatch.setattr(
        main_call,
        "API_PATH_RANGES",
        {"broken.adapter": [(55, 49, 24, 14), ("2020-01-01", "2030-01-01"), ["temperature"]]},
    )
    monkeypatch.setattr(main_call, "spatial_ranges_overlap", lambda *_args: True)
    monkeypatch.setattr(main_call, "time_ranges_overlap", lambda *_args: True)
    module = MagicMock()
    module.read_data = AsyncMock(side_effect=failure)
    monkeypatch.setattr(main_call.importlib, "import_module", lambda _name: module)

    result = await main_call.read_data(
        bounding_box=(55, 49, 24, 14),
        level=10,
        time_from="2024-01-01",
        time_to="2024-01-02",
        factors=["temperature"],
        timeout=0.1,
    )

    assert result.empty


@pytest.mark.asyncio
async def test_read_data_applies_separation_interpolation_and_map(monkeypatch):
    from core import main_call
    from core.utils import map_ploter

    cell = CellId.from_lat_lng(LatLng.from_degrees(51.0, 17.0)).parent(10)
    frame = pd.DataFrame(
        [[5.0]],
        index=pd.to_datetime(["2024-01-01"]),
        columns=pd.MultiIndex.from_tuples([("Temperature", cell)]),
    )
    module = MagicMock()
    module.read_data = AsyncMock(return_value=frame)
    monkeypatch.setattr(
        main_call,
        "API_PATH_RANGES",
        {"provider.adapter": [(55, 49, 24, 14), ("2020-01-01", "2030-01-01"), ["temperature"]]},
    )
    monkeypatch.setattr(main_call, "spatial_ranges_overlap", lambda *_args: True)
    monkeypatch.setattr(main_call, "time_ranges_overlap", lambda *_args: True)
    monkeypatch.setattr(main_call.importlib, "import_module", lambda _name: module)
    monkeypatch.setattr(main_call, "extract_bbox", lambda _cells: (51, 51, 17, 17))
    interpolate = MagicMock(side_effect=lambda data, *_args: data)
    monkeypatch.setattr(main_call, "interpolate", interpolate)
    create_map = MagicMock(return_value="<html>map</html>")
    monkeypatch.setattr(map_ploter, "create_folium_map", create_map)

    result = await main_call.read_data(
        bounding_box=(55, 49, 24, 14),
        level=10,
        time_from="2024-01-01",
        time_to="2024-01-02",
        factors=["temperature"],
        separate_api=True,
        interpolation=True,
        produce_map=True,
    )

    assert list(result["data"].columns.get_level_values(0)) == [
        "Temperature (adapter)"
    ]
    assert result["map"] == "<html>map</html>"
    assert result["metadata"]["apis"][0]["api_name"] == "adapter"
    interpolate.assert_called_once()
    create_map.assert_called_once_with(result["data"], downsample_factor=1)


@pytest.mark.asyncio
async def test_read_data_returns_empty_frame_when_concatenation_fails(monkeypatch):
    from core import main_call

    cell = CellId.from_lat_lng(LatLng.from_degrees(51.0, 17.0)).parent(10)
    frame = pd.DataFrame(
        [[5.0]],
        index=pd.to_datetime(["2024-01-01"]),
        columns=pd.MultiIndex.from_tuples([("Temperature", cell)]),
    )
    module = MagicMock()
    module.read_data = AsyncMock(return_value=frame)
    monkeypatch.setattr(
        main_call,
        "API_PATH_RANGES",
        {"provider.adapter": [(55, 49, 24, 14), ("2020-01-01", "2030-01-01"), ["temperature"]]},
    )
    monkeypatch.setattr(main_call, "spatial_ranges_overlap", lambda *_args: True)
    monkeypatch.setattr(main_call, "time_ranges_overlap", lambda *_args: True)
    monkeypatch.setattr(main_call.importlib, "import_module", lambda _name: module)
    monkeypatch.setattr(main_call, "extract_bbox", lambda _cells: (51, 51, 17, 17))
    monkeypatch.setattr(main_call.pd, "concat", MagicMock(side_effect=ValueError("bad frames")))

    result = await main_call.read_data(
        bounding_box=(55, 49, 24, 14),
        level=10,
        time_from="2024-01-01",
        time_to="2024-01-02",
        factors=["temperature"],
    )

    assert result.empty


@pytest.mark.asyncio
async def test_read_data_applies_source_weights_and_type_methods(monkeypatch):
    from core import main_call

    cell = CellId.from_lat_lng(LatLng.from_degrees(51.0, 17.0)).parent(10)
    columns = pd.MultiIndex.from_tuples(
        [("Temperature [C]", cell), ("Precipitation [mm]", cell)]
    )
    frames = {
        "provider.first": pd.DataFrame(
            [[10.0, 2.0]],
            index=pd.to_datetime(["2024-01-01"]),
            columns=columns,
        ),
        "provider.second": pd.DataFrame(
            [[20.0, 8.0]],
            index=pd.to_datetime(["2024-01-01"]),
            columns=columns,
        ),
    }
    modules = {}
    for source, frame in frames.items():
        module = MagicMock()
        module.read_data = AsyncMock(return_value=frame)
        modules[source] = module

    monkeypatch.setattr(
        main_call,
        "API_PATH_RANGES",
        {
            source: [
                (55, 49, 24, 14),
                ("2020-01-01", "2030-01-01"),
                ["temperature", "precipitation"],
            ]
            for source in frames
        },
    )
    monkeypatch.setattr(main_call, "spatial_ranges_overlap", lambda *_args: True)
    monkeypatch.setattr(main_call, "time_ranges_overlap", lambda *_args: True)
    monkeypatch.setattr(
        main_call.importlib, "import_module", lambda name: modules[name]
    )
    monkeypatch.setattr(main_call, "extract_bbox", lambda _cells: (51, 51, 17, 17))

    result = await main_call.read_data(
        bounding_box=(55, 49, 24, 14),
        level=10,
        time_from="2024-01-01",
        time_to="2024-01-02",
        factors=["temperature", "precipitation"],
        source_weights={"provider.first": 3.0, "provider.second": 1.0},
        harmonization_methods={"precipitation": "max"},
    )

    assert result["data"].loc[
        "2024-01-01", ("Temperature [C]", cell)
    ] == 12.5
    assert result["data"].loc[
        "2024-01-01", ("Precipitation [mm]", cell)
    ] == 8.0
    assert result["metadata"]["harmonization"]["source_weights"] == {
        "provider.first": 3.0,
        "provider.second": 1.0,
    }
    assert result["metadata"]["harmonization"]["methods"]["precipitation"] == "max"


@pytest.mark.asyncio
async def test_read_data_validates_harmonization_before_calling_sources(monkeypatch):
    from core import main_call

    import_module = MagicMock()
    monkeypatch.setattr(main_call.importlib, "import_module", import_module)

    with pytest.raises(ValueError, match="Unknown harmonization method"):
        await main_call.read_data(
            bounding_box=(55, 49, 24, 14),
            level=10,
            time_from="2024-01-01",
            time_to="2024-01-02",
            factors=["temperature"],
            harmonization_methods={"temperature": "not-a-method"},
        )

    import_module.assert_not_called()


def test_plan_source_dispatch_records_each_precheck_reason():
    from core.main_call import plan_source_dispatch

    plan = plan_source_dispatch(
        (55, 49, 24, 14),
        "2024-01-01",
        "2024-01-02",
        ["temperature"],
        source_ranges={
            "selected": [
                (55, 49, 24, 14),
                ("2020-01-01", "2030-01-01"),
                ["temperature"],
            ],
            "outside-space": [
                (45, 40, 10, 5),
                ("2020-01-01", "2030-01-01"),
                ["temperature"],
            ],
            "outside-time": [
                (55, 49, 24, 14),
                ("1990-01-01", "2000-01-01"),
                ["temperature"],
            ],
            "outside-factor": [
                (55, 49, 24, 14),
                ("2020-01-01", "2030-01-01"),
                ["soil"],
            ],
        },
    )

    assert [item["source"] for item in plan if item["dispatched"]] == ["selected"]
    assert sum(not item["dispatched"] for item in plan) == 3


@pytest.mark.asyncio
async def test_read_data_persists_per_source_quality_report(monkeypatch, tmp_path):
    from core import main_call

    cell = CellId.from_lat_lng(LatLng.from_degrees(51.0, 17.0)).parent(10)
    frame = pd.DataFrame(
        [[5.0]],
        index=pd.to_datetime(["2024-01-01"]),
        columns=pd.MultiIndex.from_tuples([("Temperature", cell)]),
    )
    module = MagicMock()
    module.read_data = AsyncMock(return_value=frame)
    monkeypatch.setattr(
        main_call,
        "API_PATH_RANGES",
        {
            "provider.adapter": [
                (55, 49, 24, 14),
                ("2020-01-01", "2030-01-01"),
                ["temperature"],
            ],
            "provider.unused": [
                (45, 40, 10, 5),
                ("2020-01-01", "2030-01-01"),
                ["temperature"],
            ],
        },
    )
    monkeypatch.setattr(main_call.importlib, "import_module", lambda _name: module)
    monkeypatch.setattr(main_call, "extract_bbox", lambda _cells: (51, 51, 17, 17))
    monkeypatch.setattr(
        main_call,
        "assess_data_quality",
        MagicMock(return_value={"api_name": "adapter", "S2_completeness": 1.0}),
    )

    result = await main_call.read_data(
        bounding_box=(55, 49, 24, 14),
        level=10,
        time_from="2024-01-01",
        time_to="2024-01-02",
        factors=["temperature"],
        quality_report_dir=tmp_path,
    )

    reports = result["metadata"]["quality_reports"]
    assert len(reports) == 1
    assert reports[0]["S2_completeness"] == 1
    assert pd.notna(reports[0]["report_path"])
    assert len(list(tmp_path.glob("*.json"))) == 1
    assert result["metadata"]["coverage_precheck"]["candidate_sources"] == 2
    assert result["metadata"]["coverage_precheck"]["dispatched_sources"] == 1
    assert result["metadata"]["coverage_precheck"]["requests_avoided"] == 1
    assert result["metadata"]["dispatch"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_read_data_can_skip_quality_assessment(monkeypatch):
    from core import main_call

    cell = CellId.from_lat_lng(LatLng.from_degrees(51.0, 17.0)).parent(10)
    frame = pd.DataFrame(
        [[5.0]],
        index=pd.to_datetime(["2024-01-01"]),
        columns=pd.MultiIndex.from_tuples([("Temperature", cell)]),
    )
    module = MagicMock()
    module.read_data = AsyncMock(return_value=frame)
    monkeypatch.setattr(
        main_call,
        "API_PATH_RANGES",
        {
            "provider.adapter": [
                (55, 49, 24, 14),
                ("2020-01-01", "2030-01-01"),
                ["temperature"],
            ]
        },
    )
    monkeypatch.setattr(main_call.importlib, "import_module", lambda _name: module)
    monkeypatch.setattr(main_call, "extract_bbox", lambda _cells: (51, 51, 17, 17))
    assess = MagicMock()
    monkeypatch.setattr(main_call, "assess_data_quality", assess)

    result = await main_call.read_data(
        bounding_box=(55, 49, 24, 14),
        level=10,
        time_from="2024-01-01",
        time_to="2024-01-02",
        factors=["temperature"],
        assess_quality=False,
    )

    assess.assert_not_called()
    assert result["metadata"]["quality_reports"] == []
    assert result["metadata"]["quality_assessment"] == {
        "enabled": False,
        "sources_assessed": 0,
        "final_wait_seconds": pytest.approx(0, abs=0.01),
    }


@pytest.mark.asyncio
async def test_source_quality_assessments_run_concurrently(monkeypatch):
    from threading import Barrier
    from core import main_call

    cell = CellId.from_lat_lng(LatLng.from_degrees(51.0, 17.0)).parent(10)
    frame = pd.DataFrame(
        [[5.0]],
        index=pd.to_datetime(["2024-01-01"]),
        columns=pd.MultiIndex.from_tuples([("Temperature", cell)]),
    )
    modules = {}
    for source in ("provider.first", "provider.second"):
        module = MagicMock()
        module.read_data = AsyncMock(return_value=frame)
        modules[source] = module
    monkeypatch.setattr(
        main_call,
        "API_PATH_RANGES",
        {
            source: [
                (55, 49, 24, 14),
                ("2020-01-01", "2030-01-01"),
                ["temperature"],
            ]
            for source in modules
        },
    )
    monkeypatch.setattr(
        main_call.importlib, "import_module", lambda name: modules[name]
    )
    monkeypatch.setattr(main_call, "extract_bbox", lambda _cells: (51, 51, 17, 17))
    barrier = Barrier(2)

    def assess(_frame, metadata, _ranges, _request):
        barrier.wait(timeout=2)
        return {"api_name": metadata["api_name"]}

    monkeypatch.setattr(main_call, "assess_data_quality", assess)

    result = await main_call.read_data(
        bounding_box=(55, 49, 24, 14),
        level=10,
        time_from="2024-01-01",
        time_to="2024-01-02",
        factors=["temperature"],
        persist_quality_reports=False,
    )

    assert {
        report["api_name"] for report in result["metadata"]["quality_reports"]
    } == {"first", "second"}
    assert all(
        report.get("status") != "error"
        for report in result["metadata"]["quality_reports"]
    )

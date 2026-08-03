import pytest
import asyncio
from unittest.mock import patch, MagicMock
import pandas as pd
from threading import Event, current_thread, enumerate as enumerate_threads

ORIGINAL_ASYNCIO_TASK = asyncio.Task

from adapters.API_readers.gios_gw import gios_gw
from adapters.API_readers.wetterdienst.wetterdienst_dwd import (
    _DwdFetchCancelled,
    _collect_request,
    _reject_incompatible_pydevd_asyncio_patch,
    fetch_data,
    read_data,
)


@pytest.mark.asyncio
@patch("adapters.API_readers.wetterdienst.wetterdienst_dwd.prepare_coordinates")
@patch("adapters.API_readers.wetterdienst.wetterdienst_dwd.DwdObservationRequest")
async def test_read_data(mock_dwd_request, mock_prepare_coordinates):
    # Mock DwdObservationRequest
    mock_request_instance = MagicMock()
    mock_dwd_request.return_value = mock_request_instance

    # Mock the request.filter_by_bbox method to return the same mock instance
    mock_request_instance.filter_by_bbox.return_value = mock_request_instance
    mock_request_instance.values.query = None

    # Mock the to_dict method
    mock_request_instance.values.all.return_value.to_dict.return_value = {
        "stations": [
            {
                "station_id": "02225",
                "start_date": "1922-01-01T00:00:00+00:00",
                "end_date": "1984-09-30T00:00:00+00:00",
                "latitude": 50.9167,
                "longitude": 14.3667,
                "height": 385.0,
                "name": "Hinterhermsdorf",
                "state": "Sachsen"
            },
            {
                "station_id": "02985",
                "start_date": "1991-01-01T00:00:00+00:00",
                "end_date": "2024-12-02T00:00:00+00:00",
                "latitude": 50.9383,
                "longitude": 14.2094,
                "height": 321.0,
                "name": "Lichtenhain-Mittelndorf",
                "state": "Sachsen"
            },
            {
                "station_id": "06129",
                "start_date": "1999-05-01T00:00:00+00:00",
                "end_date": "2024-12-02T00:00:00+00:00",
                "latitude": 51.0594,
                "longitude": 14.4266,
                "height": 291.0,
                "name": "Sohland/Spree",
                "state": "Sachsen"
            }
        ],
        "values": [
            {
                "station_id": "02225",
                "dataset": "climate_summary",
                "parameter": "precipitation_height",
                "date": "2017-01-10T00:00:00+00:00",
                "value": None,
                "quality": None
            },
            {
                "station_id": "02225",
                "dataset": "climate_summary",
                "parameter": "temperature_air_mean_2m",
                "date": "2017-01-11T00:00:00+00:00",
                "value": None,
                "quality": None
            },
            {
                "station_id": "02985",
                "dataset": "climate_summary",
                "parameter": "precipitation_height",
                "date": "2017-01-10T00:00:00+00:00",
                "value": 0.0,
                "quality": 9.0
            },
            {
                "station_id": "02985",
                "dataset": "climate_summary",
                "parameter": "temperature_air_mean_2m",
                "date": "2017-01-10T00:00:00+00:00",
                "value": 267.95,
                "quality": 9.0
            },
        ]
    }

    # Mock prepare_coordinates
    def mock_prepare(df, spatial_range, level):
        df["S2CELL"] = ["cell1"]
        return df

    mock_prepare_coordinates.side_effect = mock_prepare

    # Test parameters
    spatial_range = (51.0, 49.0, 12.0, 9.0)
    time_range = ("2017-01-01", "2017-01-12")
    data_range = ["temperature", "precipitation"]
    level = 8

    # Call the function under test
    result = await read_data(spatial_range, time_range, data_range, level)

    # Assertions
    assert result is not None
    assert isinstance(result, pd.DataFrame)
    assert "Temperature [°C]" in result.columns.levels[0]
    assert "Precipitation total [mm]" in result.columns.levels[0]
    assert "cell1" in result.columns.levels[1]
    mock_prepare_coordinates.assert_called_once()
    assert result['Temperature [°C]'].values[0][0] == pytest.approx(-5.2)  # validate temperature convertion
    assert isinstance(result.index, pd.DatetimeIndex)


def test_collect_request_stops_between_station_downloads():
    first_result = MagicMock()
    first_result.df = pd.DataFrame({"value": [1.0]})
    second_result = MagicMock()
    second_result.df = pd.DataFrame({"value": [2.0]})
    cancel_event = Event()

    class Values:
        def query(self):
            yield first_result
            cancel_event.set()
            yield second_result

    request = MagicMock()
    request.values = Values()

    with pytest.raises(_DwdFetchCancelled):
        _collect_request(request, cancel_event)


@pytest.mark.asyncio
async def test_fetch_data_closes_worker_after_cancellation():
    entered = Event()
    release = Event()
    result = MagicMock()
    result.df = pd.DataFrame({"value": [1.0]})

    class Values:
        def query(self):
            entered.set()
            release.wait(timeout=2)
            yield result

    request = MagicMock()
    request.values = Values()
    request.df = pd.DataFrame({"station_id": ["1"]})

    with patch(
        "adapters.API_readers.wetterdienst.wetterdienst_dwd.DwdObservationRequest",
        return_value=MagicMock(filter_by_bbox=MagicMock(return_value=request)),
    ):
        task = asyncio.create_task(
            fetch_data(["precipitation_height"], None, None, (9, 49, 12, 51))
        )
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        await asyncio.sleep(0)
        release.set()

        with pytest.raises(asyncio.CancelledError):
            await task

    assert not any(
        thread.name.startswith("farmwise-dwd")
        for thread in enumerate_threads()
    )


@pytest.mark.asyncio
async def test_fetch_data_builds_request_outside_event_loop_thread():
    worker_name = None
    request = MagicMock()
    request.values.query = None
    request.values.all.return_value.to_dict.return_value = {
        "values": [],
        "stations": [],
    }

    def build_request(*_args, **_kwargs):
        nonlocal worker_name
        worker_name = current_thread().name
        return MagicMock(filter_by_bbox=MagicMock(return_value=request))

    with patch(
        "adapters.API_readers.wetterdienst.wetterdienst_dwd.DwdObservationRequest",
        side_effect=build_request,
    ):
        await fetch_data(
            ["precipitation_height"],
            None,
            None,
            (9, 49, 12, 51),
        )

    assert worker_name.startswith("farmwise-dwd")


def test_importing_gios_does_not_patch_asyncio_tasks():
    assert "nest_asyncio" not in gios_gw.__dict__
    assert asyncio.Task is ORIGINAL_ASYNCIO_TASK


def test_incompatible_pydevd_task_patch_has_actionable_error(monkeypatch):
    class PyCharmTask:
        _pydevd_nest_patched = True

        def __init__(self, coro, loop=None, name=None, context=None):
            pass

    monkeypatch.setattr(asyncio, "Task", PyCharmTask)

    with pytest.raises(RuntimeError, match="python.debug.asyncio.repl"):
        _reject_incompatible_pydevd_asyncio_patch()

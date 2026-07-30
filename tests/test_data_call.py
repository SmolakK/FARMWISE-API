import asyncio
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from fastapi import BackgroundTasks, HTTPException

from server.routers import data_call


def _request(tmp_path):
    state = SimpleNamespace(temp_dir=str(tmp_path))
    app = SimpleNamespace(state=state)
    return SimpleNamespace(app=app)


def _body(produce_map=False):
    return SimpleNamespace(
        bounding_box=(55.0, 49.0, 24.0, 14.0),
        country=None,
        level=10,
        time_from="2024-01-01",
        time_to="2024-01-02",
        factors=["temperature"],
        separate_api=False,
        interpolation=False,
        produce_map=produce_map,
    )


def _result(include_map=False):
    result = {
        "data": pd.DataFrame({"temperature": [5.0]}, index=["2024-01-01"]),
        "metadata": {"apis": [{"api_name": "mock"}]},
    }
    if include_map:
        result["map"] = "<html>map</html>"
    return result


def _endpoint(function):
    return inspect.unwrap(function)


@pytest.mark.asyncio
async def test_monitor_client_disconnection_returns_when_stop_requested():
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    stop_event = asyncio.Event()
    stop_event.set()

    assert (
        await data_call.monitor_client_disconnection(request, stop_event) is None
    )


@pytest.mark.asyncio
async def test_monitor_client_disconnection_raises_499():
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=True))

    with pytest.raises(HTTPException) as exc_info:
        await data_call.monitor_client_disconnection(request, asyncio.Event())

    assert exc_info.value.status_code == 499


@pytest.mark.asyncio
async def test_monitor_client_disconnection_translates_cancellation_to_499():
    request = SimpleNamespace(
        is_disconnected=AsyncMock(side_effect=asyncio.CancelledError)
    )

    with pytest.raises(HTTPException) as exc_info:
        await data_call.monitor_client_disconnection(request, asyncio.Event())

    assert exc_info.value.status_code == 499


@pytest.mark.asyncio
async def test_process_and_send_email_writes_files_and_sends_links(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(data_call, "read_data", AsyncMock(return_value=_result()))
    send_email = MagicMock()
    monkeypatch.setattr(data_call, "send_email", send_email)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://farmwise.test")

    await data_call.process_and_send_email(
        _body(), _request(tmp_path), "user@example.test"
    )

    files = list(tmp_path.iterdir())
    assert {path.suffix for path in files} == {".csv", ".json"}
    metadata_file = next(path for path in files if path.suffix == ".json")
    assert json.loads(metadata_file.read_text())["apis"][0]["api_name"] == "mock"
    send_email.assert_called_once()
    assert "https://farmwise.test/download/" in send_email.call_args.args[2]


@pytest.mark.asyncio
async def test_process_and_send_email_reports_no_data(monkeypatch, tmp_path):
    monkeypatch.setattr(data_call, "read_data", AsyncMock(return_value=pd.DataFrame()))
    send_email = MagicMock()
    monkeypatch.setattr(data_call, "send_email", send_email)

    await data_call.process_and_send_email(
        _body(), _request(tmp_path), "user@example.test"
    )

    send_email.assert_called_once_with(
        "user@example.test",
        "Data Processing Failed",
        "No data available for the selected parameters.",
    )


@pytest.mark.asyncio
async def test_process_and_send_email_handles_processing_error(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        data_call, "read_data", AsyncMock(side_effect=RuntimeError("failed"))
    )
    send_email = MagicMock()
    monkeypatch.setattr(data_call, "send_email", send_email)

    await data_call.process_and_send_email(
        _body(), _request(tmp_path), "user@example.test"
    )

    send_email.assert_called_once_with(
        "user@example.test",
        "Data Processing Failed",
        "An internal error occurred during data processing.",
    )


@pytest.mark.asyncio
async def test_read_data_endpoint_writes_map_and_sends_email(monkeypatch, tmp_path):
    monkeypatch.setattr(
        data_call, "read_data", AsyncMock(return_value=_result(include_map=True))
    )
    send_email = MagicMock()
    monkeypatch.setattr(data_call, "send_email", send_email)
    monkeypatch.setenv("PUBLIC_BASE_URL", "farmwise.test")
    user = SimpleNamespace(email="user@example.test")

    response = await _endpoint(data_call.read_data_endpoint)(
        _body(produce_map=True), _request(tmp_path), user
    )

    assert response.startswith("Data processing completed")
    assert {path.suffix for path in tmp_path.iterdir()} == {".csv", ".json", ".html"}
    assert "Map File: http://farmwise.test/download/" in send_email.call_args.args[2]


@pytest.mark.asyncio
async def test_read_data_endpoint_handles_requested_map_without_map_data(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(data_call, "read_data", AsyncMock(return_value=_result()))
    send_email = MagicMock()
    monkeypatch.setattr(data_call, "send_email", send_email)

    response = await _endpoint(data_call.read_data_endpoint)(
        _body(produce_map=True),
        _request(tmp_path),
        SimpleNamespace(email="user@example.test"),
    )

    assert response.startswith("Data processing completed")
    assert not list(tmp_path.glob("*.html"))
    assert "Map File:" not in send_email.call_args.args[2]


@pytest.mark.asyncio
async def test_read_data_endpoint_returns_failure_for_empty_result(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(data_call, "read_data", AsyncMock(return_value=pd.DataFrame()))

    response = await _endpoint(data_call.read_data_endpoint)(
        _body(), _request(tmp_path), SimpleNamespace(email="user@example.test")
    )

    assert response["status"] == "failure"


@pytest.mark.asyncio
async def test_read_data_direct_returns_download_urls(monkeypatch, tmp_path):
    monkeypatch.setattr(
        data_call, "read_data", AsyncMock(return_value=_result(include_map=True))
    )
    monkeypatch.setenv("PUBLIC_BASE_URL", "farmwise.test")

    response = await _endpoint(data_call.read_data_direct)(
        _body(produce_map=True),
        _request(tmp_path),
        SimpleNamespace(email="user@example.test"),
    )

    assert response["status"] == "success"
    assert response["data_url"].startswith("http://farmwise.test/download/")
    assert response["metadata_url"].startswith("http://farmwise.test/download/")
    assert response["map_url"].startswith("http://farmwise.test/download/")


@pytest.mark.asyncio
async def test_read_data_direct_returns_404_for_empty_result(monkeypatch, tmp_path):
    monkeypatch.setattr(data_call, "read_data", AsyncMock(return_value=pd.DataFrame()))

    with pytest.raises(HTTPException) as exc_info:
        await _endpoint(data_call.read_data_direct)(
            _body(), _request(tmp_path), SimpleNamespace(email="user@example.test")
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_read_data_direct_translates_unexpected_error(monkeypatch, tmp_path):
    monkeypatch.setattr(
        data_call, "read_data", AsyncMock(side_effect=RuntimeError("failed"))
    )

    with pytest.raises(HTTPException) as exc_info:
        await _endpoint(data_call.read_data_direct)(
            _body(), _request(tmp_path), SimpleNamespace(email="user@example.test")
        )

    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_download_file_returns_file_response(tmp_path):
    file_path = tmp_path / "result.csv"
    file_path.write_text("value\n1\n", encoding="utf-8")

    response = await data_call.download_file(
        file_path.name, BackgroundTasks(), _request(tmp_path)
    )

    assert Path(response.path) == file_path
    assert response.filename == file_path.name


@pytest.mark.asyncio
async def test_download_file_rejects_invalid_filename(tmp_path):
    with pytest.raises(HTTPException) as exc_info:
        await data_call.download_file(
            "invalid-name.toolong", BackgroundTasks(), _request(tmp_path)
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_download_file_returns_404_when_file_is_missing(tmp_path):
    with pytest.raises(HTTPException) as exc_info:
        await data_call.download_file(
            "missing.csv", BackgroundTasks(), _request(tmp_path)
        )

    assert exc_info.value.status_code == 404

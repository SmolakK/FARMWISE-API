"""Synchronous and asynchronous behaviour of /read-data-direct and /jobs/{id}."""

import asyncio
import json
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import HTTPException

from farmwise_api.server import jobs
from farmwise_api.server.routers import data_call
from farmwise_api.server.schemas import ReadDataRequest

USER = SimpleNamespace(username="alice", email="alice@example.org")


def _request(**overrides) -> ReadDataRequest:
    payload = {
        "country": ["Poland"],
        "level": 10,
        "time_from": "2018-01-01",
        "time_to": "2018-01-02",
        "factors": ["temperature"],
    }
    payload.update(overrides)
    return ReadDataRequest(**payload)


def _http_request(tmp_path):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(temp_dir=str(tmp_path))))


def _result():
    frame = pd.DataFrame({"value": [1.0]}, index=pd.to_datetime(["2018-01-01"]))
    return {"data": frame, "metadata": {"dispatch": []}}


@pytest.fixture(autouse=True)
def fresh_registry(monkeypatch):
    monkeypatch.setattr(jobs, "registry", jobs.JobRegistry())


@pytest.mark.asyncio
async def test_sync_mode_returns_links_and_an_explicit_status(monkeypatch, tmp_path):
    monkeypatch.setattr(data_call, "read_data", lambda **_kwargs: _future(_result()))

    response = await data_call.read_data_direct.__wrapped__(
        request_body=_request(), request=_http_request(tmp_path), current_user=USER,
    )

    assert response["status"] == jobs.SUCCESS
    assert response["data_url"].endswith(".csv")
    assert response["metadata_url"].endswith(".json")
    assert response["map_url"] is None


@pytest.mark.asyncio
async def test_sync_mode_reports_no_data_as_404_with_an_error_code(monkeypatch, tmp_path):
    monkeypatch.setattr(
        data_call, "read_data", lambda **_kwargs: _future({"data": pd.DataFrame()})
    )

    with pytest.raises(HTTPException) as exc_info:
        await data_call.read_data_direct.__wrapped__(
            request_body=_request(), request=_http_request(tmp_path), current_user=USER,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error_code"] == "no_data"


@pytest.mark.asyncio
async def test_async_mode_accepts_immediately_then_reports_success(monkeypatch, tmp_path):
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_read_data(**_kwargs):
        started.set()
        await release.wait()
        return _result()

    monkeypatch.setattr(data_call, "read_data", slow_read_data)

    accepted = await data_call.read_data_direct.__wrapped__(
        request_body=_request(mode="async"),
        request=_http_request(tmp_path), current_user=USER,
    )

    assert accepted.status_code == 202
    body = json.loads(accepted.body.decode())
    assert body["status"] == jobs.ACCEPTED
    assert body["status_url"].endswith(f"/jobs/{body['job_id']}")
    job_id = body["job_id"]
    await started.wait()
    running = await data_call.read_job_status.__wrapped__(
        job_id=job_id, request=_http_request(tmp_path), current_user=USER,
    )
    assert running["status"] == jobs.RUNNING
    assert running["started_utc"] is not None

    release.set()
    await asyncio.sleep(0)  # let the background task finish
    for _ in range(50):
        finished = await data_call.read_job_status.__wrapped__(
            job_id=job_id, request=_http_request(tmp_path), current_user=USER,
        )
        if finished["status"] in jobs.TERMINAL_STATUSES:
            break
        await asyncio.sleep(0.01)

    assert finished["status"] == jobs.SUCCESS
    assert finished["data_url"].endswith(".csv")
    assert finished["finished_utc"] is not None


@pytest.mark.asyncio
async def test_async_failure_is_recorded_on_the_job_not_raised(monkeypatch, tmp_path):
    async def failing_read_data(**_kwargs):
        raise RuntimeError("upstream exploded")

    monkeypatch.setattr(data_call, "read_data", failing_read_data)
    job = jobs.registry.create(owner=USER.username)

    await data_call.run_direct_job(job.job_id, _request(), str(tmp_path))

    state = jobs.registry.get(job.job_id, owner=USER.username).as_response()
    assert state["status"] == jobs.ERROR
    assert state["error_code"] == "internal_error"
    # The upstream message must not reach the client.
    assert "exploded" not in state["message"]


@pytest.mark.asyncio
async def test_a_job_is_not_readable_by_another_user(tmp_path):
    job = jobs.registry.create(owner="alice")
    other = SimpleNamespace(username="mallory", email="mallory@example.org")

    with pytest.raises(HTTPException) as exc_info:
        await data_call.read_job_status.__wrapped__(
            job_id=job.job_id, request=_http_request(tmp_path), current_user=other,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error_code"] == "unknown_job"


def test_expired_jobs_are_purged():
    from datetime import timedelta

    registry = jobs.JobRegistry(retention=timedelta(seconds=0))
    job = registry.create(owner="alice")

    assert registry.purge_expired() == 1
    assert registry.get(job.job_id, owner="alice") is None


def _future(value):
    """Wrap a value so a plain lambda can stand in for an async call."""
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    future.set_result(value)
    return future


@pytest.mark.asyncio
async def test_a_finished_job_is_logged(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(data_call, "read_data", lambda **_kwargs: _future(_result()))
    job = jobs.registry.create(owner=USER.username)

    with caplog.at_level("INFO", logger=data_call.logger.name):
        await data_call.run_direct_job(job.job_id, _request(), str(tmp_path))

    assert any(job.job_id in record.message and "succeeded" in record.message
               for record in caplog.records)


@pytest.mark.asyncio
async def test_results_are_written_even_if_the_temp_directory_disappeared(monkeypatch, tmp_path):
    """Another instance shutting down removes the shared temp directory."""
    monkeypatch.setattr(data_call, "read_data", lambda **_kwargs: _future(_result()))
    missing = tmp_path / "removed-while-running"

    response = await data_call.read_data_direct.__wrapped__(
        request_body=_request(),
        request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(temp_dir=str(missing)))),
        current_user=USER,
    )

    assert response["status"] == jobs.SUCCESS
    assert missing.is_dir()

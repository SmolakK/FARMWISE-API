"""The worker count must match how asynchronous job state is stored.

Job records for ``/read-data-direct`` with ``"mode": "async"`` live in the
registry in :mod:`farmwise_api.server.jobs`. While that registry is local to
one process, a second worker would answer ``GET /jobs/{job_id}`` for a job it
has never seen, so most polls would fail with ``unknown_job``. These tests fail
if the two ever disagree.
"""

import ast
from pathlib import Path

import pytest

from farmwise_api.server.jobs import registry

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "farmwise_api"


def _uvicorn_worker_counts(path: Path):
    """Yield (line, workers) for every uvicorn.run call that sets workers."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        called = (
            isinstance(function, ast.Attribute)
            and function.attr == "run"
            and isinstance(function.value, ast.Name)
            and function.value.id == "uvicorn"
        )
        if not called:
            continue
        for keyword in node.keywords:
            if keyword.arg == "workers":
                yield node.lineno, ast.literal_eval(keyword.value)


def _entry_points():
    return sorted(
        path for path in PACKAGE_ROOT.rglob("*.py")
        if "uvicorn.run" in path.read_text(encoding="utf-8")
    )


def test_the_server_runs_one_worker_while_job_state_is_process_local():
    assert _entry_points(), "no uvicorn entry point found"
    for path in _entry_points():
        for line, workers in _uvicorn_worker_counts(path):
            if registry.is_shared:
                continue  # a shared store makes several workers safe
            assert workers == 1, (
                f"{path.name}:{line} starts {workers} uvicorn workers, but "
                "asynchronous job records are process-local; either keep one "
                "worker or move the registry to a shared store."
            )


def test_a_process_local_registry_is_not_advertised_as_shared():
    """``is_shared`` is what the check above trusts, so it must stay honest."""
    from farmwise_api.server.jobs import JobRegistry

    assert JobRegistry.is_shared is False
    assert isinstance(registry, JobRegistry)


@pytest.mark.parametrize("workers, shared, expected_failure", [
    (4, False, True),
    (1, False, False),
])
def test_the_check_itself_detects_a_mismatch(tmp_path, monkeypatch, workers, shared, expected_failure):
    """Guard against the check silently passing everything."""
    module = tmp_path / "entry.py"
    module.write_text(
        f"import uvicorn\nuvicorn.run('app', workers={workers})\n", encoding="utf-8"
    )
    monkeypatch.setattr(registry, "is_shared", shared, raising=False)

    found = [count for _line, count in _uvicorn_worker_counts(module)]

    assert found == [workers]
    assert (not registry.is_shared and found != [1]) is expected_failure

"""In-process registry of asynchronous ``/read-data-direct`` jobs.

A job is created when a request is accepted, updated while the core call runs,
and read back through ``GET /jobs/{job_id}``. Only the user who created a job
can read it, so a leaked job id cannot expose another user's results.

The registry lives in the server process: it is not shared between worker
processes and does not survive a restart. Run the public server with a single
worker, or replace this module with a shared store, before scaling out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import threading
from uuid import uuid4

# Statuses a client may observe. "success" is spelled as in the synchronous
# response so that both paths use one vocabulary.
ACCEPTED = "accepted"
RUNNING = "running"
SUCCESS = "success"
NO_DATA = "no_data"
ERROR = "error"

TERMINAL_STATUSES = (SUCCESS, NO_DATA, ERROR)

# Results are kept a little longer than the downloadable files, so a client
# that polls late is told the job expired instead of receiving a dead link.
DEFAULT_RETENTION = timedelta(hours=3)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Job:
    """One accepted request and whatever is known about it so far."""

    job_id: str
    owner: str
    status: str = ACCEPTED
    created_utc: datetime = field(default_factory=_now)
    started_utc: datetime | None = None
    finished_utc: datetime | None = None
    result: dict | None = None
    error_code: str | None = None
    message: str | None = None

    def as_response(self) -> dict:
        """The public representation, without the owner."""
        payload = {
            "job_id": self.job_id,
            "status": self.status,
            "created_utc": self.created_utc.isoformat(),
            "started_utc": self.started_utc.isoformat() if self.started_utc else None,
            "finished_utc": self.finished_utc.isoformat() if self.finished_utc else None,
            "error_code": self.error_code,
            "message": self.message,
        }
        payload.update(self.result or {})
        return payload


class JobRegistry:
    """Thread-safe job store; the scheduler purges it from another thread."""

    # False while jobs live in this process only. A replacement backed by a
    # database or Redis sets it True, which is what allows the server to be
    # run with more than one worker (see tests/test_server_workers.py).
    is_shared = False

    def __init__(self, retention: timedelta = DEFAULT_RETENTION):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self.retention = retention

    def create(self, owner: str) -> Job:
        job = Job(job_id=uuid4().hex, owner=owner)
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str, owner: str) -> Job | None:
        """Return the job only when it belongs to ``owner``."""
        with self._lock:
            job = self._jobs.get(job_id)
            return job if job is not None and job.owner == owner else None

    def mark_running(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.status = RUNNING
                job.started_utc = _now()

    def finish(self, job_id: str, status: str, *, result: dict | None = None,
               error_code: str | None = None, message: str | None = None) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = status
            job.finished_utc = _now()
            job.result = result
            job.error_code = error_code
            job.message = message

    def purge_expired(self, now: datetime | None = None) -> int:
        """Drop jobs older than the retention window; returns how many went."""
        cutoff = (now or _now()) - self.retention
        with self._lock:
            expired = [
                job_id for job_id, job in self._jobs.items()
                if job.created_utc <= cutoff
            ]
            for job_id in expired:
                del self._jobs[job_id]
        return len(expired)

    def __len__(self) -> int:
        with self._lock:
            return len(self._jobs)


registry = JobRegistry()

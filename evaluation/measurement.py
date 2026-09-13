"""Memory measurement and reproducibility metadata for empirical runs."""

from __future__ import annotations

from datetime import datetime, timezone
import gc
import hashlib
import importlib.metadata
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import tracemalloc

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCKFILE = REPO_ROOT / "requirements-lock.txt"
MB = 1024 * 1024

try:  # psutil is part of the "evaluation" extra, not a core dependency.
    import psutil
except ImportError:  # pragma: no cover - exercised when the extra is absent
    psutil = None


def _process_rss_bytes() -> int | None:
    if psutil is None:
        return None
    return psutil.Process(os.getpid()).memory_info().rss


class MemoryMonitor:
    """Peak Python-heap and process-RSS memory over one measured request.

    ``tracemalloc`` sees only allocations made through Python's allocator, so
    pandas/NumPy buffers and GDAL/rasterio native memory are largely invisible
    to it. Process RSS includes them, and is therefore the primary memory
    metric. RSS is sampled on a background thread, so a peak shorter than the
    sampling interval can be missed.

    RSS is a property of the whole process: memory retained by the allocator
    after earlier runs is included in the absolute peak. Both the absolute
    peak and the increase over the RSS measured just before the request are
    recorded; see evaluation/README.md for how they are used.
    """

    def __init__(self, interval_seconds: float = 0.05, rss_probe=_process_rss_bytes):
        self.interval_seconds = interval_seconds
        self._probe = rss_probe
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._rss_before: int | None = None
        self._rss_peak: int | None = None
        self.result: dict = {}

    def _sample(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self._observe()

    def _observe(self) -> None:
        value = self._probe()
        if value is not None and (self._rss_peak is None or value > self._rss_peak):
            self._rss_peak = value

    def __enter__(self) -> "MemoryMonitor":
        gc.collect()
        self._rss_before = self._probe()
        self._rss_peak = self._rss_before
        tracemalloc.start()
        if self._rss_before is not None:
            self._thread = threading.Thread(target=self._sample, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self._observe()  # catch a peak reached at the very end
        _current, traced_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rss_available = self._rss_before is not None
        self.result = {
            "peak_rss_mb": self._rss_peak / MB if rss_available else None,
            "rss_before_mb": self._rss_before / MB if rss_available else None,
            "peak_rss_increase_mb": (
                (self._rss_peak - self._rss_before) / MB if rss_available else None
            ),
            "peak_traced_memory_mb": traced_peak / MB,
            "rss_backend": "psutil" if rss_available else None,
            "rss_sampling_interval_seconds": (
                self.interval_seconds if rss_available else None
            ),
        }


# ---------------------------------------------------------------------------
# Reproducibility metadata
# ---------------------------------------------------------------------------

def _git(*args: str) -> str | None:
    """Raw git stdout, or None when git or the repository is unavailable."""
    try:
        completed = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
            timeout=10, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout


def git_metadata() -> dict:
    """Commit and working-tree state; a dirty tree means results may not match the SHA."""
    status = _git("status", "--porcelain", "--untracked-files=no")
    sha = _git("rev-parse", "HEAD")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    # Porcelain lines are "XY <path>"; the leading status column may be a
    # space, so the output must not be stripped before slicing.
    changed = None if status is None else [
        line[3:] for line in status.splitlines() if line.strip()
    ]
    return {
        "commit_sha": sha.strip() if sha else None,
        "branch": branch.strip() if branch else None,
        "tracked_changes_uncommitted": None if changed is None else bool(changed),
        "uncommitted_tracked_paths": changed or None,
    }


def _total_ram_bytes() -> int | None:
    if psutil is not None:
        return int(psutil.virtual_memory().total)
    if sys.platform == "win32":
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullTotalPhys)
        return None
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, ValueError, OSError):
        return None


def hardware_metadata() -> dict:
    physical = psutil.cpu_count(logical=False) if psutil is not None else None
    ram = _total_ram_bytes()
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_model": platform.processor() or None,
        "cpu_logical_cores": os.cpu_count(),
        "cpu_physical_cores": physical,
        "total_ram_gb": round(ram / 1024 ** 3, 2) if ram else None,
    }


def software_metadata() -> dict:
    try:
        farmwise_version = importlib.metadata.version("farmwise-api")
    except importlib.metadata.PackageNotFoundError:
        farmwise_version = None
    lock_digest = (
        hashlib.sha256(LOCKFILE.read_bytes()).hexdigest() if LOCKFILE.exists() else None
    )
    installed = sorted(
        {
            (dist.metadata["Name"] or "").lower(): dist.version
            for dist in importlib.metadata.distributions()
            if dist.metadata["Name"]
        }.items()
    )
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "in_virtualenv": sys.prefix != sys.base_prefix,
        "farmwise_api_version": farmwise_version,
        "lockfile": LOCKFILE.name,
        "lockfile_sha256": lock_digest,
        "psutil_available": psutil is not None,
        "installed_distributions": dict(installed),
    }


def provenance(config: dict, *, started_at: datetime | None = None) -> dict:
    """Everything needed to trace a collection back to its code and environment.

    No hostnames, user names, paths or environment variables are recorded.
    """
    started_at = started_at or datetime.now(timezone.utc)
    return {
        "collection_started_utc": started_at.isoformat(),
        "git": git_metadata(),
        "hardware": hardware_metadata(),
        "software": software_metadata(),
        "evaluation_config": config,
    }

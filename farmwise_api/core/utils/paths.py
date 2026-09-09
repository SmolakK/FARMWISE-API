"""
Central path resolution for FARMWISE-API.

This module resolves every bundled resource relative to the package instead,
so both entry points behave identically:

    * server mode  -> ``farmwise_api.server.main`` / uvicorn, any CWD
    * library mode -> ``import farmwise_api``, any CWD

It also separates *read-only bundled data* (shipped with the package) from
*writable scratch space* (must never live inside the package, because an
installed package directory may be read-only).

Environment overrides
---------------------
FARMWISE_DATA_DIR
    Override the location of bundled adapter data. Useful for containerised
    deployments that mount large rasters from a volume rather than baking them
    into the image.
FARMWISE_CACHE_DIR
    Override the scratch/cache location. Defaults to a per-user cache dir.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path

from farmwise_api.core.utils.data_manifest import REMOTE_DATA

logger = logging.getLogger("farmwise.data_fetch")

__all__ = [
    "PROJECT_ROOT",
    "PACKAGE_ROOT",
    "DATA_ROOT",
    "CACHE_ROOT",
    "adapter_data",
    "adapter_cache",
    "scratch_file",
    "scratch_dir",
    "fetch_remote",
    "prefetch_all",
]


PACKAGE_ROOT: Path = Path(__file__).resolve().parents[2]


def _resolve_project_root() -> Path:
    """Return the checkout root, or the process working directory when installed."""
    checkout_root = PACKAGE_ROOT.parent
    if (checkout_root / "pyproject.toml").is_file():
        return checkout_root
    return Path.cwd().resolve()


PROJECT_ROOT: Path = _resolve_project_root()

DATA_ROOT: Path = Path(
    os.environ.get(
        "FARMWISE_DATA_DIR",
        PACKAGE_ROOT / "adapters" / "API_readers",
    )
).resolve()


def _default_cache_root() -> Path:
    override = os.environ.get("FARMWISE_CACHE_DIR")
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "farmwise"
    return Path.home() / ".cache" / "farmwise"


CACHE_ROOT: Path = _default_cache_root()


def adapter_data(*parts: str) -> Path:
    """
    Resolve a resource needed by an adapter: bundled data first, remote
    (Zenodo-hosted, fetched into CACHE_ROOT on first use) second.

    Raises FileNotFoundError with an actionable message if the resource is
    neither bundled nor in the manifest, rather than letting pandas/rasterio
    fail with an opaque error deep inside a worker task.
    """
    path = DATA_ROOT.joinpath(*parts)
    if path.exists():
        return path

    rel = "/".join(parts)
    if rel in REMOTE_DATA:
        return fetch_remote(rel)

    raise FileNotFoundError(
        f"FARMWISE resource not found: {path}\n"
        f"Not bundled under DATA_ROOT={DATA_ROOT}, and not listed in "
        f"utils/data_manifest.py. If this should be fetched from Zenodo, "
        f"add it to REMOTE_DATA; if FARMWISE_DATA_DIR points at a custom "
        f"volume, check it's populated."
    )


_fetch_locks: dict[str, threading.Lock] = {}
_fetch_locks_guard = threading.Lock()


def _lock_for(rel: str) -> threading.Lock:
    with _fetch_locks_guard:
        return _fetch_locks.setdefault(rel, threading.Lock())


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path) -> None:
    import requests  # local import: only needed on cache-miss, not at import time

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + f".part-{uuid.uuid4().hex[:8]}")
    try:
        for attempt in range(3):
            offset = tmp.stat().st_size if tmp.exists() else 0
            request_options = {"stream": True, "timeout": 60}
            if offset:
                request_options["headers"] = {"Range": f"bytes={offset}-"}
            try:
                with requests.get(
                    url,
                    **request_options,
                ) as response:
                    response.raise_for_status()
                    append = offset > 0 and response.status_code == 206
                    with open(tmp, "ab" if append else "wb") as output:
                        for chunk in response.iter_content(chunk_size=1 << 20):
                            if chunk:
                                output.write(chunk)
                os.replace(tmp, dest)  # atomic on same filesystem
                return
            except requests.HTTPError:
                raise
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
    finally:
        tmp.unlink(missing_ok=True)


def fetch_remote(rel: str) -> Path:
    """
    Ensure the manifest entry ``rel`` is present in CACHE_ROOT, downloading
    and verifying it if necessary, and return its local path.

    Safe to call concurrently for the same ``rel``: later callers block on
    the first download rather than re-downloading or reading a partial file.
    Safe to call repeatedly across runs: a cache hit is a plain existence
    check, no network access.
    """
    entry = REMOTE_DATA[rel]
    target = CACHE_ROOT.joinpath(*rel.split("/"))

    with _lock_for(rel):
        if target.exists():
            return target

        size = entry.get("size_mb", "?")
        logger.info(
            "Fetching %s (%s MB) -- first use only, cached under %s",
            rel, size, CACHE_ROOT,
        )

        if entry["kind"] == "file":
            _download(entry["url"], target)
            if entry.get("sha256") and entry["sha256"] != "REPLACE_ME":
                digest = _sha256(target)
                if digest.casefold() != entry["sha256"].casefold():
                    target.unlink(missing_ok=True)
                    raise ValueError(
                        f"Checksum mismatch for {rel}: expected "
                        f"{entry['sha256']}, got {digest}. Deleted the "
                        f"corrupt download; try again."
                    )

        elif entry["kind"] == "archive":
            extract_to = CACHE_ROOT.joinpath(*entry["extract_to"].split("/"))
            zip_path = CACHE_ROOT / f".archive_{uuid.uuid4().hex}.zip"
            try:
                _download(entry["url"], zip_path)
                if entry.get("sha256") and entry["sha256"] != "REPLACE_ME":
                    digest = _sha256(zip_path)
                    if digest.casefold() != entry["sha256"].casefold():
                        raise ValueError(
                            f"Checksum mismatch for archive {rel}: expected "
                            f"{entry['sha256']}, got {digest}."
                        )
                extract_to.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(zip_path) as zf:
                    zf.extractall(extract_to)
            finally:
                zip_path.unlink(missing_ok=True)

        else:
            raise ValueError(f"Unknown manifest entry kind for {rel}: {entry['kind']!r}")

        logger.info("Fetched %s", rel)
        return target


def prefetch_all(sources: list[str] | None = None) -> None:
    """
    Eagerly fetch manifest entries. For deployment: run this in your Docker
    build or startup script so a server's first *request* never triggers a
    surprise multi-minute download.

    ``sources``: optional list of substrings to filter which entries to
    fetch (e.g. ["eea", "EuroCropV2"]); None fetches everything.
    """
    for rel in REMOTE_DATA:
        if sources and not any(s in rel for s in sources):
            continue
        fetch_remote(rel)


def adapter_cache(adapter: str) -> Path:
    """Writable, persistent per-adapter cache directory (created on demand)."""
    path = CACHE_ROOT / adapter
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        logger.warning("Could not restrict cache permissions for %s", path)
    return path


def scratch_file(adapter: str, suffix: str = ".tif", stem: str = "out") -> Path:
    """
    Unique writable path for a single call's intermediate output.

    The uuid4 component is what prevents concurrent requests for the same
    variable from racing on a shared filename -- the previous behaviour of
    ``out_{soil_property}.tif`` was corrupt-prone under asyncio.gather dispatch.
    """
    d = Path(tempfile.gettempdir()) / "farmwise" / adapter
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{stem}_{uuid.uuid4().hex}{suffix}"


@contextmanager
def scratch_dir(adapter: str):
    """
    Temporary directory for one call, removed on exit.

    Preferred over ``scratch_file`` when an adapter writes several files
    (e.g. the CDS readers, which currently write into the package directory).
    """
    with tempfile.TemporaryDirectory(prefix=f"farmwise_{adapter}_") as tmp:
        yield Path(tmp)

"""Keep GDAL pointed at a usable PROJ database.

GDAL reads the ``PROJ_LIB``/``PROJ_DATA`` environment variables to find
``proj.db``. On machines that also carry a conda, OSGeo4W or PostGIS install,
``PROJ_LIB`` often points at that installation's older database. GDAL then
refuses it::

    proj_create_from_database: ...\\proj.db contains
    DATABASE.LAYOUT.VERSION.MINOR = 2 whereas a number >= 6 is expected.

and every CRS lookup fails - ``CRS.from_epsg(4326)`` raises, so reprojection
and every raster adapter stop working. The message is emitted by GDAL's error
handler on each attempt, so a single request can produce hundreds of lines.

pyproj is unaffected (it resolves its own data directory), and
``rasterio.Env()`` does not help: the environment variable still wins.

This module checks the configured database before GDAL touches it - by reading
the layout version straight out of the SQLite file, which costs nothing and
emits no GDAL errors - and, when it is too old, sets ``PROJ_DATA`` to the copy
shipped with rasterio. ``PROJ_DATA`` takes precedence over the legacy
``PROJ_LIB`` in PROJ 9+, so the host variable is left untouched and other
software on the machine keeps working.

Set ``FARMWISE_FIX_PROJ_DATA=0`` to disable this entirely. This is also documented in the README.
This was implemented for the dev purposes but left working as workaround.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

#: GDAL/PROJ 9 requires at least this database layout minor version.
MINIMUM_LAYOUT_MINOR = 6

DISABLE_ENV = "FARMWISE_FIX_PROJ_DATA"
_FALSEY = {"0", "false", "no", "off"}


def _layout_minor(proj_db: Path) -> int | None:
    """Return the database layout minor version, or None if unreadable."""
    try:
        connection = sqlite3.connect(f"file:{proj_db}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = ?",
            ("DATABASE.LAYOUT.VERSION.MINOR",),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    try:
        return int(row[0]) if row else None
    except (TypeError, ValueError):
        return None


def _is_usable(directory: str | os.PathLike[str]) -> bool:
    """Whether `directory` holds a proj.db GDAL will accept."""
    proj_db = Path(directory) / "proj.db"
    if not proj_db.is_file():
        return False
    minor = _layout_minor(proj_db)
    # An unreadable version is left alone: better to defer to the operator's
    # configuration than to override something merely unusual.
    return minor is None or minor >= MINIMUM_LAYOUT_MINOR


def _bundled_proj_data() -> Path | None:
    """Locate the PROJ data shipped inside the installed wheels.

    Uses ``find_spec`` rather than importing: importing rasterio initialises
    GDAL, which resolves the PROJ search path once and caches it. Doing that
    here would load the stale database before this module could redirect it,
    leaving the fix a no-op.
    """
    for module_name, *parts in (
        ("rasterio", "proj_data"),
        ("pyproj", "proj_dir", "share", "proj"),
    ):
        try:
            spec = importlib.util.find_spec(module_name)
        except (ImportError, ValueError):
            continue
        if spec is None or not spec.origin:
            continue
        candidate = Path(spec.origin).parent.joinpath(*parts)
        if (candidate / "proj.db").is_file():
            return candidate
    return None


def ensure_usable_proj_data() -> Path | None:
    """Redirect PROJ to bundled data when the host's database is too old.

    Returns the directory that was applied, or None when nothing was changed
    - which is the normal case on a correctly configured machine.
    """
    if os.environ.get(DISABLE_ENV, "").strip().lower() in _FALSEY:
        return None

    # An explicit PROJ_DATA is the operator's own decision; respect it.
    if os.environ.get("PROJ_DATA"):
        return None

    configured = os.environ.get("PROJ_LIB")
    if not configured or _is_usable(configured):
        return None

    bundled = _bundled_proj_data()
    if bundled is None:
        logger.warning(
            "PROJ_LIB points at %s, whose proj.db is too old for GDAL, and no "
            "bundled PROJ data was found. Coordinate lookups will fail; unset "
            "PROJ_LIB or point it at a current PROJ installation.",
            configured,
        )
        return None

    os.environ["PROJ_DATA"] = str(bundled)
    logger.warning(
        "PROJ_LIB points at %s, whose proj.db layout is older than GDAL "
        "accepts. Using the bundled PROJ data at %s for this process instead; "
        "PROJ_LIB itself is left unchanged. Unset PROJ_LIB to silence this, or "
        "set %s=0 to keep the host configuration.",
        configured, bundled, DISABLE_ENV,
    )
    return bundled


__all__ = ["ensure_usable_proj_data", "MINIMUM_LAYOUT_MINOR", "DISABLE_ENV"]

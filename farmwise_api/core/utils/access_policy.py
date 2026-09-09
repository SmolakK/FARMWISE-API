"""Runtime acknowledgements for sources with restricted usage terms."""

from __future__ import annotations

import os


IMGW_PRIVATE_USE_ENV = "FARMWISE_ENABLE_PRIVATE_IMGW"
_TRUE_VALUES = {"1", "true", "yes", "on"}


def private_noncommercial_imgw_enabled() -> bool:
    """Return whether local private, non-commercial IMGW use was acknowledged."""
    return os.getenv(IMGW_PRIVATE_USE_ENV, "").strip().lower() in _TRUE_VALUES


def require_private_noncommercial_imgw() -> None:
    """Require an explicit acknowledgement before accessing IMGW-PIB data."""
    if not private_noncommercial_imgw_enabled():
        raise PermissionError(
            "IMGW-PIB access is disabled by default. It may be enabled only "
            "for private, non-commercial local use by setting "
            f"{IMGW_PRIVATE_USE_ENV}=1. Public/server use remains disabled."
        )

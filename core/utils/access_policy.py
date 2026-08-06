"""Runtime acknowledgements for sources with restricted usage terms."""

from __future__ import annotations

import os


IMGW_PRIVATE_USE_ENV = "FARMWISE_ENABLE_PRIVATE_IMGW"
_TRUE_VALUES = {"1", "true", "yes", "on"}


def require_private_noncommercial_imgw() -> None:
    """Require an explicit acknowledgement before accessing IMGW-PIB data."""
    acknowledged = os.getenv(IMGW_PRIVATE_USE_ENV, "").strip().lower()
    if acknowledged not in _TRUE_VALUES:
        raise PermissionError(
            "IMGW-PIB access is disabled by default. It may be enabled only "
            "for private, non-commercial local use by setting "
            f"{IMGW_PRIVATE_USE_ENV}=1. Public/server use remains disabled."
        )

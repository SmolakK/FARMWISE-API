"""Runtime acknowledgements for sources with usage-specific terms."""

from __future__ import annotations

import os


IMGW_PRIVATE_USE_ENV = "FARMWISE_ENABLE_PRIVATE_IMGW"
IMGW_RESEARCH_USE_ENV = "FARMWISE_ENABLE_RESEARCH_IMGW"
_TRUE_VALUES = {"1", "true", "yes", "on"}


def private_noncommercial_imgw_enabled() -> bool:
    """Return whether permitted local IMGW use was acknowledged.

    ``FARMWISE_ENABLE_PRIVATE_IMGW`` is retained as a backwards-compatible
    alias.  Academic evaluation should use ``FARMWISE_ENABLE_RESEARCH_IMGW``.
    """
    return any(
        os.getenv(name, "").strip().lower() in _TRUE_VALUES
        for name in (IMGW_RESEARCH_USE_ENV, IMGW_PRIVATE_USE_ENV)
    )


def require_private_noncommercial_imgw() -> None:
    """Require an explicit acknowledgement before accessing IMGW-PIB data."""
    if not private_noncommercial_imgw_enabled():
        raise PermissionError(
            "IMGW-PIB access is disabled by default. It may be enabled only "
            "for permitted local private/non-commercial or academic research "
            "use by setting "
            f"{IMGW_RESEARCH_USE_ENV}=1. Public/server use remains disabled."
        )

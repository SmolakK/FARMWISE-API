"""Runtime acknowledgements for sources with usage-specific terms."""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
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


@contextmanager
def acknowledged_private_noncommercial_imgw() -> Iterator[None]:
    """Acknowledge permitted local IMGW use for the duration of the block.

    The acknowledgement is process-global while active, because adapters read
    it from the environment. The previous value is restored on exit, so a
    caller cannot leave the gate open for unrelated code running later in the
    same process.
    """
    previous = os.environ.get(IMGW_RESEARCH_USE_ENV)
    os.environ[IMGW_RESEARCH_USE_ENV] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(IMGW_RESEARCH_USE_ENV, None)
        else:
            os.environ[IMGW_RESEARCH_USE_ENV] = previous


def require_private_noncommercial_imgw() -> None:
    """Require an explicit acknowledgement before accessing IMGW-PIB data."""
    if not private_noncommercial_imgw_enabled():
        raise PermissionError(
            "IMGW-PIB access is disabled by default. It may be enabled only "
            "for permitted local private/non-commercial or academic research "
            "use by setting "
            f"{IMGW_RESEARCH_USE_ENV}=1. Public/server use remains disabled."
        )

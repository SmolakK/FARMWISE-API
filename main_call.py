"""Public library entry point for local FARMWISE usage.

The implementation lives in :mod:`core.main_call`; this module preserves the
established ``from main_call import read_data`` interface.
"""

from core.main_call import read_data

__all__ = ["read_data"]

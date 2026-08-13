"""Public library entry point for local FARMWISE usage.

The implementation lives in :mod:`farmwise_api.core.main_call`; this module preserves the
established ``from main_call import read_data`` interface.
"""

from farmwise_api.core.main_call import read_data

__all__ = ["read_data"]

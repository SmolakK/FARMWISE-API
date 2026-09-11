"""Public Python API for FARMWISE."""

from farmwise_api.core.utils.proj_env import ensure_usable_proj_data

# Runs before anything imports GDAL, which resolves PROJ_LIB on first use.
# A no-op unless the host points PROJ at a database GDAL cannot read.
ensure_usable_proj_data()

from farmwise_api.core.main_call import read_data  # noqa: E402

__all__ = ["read_data"]
__version__ = "0.1.0"

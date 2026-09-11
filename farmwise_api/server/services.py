from farmwise_api.adapters.mappings.data_source_mapping import PUBLIC_SERVER_DISABLED_SOURCES
from farmwise_api.core.main_call import read_data as read_core_data
import pandas as pd


async def read_data(**kwargs) -> dict | pd.DataFrame:
    """Run the core reader with public-server licensing restrictions."""
    kwargs["disabled_sources"] = PUBLIC_SERVER_DISABLED_SOURCES
    return await read_core_data(**kwargs)


async def process_data(bounding_box, level, time_from, time_to, factors) -> dict | pd.DataFrame:
    """Call the core aggregation service with explicit argument names."""
    return await read_data(
        bounding_box=bounding_box,
        level=level,
        time_from=time_from,
        time_to=time_to,
        factors=factors,
    )

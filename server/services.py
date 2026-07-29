from core.main_call import read_data


async def process_data(bounding_box, level, time_from, time_to, factors):
    """Call the core aggregation service with explicit argument names."""
    return await read_data(
        bounding_box=bounding_box,
        level=level,
        time_from=time_from,
        time_to=time_to,
        factors=factors,
    )

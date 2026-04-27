import pandas as pd
from API_readers.IFSGRID.utils.extraction import stack_values
from API_readers.IFSGRID.utils.preparation import (
    check_overlap, 
    build_bbox, 
    aggregate_spatial, 
    expand_time_dimension
)
from API_readers.IFSGRID.mappings.IFSGRID_mappings import GLOBAL_MAPPING
async def read_data(
        spatial_range:tuple, time_range:tuple, data_range:list, level:int
    ):
    """
    Read, process and aggregate IFSGRID data for a given
    spatial and temporal range.

    Parameters
    ----------
    spatial_range : tuple of float (north, south, east, west)
        Geographic extent in EPSG:4326 coordinate system.
    time_range : tuple of str (start_date, end_date)
        Date range in format "YYYY-MM-DD".
    data_range : list of str
        List of logical factor names to extract.
    level : int
        S2 cell resolution level used for spatial aggregation.

    Returns
    -------
    pd.DataFrame
        Pivoted DataFrame indexed by daily timestamps with
        S2CELL identifiers as columns.

    None
        Returned when:
        - Requested time range does not overlap with available data.
        - No spatial data is found within the bounding box.
    """
    start_date, end_date = check_overlap(time_range)

    if start_date is None:
        return None
    
    bbox_geom = build_bbox(spatial_range)
    factors_data = stack_values(data_range, bbox_geom)

    if factors_data.empty:
        return None
    
    aggregated_df = aggregate_spatial(factors_data, spatial_range, level)
    final_df = expand_time_dimension(aggregated_df, start_date, end_date)

    final_df.columns = pd.MultiIndex.from_tuples(
    [
        (GLOBAL_MAPPING.get(var, var), cell)
        for var, cell in final_df.columns
    ]
    )
    return final_df
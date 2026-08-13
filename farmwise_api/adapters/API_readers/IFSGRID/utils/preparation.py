from datetime import datetime, date
from shapely.geometry import box, Polygon
import pandas as pd
from farmwise_api.adapters.API_readers.IFSGRID.mappings.IFSGRID_mappings import DATA_ALIASES
from farmwise_api.adapters.mappings.data_source_mapping import WITHIN_SOURCE_AGGREGATION_METHODS
from farmwise_api.core.within_source_aggregation import aggregate_to_s2
from farmwise_api.core.utils.coordinates_to_cells import prepare_coordinates

def check_overlap(period:tuple) -> tuple:
    """
    Validate and adjust a requested time period against
    dataset availability constraints.

    Parameters
    ----------
    period : tuple of str (start_date, end_date)
        Date range in format "YYYY-MM-DD".

    Returns
    -------
    tuple of date
        Adjusted (start_date, end_date) if overlap exists
        with available data period.

    tuple of (None, None)
        Returned when the requested period does not overlap
        with available data.
    """
    start = datetime.strptime(period[0], "%Y-%m-%d").date()
    end = datetime.strptime(period[1], "%Y-%m-%d").date()

    boundary_start = date(2020, 1, 1)
    today = date.today()

    if end >= boundary_start:
        new_start = max(start, boundary_start)
        return new_start, end
    else:
        return None, None


def build_bbox(spatial_range:tuple) -> Polygon:
    """
    Create a bounding box geometry from spatial range coordinates.

    Parameters
    ----------
    spatial_range : tuple of float (north, south, east, west)
        Geographic extent in EPSG:4326 coordinate system.

    Returns
    -------
    shapely.geometry.Polygon
        Bounding box geometry.
    """
    north, south, east, west = spatial_range
    return box(west, south, east, north)


def aggregate_spatial(
        df:pd.DataFrame, spatial_range:tuple, level:int,
        logical_data_types=(), methods=None,
    ) -> pd.DataFrame:
    """
    Aggregate spatial data into S2 cells at a given level.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing latitude, longitude and factor values.
    spatial_range : tuple of float
        Geographic extent used for coordinate preparation.
    level : int
        S2 cell resolution level.

    Returns
    -------
    pd.DataFrame
        DataFrame aggregated by S2CELL with mean values
        computed per cell.
    """
    df = prepare_coordinates(df, spatial_range, level)
    return aggregate_to_s2(
        df.drop(columns=["lat", "lon"], errors="ignore"),
        group_by=("S2CELL",),
        logical_data_types=logical_data_types,
        methods=methods or WITHIN_SOURCE_AGGREGATION_METHODS,
        column_data_types=DATA_ALIASES,
    ).reset_index()


def expand_time_dimension(
        df:pd.DataFrame, start_date:datetime.date, end_date:datetime.date
    ) -> pd.DataFrame:
    """
    Expand spatially aggregated data across a daily time range.

    Parameters
    ----------
    df : pd.DataFrame
        Spatially aggregated DataFrame indexed by S2CELL.
    start_date : datetime.date
        Start date of the time range.
    end_date : datetime.date
        End date of the time range.

    Returns
    -------
    pd.DataFrame
        Pivoted DataFrame with daily timestamps as index
        and S2CELL values as columns.
    """
    dates = pd.date_range(start=start_date, end=end_date, freq="D")
    expanded = pd.concat([df.assign(Timestamp=d) for d in dates])

    return expanded.pivot(index="Timestamp", columns="S2CELL")

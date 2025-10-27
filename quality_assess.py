import pandas as pd
from datetime import datetime
from utils.coordinates_to_cells import get_s2_cells
import numpy as np

def bbox_intersects(b1, b2):
    """
    Check intersection between two bounding boxes and return the intersecting bbox.

    Parameters
    ----------
    b1, b2 : tuple
        Bounding boxes defined as (N, S, E, W)

    Returns
    -------
    (bool, tuple or None)
        (True, (N, S, E, W)) if intersection exists, otherwise (False, None)
    """

    N1, S1, E1, W1 = b1
    N2, S2, E2, W2 = b2

    # Compute overlap
    N = min(N1, N2)
    S = max(S1, S2)
    E = min(E1, E2)
    W = max(W1, W2)

    if S < N and W < E:
        return True, (N, S, E, W)
    else:
        return False, None


def assess_data_quality(df, metadata, ranges, req_ranges):
    report = {}
    # API ranges
    api_bbox = ranges[0]               # (N, S, E, W)
    api_time = ranges[1]               # ('YYYY-MM-DD','YYYY-MM-DD')
    api_factors = ranges[2]            # list of requested factors
    api_start = datetime.strptime(api_time[0], "%Y-%m-%d")
    api_end = datetime.strptime(api_time[1], "%Y-%m-%d")
    # Requested ranges
    req_bbox = req_ranges['bbox']
    req_level = req_ranges['level']
    req_start = datetime.strptime(req_ranges['time_from'],"%Y-%m-%d")
    req_end = datetime.strptime(req_ranges['time_to'],"%Y-%m-%d")
    req_factors = req_ranges['factors']

    bbox_intersect, intersected_bbox = bbox_intersects(api_bbox,req_bbox)

    if req_start > api_start:
        actual_start = req_start
    else:
        actual_start = api_start

    if req_end > api_end:
        actual_end = api_end
    else:
        actual_end = req_end

    # Extract S2 cells and days from df
    df_cells = set(df.columns.get_level_values(1).unique()) if not df.empty else set()
    df_days = set(df.index.astype(str).unique())

    expected_s2_cells = get_s2_cells(intersected_bbox,req_level)

    api_name = metadata.get("api_name")
    report['api_name'] = api_name
    returned_columns = metadata.get("columns", [])

    # SPATIAL OVERLAP
    overlapping_cells = set(expected_s2_cells).intersection(set(df_cells))
    s2_overlap = len(overlapping_cells)/len(expected_s2_cells)
    report['S2_level'] = req_level
    report['S2_completeness'] = s2_overlap

    # TEMPORAL OVERLAP
    df.index = pd.to_datetime(df.index)  # ensure datetime index
    df_daily = df.resample("D").mean()
    missing = df_daily.isna().sum().sum()
    total_expected = df_daily.shape[0] * df_daily.shape[1]
    report['total_missing_values'] = missing/total_expected
    report['factor_missing_values'] = df_daily.stack().isna().sum()/df_daily.stack().shape[0]
    report['missing_days'] = df_daily.isna().any(axis=1).sum()/df_daily.shape[0]

    returned_start = df.index.min()
    returned_end = df.index.max()
    report['data_delay'] = (actual_start - returned_start).total_seconds()/3600
    report['data_cutshort'] = (actual_end - returned_end).total_seconds() / 3600

    # FACTORS OVERLAP
    expected_factors = list(set(api_factors).intersection(set(req_factors)))
    report['factors_returned_completeness'] = len(returned_columns)/len(expected_factors)

    # WRONG VALUES
    error_values = []
    # WRONG PRECIP
    df_stack = df.stack()
    precip_cols = [x for x in df_stack.columns if 'precipitation' in x.lower()]
    if len(precip_cols) > 0:
        precip_df = (df_stack[precip_cols] < 0) | (df_stack[precip_cols] > 500)
        error_precip = precip_df.sum().sum()/precip_df.size
        error_values.append(error_precip)

    # WRONG TEMP
    temp_cols = [x for x in df_stack.columns if 'temperature' in x.lower()]
    if len(temp_cols) > 0:
        temp_df = (df_stack[temp_cols] < -80) | (df_stack[temp_cols] > 80)
        error_temp = temp_df.sum().sum()/temp_df.size
        error_values.append(error_temp)

    # SOIL WRONG
    if api_factors[0] == 'soil' or api_factors[0] == 'hydraulic conductivity' or api_factors[0] == 'depth to watertable' \
            or api_factors[0] == 'groundwater quality' or api_factors[0] == 'groundwater quantity' or \
            api_factors[0] == 'surface water quality' or api_factors[0] == 'potential evaporation' or api_factors[0] == 'surface water quantity':
        error_soil = (df_stack<0).sum().sum()/df_stack.size
        error_values.append(error_soil)
    elif api_factors[0] == 'land cover':
        error_lc = ((df_stack<0) | (df_stack > 255)).sum().sum()/df_stack.size
        error_values.append(error_lc)
    report['error_values'] = np.mean(error_values)
    return report



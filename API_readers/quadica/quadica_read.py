import numpy as np
import pandas as pd
import os
from API_readers.quadica.utils.preparation import (
    multi_factor_values,
    data_agregation,
    pivoting_table
)
from API_readers.quadica.mappings.quadica_mappings import GLOBAL_MAPPING



async def read_data(
    spatial_range,
    time_range,
    data_range,
    level
):
    """
    Read and process QUADICA dataset for a given spatial and temporal range.

    The function performs a full ETL pipeline:
    1. Extract raw multi-factor values
    2. Aggregate data
    3. Pivot into structured time-series format
    4. Rename columns using global mapping

    Parameters
    ----------
    spatial_range : tuple
        Geographic bounding box (format depends on downstream extractor).
    time_range : tuple
        Time interval used for filtering data.
    data_range : list
        List of parameters/factors to extract.
    level : int
        Spatial aggregation level (resolution or grid level).

    Returns
    -------
    pd.DataFrame
        Pivoted DataFrame containing aggregated QUADICA data,
        with renamed columns according to GLOBAL_MAPPING.
    """
    DATA_PATH = os.path.join(
        os.getcwd(),
        "API_readers",
        "quadica",
        "data"
    )

    extracted_data = multi_factor_values(
        DATA_PATH,
        data_range,
        spatial_range,
        time_range,
        level
    )

    agregated_data = data_agregation(extracted_data)
    pivot_data = pivoting_table(agregated_data)

    final_data = pivot_data.rename(columns=GLOBAL_MAPPING, level=0)

    return final_data
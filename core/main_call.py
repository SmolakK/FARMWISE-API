from adapters.mappings.data_source_mapping import (
    API_PATH_RANGES,
    DATA_SOURCE_WEIGHTS,
    DATA_TYPE_HARMONIZATION_METHODS,
)
from core.harmonization import (
    DEFAULT_SOURCE_WEIGHT,
    harmonize_data,
    validate_harmonization_methods,
    validate_source_weights,
)
from core.quality_assess import assess_data_quality, persist_quality_report
from core.utils.overlap_checks import spatial_ranges_overlap, time_ranges_overlap
from core.utils.interpolate_data import interpolate
from core.utils.cells_to_coordinates import extract_bbox
from core.utils.country_bboxes import return_country_bboxes
from core.utils.merge_bboxes import merge_bounding_boxes
import importlib
import pandas as pd
import logging
import asyncio
from time import perf_counter
from uuid import uuid4

logger = logging.getLogger(__name__)
COUNTRY_BBOXES = return_country_bboxes()


def plan_source_dispatch(
    bounding_box,
    time_from,
    time_to,
    factors,
    source_ranges=None,
):
    """Evaluate the coverage pre-check for every configured source."""
    source_ranges = API_PATH_RANGES if source_ranges is None else source_ranges
    requested_factors = set(factors or [])
    plan = []

    for source, ranges in source_ranges.items():
        spatial_overlap = spatial_ranges_overlap(bounding_box, ranges[0])
        temporal_overlap = time_ranges_overlap(
            (time_from, time_to), ranges[1]
        )
        factor_overlap = sorted(requested_factors.intersection(ranges[2]))
        plan.append(
            {
                "source": source,
                "spatial_overlap": spatial_overlap,
                "temporal_overlap": temporal_overlap,
                "factor_overlap": factor_overlap,
                "dispatched": bool(
                    spatial_overlap and temporal_overlap and factor_overlap
                ),
            }
        )
    return plan


async def read_data(bounding_box=None, country=None, level=None, time_from=None, time_to=None,
                    factors=None, separate_api=False, timeout=600, interpolation=False,
                    produce_map=False, source_weights=None, harmonization_methods=None,
                    persist_quality_reports=True, quality_report_dir=None):
    """
    Main data reading call - combines different APIs which overlap with the requested area and time range.

    :param produce_map: If true, a map will be produced.
    :param interpolation: If true, interpolation is applied to the resulting data. Especially useful for maps and
    high data resolutions.
    :param timeout: Timeout for each API after which the process will skip this API.
    :param separate_api: If True APIs are stored in separate columns and not averaged
    :param source_weights: Optional mapping of full API module paths to relative
                           source weights. Values override DATA_SOURCE_WEIGHTS.
    :param harmonization_methods: Optional mapping of logical data types to
                                  harmonization methods. Values override
                                  DATA_TYPE_HARMONIZATION_METHODS.
    :param persist_quality_reports: Persist each per-source quality assessment
                                    as JSON when True.
    :param quality_report_dir: Optional report directory override. By default
                               reports use the FARMWISE cache directory.
    :param bounding_box: A tuple containing the geographical coordinates (N, S, E, W) of the area for which data is requested.
                         Format: (North, South, East, West) in decimal degrees.
    :param level: S2Cell level.
    :param time_from: The starting date from when data should be collected. Format: YYYY-MM-DD.
    :param time_to: The ending date to when data should be collected. Format: YYYY-MM-DD.
    :param factors: A list of factors specifying the type of data requested.
                    Examples of allowed factors: 'precipitation', 'temperature'

    :return: Requested data in DataFrame of pandas.

    :raises: Specific exceptions raised by individual API modules if data retrieval fails.

    Note: `API_PATH_RANGES` is a dictionary mapping API names to their spatial, temporal, and data range constraints.
    """
    effective_source_weights = dict(DATA_SOURCE_WEIGHTS)
    if source_weights:
        effective_source_weights.update(source_weights)
    effective_source_weights = validate_source_weights(effective_source_weights)

    effective_methods = dict(DATA_TYPE_HARMONIZATION_METHODS)
    if harmonization_methods:
        effective_methods.update(harmonization_methods)
    effective_methods = validate_harmonization_methods(effective_methods)

    data_storage = []  # (source path, DataFrame, matching logical data types)
    api_metadata = []
    api_reports = []
    dispatch_metrics = []
    request_id = uuid4().hex
    if country is not None:
        if isinstance(country, str):
            country = [country]  # Support single country input

        selected_bboxes = []
        for c in country:
            if c not in COUNTRY_BBOXES:
                raise ValueError(f"Country '{c}' not found in country bounding boxes.")
            selected_bboxes.append(COUNTRY_BBOXES[c])
        bounding_box = merge_bounding_boxes(selected_bboxes)
        logger.info(f"Using merged bounding box {bounding_box} for countries: {country}")

    elif bounding_box is None:
        raise ValueError("You must provide either a 'bounding_box' or a 'country' parameter.")

    precheck_started = perf_counter()
    dispatch_plan = plan_source_dispatch(
        bounding_box, time_from, time_to, factors
    )
    precheck_seconds = perf_counter() - precheck_started

    for decision in dispatch_plan:
        if not decision["dispatched"]:
            continue

        api_name = decision["source"]
        api_name_suffix = api_name.split(".")[-1]
        ranges = API_PATH_RANGES[api_name]
        data_overlap = decision["factor_overlap"]
        dispatch_started = perf_counter()
        dispatch_status = "failure"
        dispatch_error = None

        try:
            module = importlib.import_module(api_name)
            api_response_data = await asyncio.wait_for(
                module.read_data(
                    spatial_range=bounding_box,
                    time_range=(time_from, time_to),
                    data_range=factors,
                    level=level,
                ),
                timeout=timeout,
            )
            if not isinstance(api_response_data, pd.DataFrame):
                dispatch_status = "invalid_response"
                continue
            if api_response_data.empty:
                dispatch_status = "empty"
                continue

            api_columns = list(
                api_response_data.columns.get_level_values(0).unique()
            )
            api_dates = [
                str(api_response_data.index.min()),
                str(api_response_data.index.max()),
            ]
            api_cells = list(
                api_response_data.columns.get_level_values(1).unique()
            )
            meta = {
                "api_name": api_name_suffix,
                "source": api_name,
                "columns": api_columns,
                "dates_range": api_dates,
                "bounding_box (NSEW)": extract_bbox(api_cells),
                "status": "success",
                "error": None,
            }
            api_metadata.append(meta)

            request_ranges = {
                "bbox": bounding_box,
                "level": level,
                "time_from": time_from,
                "time_to": time_to,
                "factors": factors,
            }
            try:
                api_report = await asyncio.to_thread(
                    assess_data_quality,
                    api_response_data,
                    meta,
                    ranges,
                    request_ranges,
                )
                if persist_quality_reports:
                    report_path = await asyncio.to_thread(
                        persist_quality_report,
                        api_report,
                        output_dir=quality_report_dir,
                        request_id=request_id,
                        source=api_name,
                    )
                    api_report["report_path"] = str(report_path)
                api_reports.append(api_report)
            except Exception as quality_error:
                logger.warning(
                    "Quality assessment failed for %s: %s",
                    api_name,
                    quality_error,
                )
                api_reports.append(
                    {
                        "api_name": api_name_suffix,
                        "source": api_name,
                        "status": "error",
                        "error": str(quality_error),
                    }
                )

            if separate_api:
                api_response_data.columns = api_response_data.columns.set_levels(
                    [
                        api_response_data.columns.levels[0]
                        + f" ({api_name_suffix})",
                        api_response_data.columns.levels[1],
                    ]
                )
            data_storage.append(
                (api_name, api_response_data, tuple(data_overlap))
            )
            dispatch_status = "success"
            logger.info(f"Data retrieved from {api_name_suffix}")
        except asyncio.TimeoutError:
            dispatch_status = "timeout"
            dispatch_error = f"Timed out after {timeout} seconds"
            logger.error(f"Request to {api_name_suffix} timed out")
        except Exception as error:
            dispatch_error = str(error)
            logger.error(f"Failed to retrieve data from {api_name}: {error}")
        finally:
            dispatch_metrics.append(
                {
                    "source": api_name,
                    "status": dispatch_status,
                    "wall_seconds": perf_counter() - dispatch_started,
                    "error": dispatch_error,
                }
            )

    # Concatenate data if any DataFrames were retrieved
    if data_storage:
        try:
            if separate_api:
                combined_data = pd.concat(
                    [data for _source, data, _types in data_storage]
                )
                combined_data = combined_data.groupby(level=0).mean()
            else:
                combined_data = harmonize_data(
                    data_storage,
                    source_weights=effective_source_weights,
                    data_type_methods=effective_methods,
                )
            if interpolation:  # be aware this inserts values to NaNs
                combined_data = interpolate(combined_data, bounding_box, level)
            result = {"data": combined_data,  # The DataFrame containing the concatenated data
                    "metadata": {
                        "request_id": request_id,
                        "apis": api_metadata,
                        "quality_reports": api_reports,
                        "coverage_precheck": {
                            "candidate_sources": len(dispatch_plan),
                            "dispatched_sources": sum(
                                item["dispatched"] for item in dispatch_plan
                            ),
                            "requests_avoided": sum(
                                not item["dispatched"] for item in dispatch_plan
                            ),
                            "precheck_seconds": precheck_seconds,
                            "sources": dispatch_plan,
                        },
                        "dispatch": dispatch_metrics,
                        "harmonization": {
                            "enabled": not separate_api,
                            "source_weights": {
                                source: effective_source_weights.get(
                                    source, DEFAULT_SOURCE_WEIGHT
                                )
                                for source, _data, _types in data_storage
                            },
                            "methods": effective_methods,
                        },
                    }
                    }
            if produce_map:
                from core.utils.map_ploter import create_folium_map
                html_content = create_folium_map(combined_data,downsample_factor=1)
                result['map'] = html_content
            return result
        except Exception as e:
            logger.error(f'Error concatenating data: {e}')
            return pd.DataFrame()  # Return an empty DataFrame if concatenation fails
    else:
        logger.warning("No data retrieved from available APIs")
        return pd.DataFrame()


# import random
# from datetime import datetime, timedelta
#
# EUROPE_COUNTRIES = ["Ireland"]
#
# # FACTORS = [
# #     'temperature', 'precipitation', 'potential evaporation', 'soil',
# #     'surface water quantity', 'land cover', 'hydraulic conductivity',
# #     'depth to watertable', 'groundwater quality', 'groundwater quantity',
# #     'surface water quality'
# # ]
# FACTORS = [
#     'precipitation','temperature'
# ]
#
#
# def generate_test_cases(
#         n_countries=10, n_levels=3, n_dates=3,
#         date_start="2010-01-01", date_end="2020-01-20",
#         date_range_days=720
# ):
#     """
#     Generates parameterized test cases for read_data().
#
#     :param n_countries: How many random countries to pick from Europe
#     :param n_levels: How many random levels to generate
#     :param n_dates: How many random date ranges to generate
#     :param date_start: Earliest possible start date
#     :param date_end: Latest possible end date
#     :param date_range_days: Length of each test date window (days)
#     :return: List of test case dictionaries
#     """
#     test_cases = []
#
#     chosen_countries = random.sample(EUROPE_COUNTRIES, n_countries)
#     chosen_levels = random.sample(range(5, 12), n_levels)
#
#     # Convert to datetime
#     date_start = datetime.fromisoformat(date_start)
#     date_end = datetime.fromisoformat(date_end)
#
#     for country in chosen_countries:
#         for level in chosen_levels:
#             for _ in range(n_dates):
#                 # Pick random date window
#                 start = date_start + timedelta(
#                     days=random.randint(0, (date_end - date_start).days - date_range_days)
#                 )
#                 end = start + timedelta(days=date_range_days)
#
#                 test_cases.append({
#                     "country": country,
#                     "level": level,
#                     "time_from": start.strftime("%Y-%m-%d"),
#                     "time_to": end.strftime("%Y-%m-%d"),
#                     "factors": FACTORS
#                 })
#
#     return test_cases
#
#
# # Example usage:
# TEST_CASES = generate_test_cases()
#
# for case in TEST_CASES:
#     # Example using bounding box
#     asyncio.run(read_data(**case))

# Example using bounding box
# asyncio.run(read_data(bounding_box=(71, 34, 45, -25), level=10, time_from='2010-01-10', time_to='2010-02-10', factors=['temperature', 'precipitation','potential evaporation',
#                                                                                                                        'soil','surface water quantity','land cover','hydraulic conductivity',
#                                                                                                                        'depth to watertable','groundwater quality','groundwater quantity',
#                                                                                                                        'surface water quality',]))
#
# Example using country
# asyncio.run(read_data(country='Poland', level=10, time_from='2017-01-10', time_to='2017-01-12', factors=['temperature', 'precipitation'], produce_map=True))


__all__ = ["plan_source_dispatch", "read_data"]

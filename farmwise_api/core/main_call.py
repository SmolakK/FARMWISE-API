from farmwise_api.adapters.mappings.data_source_mapping import (
    API_PATH_RANGES,
    DATA_SOURCE_WEIGHTS,
    DATA_TYPE_HARMONIZATION_METHODS,
    DISABLED_API_SOURCES,
    PUBLIC_SERVER_DISABLED_SOURCES,
    WITHIN_SOURCE_AGGREGATION_METHODS,
)
from farmwise_api.core.harmonization import (
    DEFAULT_SOURCE_WEIGHT,
    harmonize_data,
    normalize_temporal_index,
    resolve_data_type,
    validate_harmonization_methods,
    validate_source_weights,
)
from farmwise_api.core.quality_assess import assess_data_quality, persist_quality_report
from farmwise_api.core.within_source_aggregation import (
    _aggregator as within_source_aggregator,
    validate_within_source_methods,
)
from farmwise_api.core.utils.overlap_checks import spatial_ranges_overlap, time_ranges_overlap
from farmwise_api.core.utils.interpolate_data import interpolate
from farmwise_api.core.utils.cells_to_coordinates import extract_bbox
from farmwise_api.core.utils.country_bboxes import return_country_bboxes
from farmwise_api.core.utils.merge_bboxes import merge_bounding_boxes
from farmwise_api.core.utils.access_policy import private_noncommercial_imgw_enabled
import importlib
import inspect
import pandas as pd
import logging
import asyncio
from time import perf_counter
from uuid import uuid4

logger = logging.getLogger(__name__)
COUNTRY_BBOXES = return_country_bboxes()


def _default_disabled_sources():
    """Return static and runtime-disabled sources for local Python calls."""
    disabled = dict(DISABLED_API_SOURCES)
    if not private_noncommercial_imgw_enabled():
        for source, reason in PUBLIC_SERVER_DISABLED_SOURCES.items():
            if ".imgw." in source or ".imgw_hydro." in source:
                disabled[source] = reason
    return disabled


async def _assess_source_quality(
    *,
    frame,
    metadata,
    ranges,
    request_ranges,
    persist,
    output_dir,
    request_id,
    source,
):
    """Run and optionally persist one source report without blocking the loop."""
    started = perf_counter()
    try:
        report = await asyncio.to_thread(
            assess_data_quality,
            frame,
            metadata,
            ranges,
            request_ranges,
        )
        if persist:
            report_path = await asyncio.to_thread(
                persist_quality_report,
                report,
                output_dir=output_dir,
                request_id=request_id,
                source=source,
            )
            report["report_path"] = str(report_path)
        report["assessment_wall_seconds"] = perf_counter() - started
        return report
    except Exception as error:
        logger.warning("Quality assessment failed for %s: %s", source, error)
        return {
            "api_name": metadata["api_name"],
            "source": source,
            "status": "error",
            "error": str(error),
            "assessment_wall_seconds": perf_counter() - started,
        }


def _reduce_duplicate_timestamps(frame, data_storage, within_source_methods):
    """Collapse repeated timestamps in the separate-API frame, per column.

    Sources are concatenated rather than harmonized here, so a timestamp can
    appear once per source and has to be reduced to one row. Averaging every
    column - which is what this used to do - is wrong for categorical
    variables: the mean of CORINE classes 211 and 312 is 261.5, which is not a
    class at all, and even a single source came back as 211.0 instead of 211.
    Each column is therefore reduced with the method configured for its
    logical data type, the same one the adapters use within a source.
    """
    available_types = sorted(
        {data_type for _source, _data, types in data_storage for data_type in types}
    )
    aggregations = {}
    for column in frame.columns:
        data_type = resolve_data_type(
            column, available_types, within_source_methods
        )
        method = within_source_methods.get(
            data_type, within_source_methods.get("default", "mean")
        )
        aggregations[column] = within_source_aggregator(method)

    reduced = frame.groupby(level=0).agg(aggregations)
    # groupby().agg() can widen integer columns when a group is empty; restore
    # the input dtype where the values are still integral, so class codes stay
    # class codes rather than becoming 211.0.
    for column in reduced.columns:
        original = frame[column].dtype
        if pd.api.types.is_integer_dtype(original) and not reduced[column].isna().any():
            reduced[column] = reduced[column].astype(original)
    return reduced


def _categorical_columns(frame, data_storage, harmonization_methods):
    """Return the columns whose values are class codes rather than measurements.

    A data type configured to combine by mode is categorical by definition:
    taking a mean or interpolating linearly between two of its values produces
    something that is not one of its classes.
    """
    available_types = sorted(
        {data_type for _source, _data, types in data_storage for data_type in types}
    )
    categorical = []
    for column in frame.columns:
        data_type = resolve_data_type(
            column, available_types, harmonization_methods
        )
        method = harmonization_methods.get(
            data_type, harmonization_methods.get("default", "weighted_mean")
        )
        if "mode" in method:
            categorical.append(column[0] if isinstance(column, tuple) else column)
    return tuple(dict.fromkeys(categorical))


def plan_source_dispatch(
    bounding_box,
    time_from,
    time_to,
    factors,
    source_ranges=None,
    disabled_sources=None,
):
    """Evaluate the coverage pre-check for every configured source."""
    using_default_sources = source_ranges is None
    source_ranges = API_PATH_RANGES if using_default_sources else source_ranges
    if disabled_sources is None:
        disabled_sources = _default_disabled_sources() if using_default_sources else {}
    requested_factors = set(factors or [])
    plan = []

    for source, ranges in source_ranges.items():
        disabled_reason = disabled_sources.get(source)
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
                "disabled_reason": disabled_reason,
                "dispatched": bool(
                    not disabled_reason
                    and spatial_overlap
                    and temporal_overlap
                    and factor_overlap
                ),
            }
        )
    return plan


async def read_data(bounding_box=None, country=None, level=None, time_from=None, time_to=None,
                    factors=None, separate_api=False, timeout=600, interpolation=False,
                    produce_map=False, source_weights=None, harmonization_methods=None,
                    within_source_aggregation_methods=None,
                    assess_quality=False, persist_quality_reports=False,
                    quality_report_dir=None, disabled_sources=None):
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
    :param within_source_aggregation_methods: Optional mapping of logical data
                                              types to methods used when one
                                              source has multiple records in
                                              the same S2 cell and time.
    :param persist_quality_reports: Persist each per-source quality assessment
                                    as JSON when True.
    :param assess_quality: Run per-source quality assessment when True. Set to
                           False for latency-sensitive calls.
    :param quality_report_dir: Optional report directory override. By default
                               reports use the FARMWISE cache directory.
    :param disabled_sources: Additional source paths to exclude from dispatch.
                             Server entry points use this for sources whose
                             terms permit local/private use only.
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

    effective_within_source_methods = dict(WITHIN_SOURCE_AGGREGATION_METHODS)
    if within_source_aggregation_methods:
        effective_within_source_methods.update(within_source_aggregation_methods)
    effective_within_source_methods = validate_within_source_methods(effective_within_source_methods)

    data_storage = []  # (source path, DataFrame, matching logical data types)
    api_metadata = []
    api_reports = []
    quality_tasks = []
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
    effective_disabled_sources = _default_disabled_sources()
    if disabled_sources:
        effective_disabled_sources.update(disabled_sources)
    dispatch_plan = plan_source_dispatch(
        bounding_box,
        time_from,
        time_to,
        factors,
        disabled_sources=effective_disabled_sources,
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
            adapter_kwargs = {
                "spatial_range": bounding_box,
                "time_range": (time_from, time_to),
                "data_range": factors,
                "level": level,
            }
            if "within_source_aggregation_methods" in inspect.signature(
                module.read_data
            ).parameters:
                adapter_kwargs["within_source_aggregation_methods"] = (
                    effective_within_source_methods
                )
            api_response_data = await asyncio.wait_for(
                module.read_data(**adapter_kwargs),
                timeout=timeout,
            )
            if not isinstance(api_response_data, pd.DataFrame):
                dispatch_status = "invalid_response"
                continue
            if api_response_data.empty:
                dispatch_status = "empty"
                continue
            api_response_data = normalize_temporal_index(api_response_data)

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
            if assess_quality:
                quality_tasks.append(
                    asyncio.create_task(
                        _assess_source_quality(
                            frame=api_response_data.copy(deep=False),
                            metadata=meta,
                            ranges=ranges,
                            request_ranges=request_ranges,
                            persist=persist_quality_reports,
                            output_dir=quality_report_dir,
                            request_id=request_id,
                            source=api_name,
                        )
                    )
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

    quality_wait_started = perf_counter()
    if quality_tasks:
        api_reports = list(await asyncio.gather(*quality_tasks))
    quality_wait_seconds = perf_counter() - quality_wait_started

    # Concatenate data if any DataFrames were retrieved
    if data_storage:
        try:
            if separate_api:
                combined_data = pd.concat(
                    [data for _source, data, _types in data_storage]
                )
                combined_data = _reduce_duplicate_timestamps(
                    combined_data,
                    data_storage,
                    effective_within_source_methods,
                )
            else:
                combined_data = harmonize_data(
                    data_storage,
                    source_weights=effective_source_weights,
                    data_type_methods=effective_methods,
                )
            if interpolation:  # be aware this inserts values to NaNs
                combined_data = interpolate(
                    combined_data,
                    bounding_box,
                    level,
                    categorical_columns=_categorical_columns(
                        combined_data, data_storage, effective_methods
                    ),
                )
            metadata = {
                        "request_id": request_id,
                        "apis": api_metadata,
                        "quality_assessment": {
                            "enabled": assess_quality,
                            "sources_assessed": len(api_reports),
                            "final_wait_seconds": quality_wait_seconds,
                        },
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
                        "within_source_aggregation": {
                            "methods": effective_within_source_methods,
                        },
                    }
            if assess_quality:
                metadata["quality_reports"] = api_reports

            result = {
                "data": combined_data,
                "metadata": metadata,
            }
            if produce_map:
                from farmwise_api.core.utils.map_ploter import create_folium_map
                html_content = create_folium_map(combined_data,downsample_factor=1)
                result['map'] = html_content
            return result
        except Exception as e:
            logger.error(f'Error concatenating data: {e}')
            return pd.DataFrame()  # Return an empty DataFrame if concatenation fails
    else:
        logger.warning("No data retrieved from available APIs")
        return pd.DataFrame()

# Example using bounding box
if __name__ == "__main__":
    # asyncio.run(read_data(
    #     bounding_box=(71, 34, 45, -25),
    #     level=10,
    #     time_from='2010-01-10',
    #     time_to='2010-02-10',
    #     factors=[
    #         'temperature', 'precipitation', 'potential evaporation',
    #         'soil', 'surface water quantity', 'land cover',
    #         'hydraulic conductivity', 'depth to watertable',
    #         'groundwater quality', 'groundwater quantity',
    #         'surface water quality',
    #     ],
    #     produce_map=True
    # ))
    asyncio.run(read_data(
        country=['Poland'],
        level=10,
        time_from='2010-01-10',
        time_to='2010-01-10',
        factors=[
            'temperature', 'precipitation','surface water quality','groundwater quantity','groundwater quality','soil',
            'land cover', 'surface water quantity'],
        assess_quality=True,
    ))


__all__ = ["plan_source_dispatch", "read_data"]

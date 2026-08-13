"""DuckDB-backed extraction helpers for QUADICA v1 files."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from farmwise_api.adapters.API_readers.quadica.mappings.quadica_mappings import DATA_ALIASES
from farmwise_api.adapters.API_readers.quadica.utils.definition import DATA_FRAME, DATA_RANGES
from farmwise_api.core.utils.coordinates_to_cells import prepare_coordinates


def files_with_params_extraction(factor):
    """Return source files and columns associated with one logical factor."""
    factor_parameters = {
        parameter for parameter, data_type in DATA_ALIASES.items()
        if data_type == factor
    }
    return {
        filename: [
            parameter
            for parameter in parameters
            if parameter in factor_parameters
        ]
        for filename, parameters in DATA_RANGES.items()
        if factor_parameters.intersection(parameters)
    }


def requested_data_files(factors):
    """Combine factor selections without reading the same file twice."""
    selected = {}
    for factor in dict.fromkeys(factors or []):
        for filename, parameters in files_with_params_extraction(factor).items():
            existing = selected.setdefault(filename, [])
            existing.extend(
                parameter for parameter in parameters if parameter not in existing
            )
    return selected


def combined_extractions(
    data_path,
    filename,
    values,
    spatial_range,
    time_range,
    level,
):
    """Dispatch to the extractor matching a configured QUADICA layout."""
    layout = DATA_FRAME[filename]
    if layout == "year_vertical":
        return year_vertical_extraction(
            data_path, values, spatial_range, time_range, level
        )
    if layout == "date_vertical":
        return date_vertical_extraction(
            data_path, values, spatial_range, time_range, level
        )
    if layout == "monthly_horizontal":
        return monthly_horizontal_extraction(
            data_path, spatial_range, time_range, level
        )
    raise ValueError(f"Unsupported QUADICA layout '{layout}' for {filename}.")


def monthly_horizontal_extraction(data_path, spatial_range, time_range, level):
    """Read monthly wide data while preserving one timestamp per month."""
    north, south, east, west = map(float, spatial_range)
    start, end = map(pd.Timestamp, time_range)
    path_sql = _sql_path(data_path)

    with duckdb.connect() as connection:
        columns = [
            row[0]
            for row in connection.execute(
                f"DESCRIBE SELECT * FROM read_csv_auto('{path_sql}')"
            ).fetchall()
        ]

        date_columns = []
        for column in columns:
            if column in {"OBJECTID", "lat", "lon"}:
                continue
            try:
                timestamp = pd.Timestamp(column)
            except (TypeError, ValueError):
                continue
            if start <= timestamp <= end:
                date_columns.append(column)

        if not date_columns:
            return _empty_fragment()

        selected_columns = ["OBJECTID", "lat", "lon", *date_columns]
        columns_sql = ", ".join(_quote_identifier(c) for c in selected_columns)
        result = connection.execute(
            f"""
            SELECT {columns_sql}
            FROM read_csv_auto('{path_sql}')
            WHERE lat BETWEEN {south} AND {north}
              AND lon BETWEEN {west} AND {east}
            """
        ).df()

    if result.empty:
        return _empty_fragment()

    value_column = Path(data_path).name.split("_", 1)[0]
    long_frame = result.melt(
        id_vars=["OBJECTID", "lat", "lon"],
        var_name="date",
        value_name=value_column,
    )
    long_frame["date"] = pd.to_datetime(long_frame["date"], errors="raise")
    return _assign_s2(long_frame, spatial_range, level)


def date_vertical_extraction(data_path, values, spatial_range, time_range, level):
    """Read native monthly records from the vertical WRTDS table."""
    north, south, east, west = map(float, spatial_range)
    start, end = (_validated_date(value) for value in time_range)
    path_sql = _sql_path(data_path)
    selected = ["OBJECTID", "date", "lat", "lon", *values]
    columns_sql = ", ".join(_quote_identifier(column) for column in selected)

    with duckdb.connect() as connection:
        result = connection.execute(
            f"""
            SELECT {columns_sql}
            FROM read_csv_auto('{path_sql}')
            WHERE lat BETWEEN {south} AND {north}
              AND lon BETWEEN {west} AND {east}
              AND CAST(date AS DATE) BETWEEN DATE '{start}' AND DATE '{end}'
            """
        ).df()

    if result.empty:
        return _empty_fragment()
    result["date"] = pd.to_datetime(result["date"], errors="raise")
    return _assign_s2(result, spatial_range, level)


def year_vertical_extraction(data_path, values, spatial_range, time_range, level):
    """Read annual records and represent each year by its January 1 timestamp."""
    north, south, east, west = map(float, spatial_range)
    start, end = map(pd.Timestamp, time_range)
    path_sql = _sql_path(data_path)
    selected = ["OBJECTID", "Year", "lat", "lon", *values]
    columns_sql = ", ".join(_quote_identifier(column) for column in selected)

    with duckdb.connect() as connection:
        result = connection.execute(
            f"""
            SELECT {columns_sql}
            FROM read_csv_auto('{path_sql}')
            WHERE lat BETWEEN {south} AND {north}
              AND lon BETWEEN {west} AND {east}
              AND Year BETWEEN {start.year} AND {end.year}
            """
        ).df()

    if result.empty:
        return _empty_fragment()
    result["date"] = pd.to_datetime(
        result.pop("Year").astype("Int64").astype(str) + "-01-01",
        errors="raise",
    )
    result = result.loc[result["date"].between(start, end)]
    if result.empty:
        return _empty_fragment()
    return _assign_s2(result, spatial_range, level)


def _assign_s2(frame, spatial_range, level):
    prepared = prepare_coordinates(frame, spatial_range, level)
    if prepared is None or prepared.empty:
        return _empty_fragment()
    return prepared.drop(columns=["lat", "lon"], errors="ignore").reset_index(
        drop=True
    )


def _empty_fragment():
    return pd.DataFrame(columns=["OBJECTID", "date", "S2CELL"])


def _quote_identifier(value):
    return '"' + str(value).replace('"', '""') + '"'


def _sql_path(path):
    return str(Path(path)).replace("'", "''")


def _validated_date(value):
    return pd.Timestamp(value).strftime("%Y-%m-%d")


__all__ = [
    "combined_extractions",
    "date_vertical_extraction",
    "files_with_params_extraction",
    "monthly_horizontal_extraction",
    "requested_data_files",
    "year_vertical_extraction",
]

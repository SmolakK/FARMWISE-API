"""Build the FARMWISE EuroCropsV2 representative-point data set.

The official EuroCropsV2 stack files contain parcel polygons in EPSG:3035.
This tool converts every polygon to a representative point, transforms the
coordinates to EPSG:4326 and writes the compact table consumed by FARMWISE.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import requests
import shapely
from pyproj import CRS, Transformer


SOURCE_DATASET_DOI = "10.2905/b9fb9e67-78a9-4327-9d59-39a928d812d3"
SOURCE_DATASET_VERSION = "2.01"
SOURCE_BASE_URL = (
    "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/DRLL/"
    "EuroCropsV2/gpqtv201"
)
DEFAULT_REGIONS = (
    "at",
    "be2",
    "be3",
    "cz",
    "de4",
    "dea",
    "dk",
    "ee",
    "es",
    "fi",
    "fr",
    "ie",
    "iti1",
    "nl",
    "pt",
    "si",
    "sk",
)
YEAR_COLUMN = re.compile(r"^(?:c|cf)(\d{4})$")
EXPECTED_SOURCE_CRS = CRS.from_epsg(3035)
OUTPUT_CRS = CRS.from_epsg(4326)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_url(region: str, base_url: str = SOURCE_BASE_URL) -> str:
    return f"{base_url.rstrip('/')}/{region}_stack.parquet"


def download_source(
    region: str,
    destination: Path,
    *,
    base_url: str = SOURCE_BASE_URL,
) -> dict:
    """Stream one official stack file to disk and return HTTP provenance."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return {
            "downloaded": False,
            "url": source_url(region, base_url),
        }

    temporary = destination.with_name(destination.name + ".part")
    url = source_url(region, base_url)
    try:
        with requests.get(url, stream=True, timeout=(30, 300)) as response:
            response.raise_for_status()
            with temporary.open("wb") as output:
                for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):
                    if chunk:
                        output.write(chunk)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    return {
        "downloaded": True,
        "url": url,
        "etag": response.headers.get("ETag"),
        "last_modified": response.headers.get("Last-Modified"),
        "content_length": response.headers.get("Content-Length"),
    }


def _geo_metadata(parquet: pq.ParquetFile) -> tuple[str, CRS]:
    metadata = parquet.schema_arrow.metadata or {}
    raw_geo = metadata.get(b"geo")
    if not raw_geo:
        raise ValueError("GeoParquet metadata is missing; source CRS is unknown.")

    geo = json.loads(raw_geo.decode("utf-8"))
    geometry_column = geo.get("primary_column")
    columns = geo.get("columns", {})
    if not geometry_column or geometry_column not in columns:
        raise ValueError("GeoParquet primary geometry column is not declared.")

    column_metadata = columns[geometry_column]
    encoding = str(column_metadata.get("encoding", "WKB")).upper()
    if encoding != "WKB":
        raise ValueError(
            f"Unsupported GeoParquet geometry encoding {encoding!r}; WKB required."
        )

    crs_metadata = column_metadata.get("crs")
    if not crs_metadata:
        raise ValueError("GeoParquet geometry CRS is not declared.")
    source_crs = CRS.from_user_input(crs_metadata)
    if not source_crs.equals(EXPECTED_SOURCE_CRS):
        raise ValueError(
            f"Unexpected source CRS {source_crs.to_string()}; EPSG:3035 required."
        )
    return geometry_column, source_crs


def _year_sort_key(column: str) -> tuple[int, int]:
    match = YEAR_COLUMN.fullmatch(column)
    if not match:
        return (9999, 9)
    return (int(match.group(1)), 0 if column.startswith("c") else 1)


def inspect_source(path: Path) -> dict:
    parquet = pq.ParquetFile(path)
    geometry_column, source_crs = _geo_metadata(parquet)
    schema_names = parquet.schema_arrow.names
    year_columns = sorted(
        (column for column in schema_names if YEAR_COLUMN.fullmatch(column)),
        key=_year_sort_key,
    )
    if not year_columns:
        raise ValueError(f"No cYYYY/cfYYYY columns found in {path.name}.")
    return {
        "geometry_column": geometry_column,
        "source_crs": source_crs,
        "year_columns": year_columns,
        "has_cropfield": "cropfield" in schema_names,
    }


def _open_text_output(path: Path):
    raw = path.open("wb")
    if path.name.endswith(".gz.part"):
        compressed = gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=6,
            fileobj=raw,
            mtime=0,
        )
        return io.TextIOWrapper(compressed, encoding="utf-8", newline="")
    return io.TextIOWrapper(raw, encoding="utf-8", newline="")


def _batch_to_frame(
    batch,
    *,
    region: str,
    geometry_column: str,
    source_crs: CRS,
    source_year_columns: Iterable[str],
    all_year_columns: list[str],
    has_cropfield: bool,
) -> tuple[pd.DataFrame, int]:
    geometry_values = np.asarray(
        batch.column(batch.schema.get_field_index(geometry_column)).to_pylist(),
        dtype=object,
    )
    geometries = shapely.from_wkb(geometry_values, on_invalid="ignore")
    points = shapely.point_on_surface(geometries)
    valid = ~(shapely.is_missing(points) | shapely.is_empty(points))

    x_source = shapely.get_x(points)
    y_source = shapely.get_y(points)
    transformer = Transformer.from_crs(source_crs, OUTPUT_CRS, always_xy=True)
    lon, lat = transformer.transform(
        np.asarray(x_source, dtype=float).tolist(),
        np.asarray(y_source, dtype=float).tolist(),
    )
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    valid &= np.isfinite(lon) & np.isfinite(lat)

    attributes = list(source_year_columns)
    if has_cropfield:
        attributes.insert(0, "cropfield")
    frame = batch.select(attributes).to_pandas()
    frame.insert(0, "source_region", region)
    if has_cropfield:
        frame = frame.rename(columns={"cropfield": "source_cropfield"})
    else:
        frame.insert(1, "source_cropfield", pd.NA)
    frame.insert(2, "lon", lon)
    frame.insert(3, "lat", lat)

    for column in all_year_columns:
        if column not in frame.columns:
            frame[column] = pd.NA

    output_columns = [
        "source_region",
        "source_cropfield",
        "lon",
        "lat",
        *all_year_columns,
    ]
    invalid_count = int((~valid).sum())
    return frame.loc[valid, output_columns], invalid_count


def build_points_dataset(
    source_paths: dict[str, Path],
    output_path: Path,
    provenance_path: Path,
    *,
    batch_size: int = 50_000,
    overwrite: bool = False,
    source_http_metadata: dict[str, dict] | None = None,
    source_base_url: str = SOURCE_BASE_URL,
) -> dict:
    """Build a deterministic CSV/CSV.GZ and its provenance manifest."""
    if not source_paths:
        raise ValueError("At least one EuroCropsV2 stack file is required.")
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output_path}")
    if provenance_path.exists() and not overwrite:
        raise FileExistsError(f"Provenance already exists: {provenance_path}")

    source_paths = dict(sorted(source_paths.items()))
    inspections = {
        region: inspect_source(path) for region, path in source_paths.items()
    }
    all_year_columns = sorted(
        {
            column
            for inspection in inspections.values()
            for column in inspection["year_columns"]
        },
        key=_year_sort_key,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    provenance_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output_path.with_name(output_path.name + ".part")
    temporary_output.unlink(missing_ok=True)
    wrote_header = False
    total_rows_read = 0
    total_rows_written = 0
    total_invalid = 0
    source_records = []

    try:
        with _open_text_output(temporary_output) as output:
            for region, path in source_paths.items():
                inspection = inspections[region]
                parquet = pq.ParquetFile(path)
                selected_columns = [inspection["geometry_column"]]
                if inspection["has_cropfield"]:
                    selected_columns.append("cropfield")
                selected_columns.extend(inspection["year_columns"])

                region_rows_read = 0
                region_rows_written = 0
                region_invalid = 0
                for batch in parquet.iter_batches(
                    batch_size=batch_size,
                    columns=selected_columns,
                ):
                    frame, invalid_count = _batch_to_frame(
                        batch,
                        region=region,
                        geometry_column=inspection["geometry_column"],
                        source_crs=inspection["source_crs"],
                        source_year_columns=inspection["year_columns"],
                        all_year_columns=all_year_columns,
                        has_cropfield=inspection["has_cropfield"],
                    )
                    frame.to_csv(
                        output,
                        index=False,
                        header=not wrote_header,
                        na_rep="",
                        float_format="%.8f",
                        lineterminator="\n",
                    )
                    wrote_header = True
                    region_rows_read += batch.num_rows
                    region_rows_written += len(frame)
                    region_invalid += invalid_count

                total_rows_read += region_rows_read
                total_rows_written += region_rows_written
                total_invalid += region_invalid
                source_records.append(
                    {
                        "region": region,
                        "filename": path.name,
                        "url": source_url(region, source_base_url),
                        "sha256": sha256_file(path),
                        "size_bytes": path.stat().st_size,
                        "rows_read": region_rows_read,
                        "rows_written": region_rows_written,
                        "invalid_geometry_rows_skipped": region_invalid,
                        "columns": inspection["year_columns"],
                        "http": (source_http_metadata or {}).get(region, {}),
                    }
                )

        os.replace(temporary_output, output_path)
    except Exception:
        temporary_output.unlink(missing_ok=True)
        raise

    provenance = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dataset": {
            "title": "EuroCropsV2.01",
            "version": SOURCE_DATASET_VERSION,
            "publisher": "European Commission, Joint Research Centre",
            "doi": SOURCE_DATASET_DOI,
            "license": "CC-BY-4.0",
            "copyright": "European Union, 1995-2026",
        },
        "transformation": {
            "description": (
                "Each EPSG:3035 parcel polygon was replaced by a Shapely "
                "point_on_surface and transformed to EPSG:4326. Original "
                "annual cYYYY and cfYYYY values were retained."
            ),
            "source_crs": "EPSG:3035",
            "output_crs": "EPSG:4326",
            "coordinate_precision_decimal_places": 8,
            "batch_size": batch_size,
        },
        "coverage": {
            "regions": list(source_paths),
            "year_columns": all_year_columns,
        },
        "counts": {
            "rows_read": total_rows_read,
            "rows_written": total_rows_written,
            "invalid_geometry_rows_skipped": total_invalid,
        },
        "output": {
            "filename": output_path.name,
            "sha256": sha256_file(output_path),
            "size_bytes": output_path.stat().st_size,
        },
        "sources": source_records,
    }
    provenance_path.write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return provenance


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument(
        "--regions",
        nargs="+",
        default=list(DEFAULT_REGIONS),
        help="Stack-file region prefixes; defaults to the full official set.",
    )
    parser.add_argument("--base-url", default=SOURCE_BASE_URL)
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download missing *_stack.parquet files from JRC.",
    )
    parser.add_argument("--batch-size", type=int, default=50_000)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.batch_size < 1:
        raise ValueError("--batch-size must be positive.")

    regions = list(dict.fromkeys(region.lower() for region in args.regions))
    unknown = sorted(set(regions) - set(DEFAULT_REGIONS))
    if unknown:
        raise ValueError(f"Unknown region prefixes: {unknown}")

    paths = {
        region: args.source_dir / f"{region}_stack.parquet"
        for region in regions
    }
    http_metadata = {}
    for region, path in paths.items():
        if args.download:
            http_metadata[region] = download_source(
                region,
                path,
                base_url=args.base_url,
            )
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing {path}. Download it first or pass --download."
            )

    provenance_path = args.provenance or (
        args.output.parent / "PROVENANCE.json"
    )
    provenance = build_points_dataset(
        paths,
        args.output,
        provenance_path,
        batch_size=args.batch_size,
        overwrite=args.overwrite,
        source_http_metadata=http_metadata,
        source_base_url=args.base_url,
    )
    print(
        f"Built {args.output} with {provenance['counts']['rows_written']:,} rows; "
        f"SHA-256 {provenance['output']['sha256']}"
    )
    print(f"Provenance: {provenance_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

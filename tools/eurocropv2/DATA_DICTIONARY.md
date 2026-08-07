# Data dictionary

The table is encoded as UTF-8 CSV, normally compressed as `points.csv.gz`.
Missing values are represented by empty fields. Coordinates use decimal
degrees in EPSG:4326 and are serialized to eight decimal places.

| Column | Type | Description |
|---|---|---|
| `source_region` | string | Region prefix of the official EuroCropsV2 stack file, for example `fr` or `de4`. |
| `source_cropfield` | string/integer | Stack-level crop-field identifier from the source table. It is only unique together with `source_region`. |
| `lon` | decimal | Longitude of the parcel's representative point in EPSG:4326. |
| `lat` | decimal | Latitude of the parcel's representative point in EPSG:4326. |
| `cYYYY` | string | Original cultivation/crop code for year `YYYY`. Codes are source-specific and require the official EuroCropsV2 mapping tables for semantic interpretation. |
| `cfYYYY` | string/integer | Identifier of the corresponding parcel in the annual GSA layer for year `YYYY`. |

The set of years differs between regions. The combined table contains the
union of all available `cYYYY` and `cfYYYY` columns; unavailable regional years
are empty.

## Spatial interpretation

The point is computed with Shapely `point_on_surface`, not with a geometric
centroid. It is intended to lie inside the parcel geometry. It is suitable for
point-in-bounding-box and S2-cell assignment, but it cannot reconstruct the
original parcel boundary or area.

## Provenance

`PROVENANCE.json` records source filenames, URLs, SHA-256 checksums, processed
columns, row counts, skipped invalid geometries, CRS transformation and the
checksum of the published data file.

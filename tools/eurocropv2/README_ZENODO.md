# FARMWISE EuroCropsV2.01 representative-point derivative

This deposit contains a derived, point-based representation of the European
Commission Joint Research Centre EuroCropsV2.01 parcel dataset. It was created for
spatial lookup and S2-cell aggregation by FARMWISE-API.

## Contents

- `points.csv.gz`: UTF-8 CSV data compressed with gzip.
- `DATA_DICTIONARY.md`: column definitions and spatial interpretation.
- `PROVENANCE.json`: exact source files, their SHA-256 checksums, processing
  parameters, coverage, row counts and output checksum.
- `LICENSE.txt`: source attribution, licence and description of changes.
- `SHA256SUMS`: checksums for integrity verification.

## Method

For each official regional `*_stack.parquet` file, the parcel geometry was
converted to an interior representative point using Shapely
`point_on_surface`. Coordinates were transformed from ETRS89 / LAEA Europe
(EPSG:3035) to WGS 84 longitude/latitude (EPSG:4326). Annual cultivation codes
(`cYYYY`) and annual parcel identifiers (`cfYYYY`) were retained. Regional
tables were concatenated into one compressed CSV.

The transformation is reproducible with:

https://github.com/SmolakK/FARMWISE-API/tree/main/tools/eurocropv2

## Source and citation

European Commission, Joint Research Centre (2026): EuroCropsV2 [Dataset],
source snapshot EuroCropsV2.01.
https://doi.org/10.2905/b9fb9e67-78a9-4327-9d59-39a928d812d3

Dataset description article:
https://doi.org/10.5194/essd-18-4075-2026

Source data copyright: European Union, 1995-2026. Source data and this
derivative are distributed under Creative Commons Attribution 4.0
International. The conversion from polygons to points and all other changes
are described above and in `PROVENANCE.json`.

## Limitations

- A representative point is not a parcel geometry and carries no boundary or
  area information.
- Crop codes may be country-specific; use the official EuroCropsV2 mapping
  tables to interpret them.
- Coverage and available years differ by region.
- Only declared agricultural parcels present in the source are represented.
- Invalid or empty source geometries are omitted and counted in provenance.

## FARMWISE installation

FARMWISE downloads the compressed file on first use after its Zenodo record is
registered in `core/utils/data_manifest.py`. For manual installation, place it
at:

```text
%FARMWISE_DATA_DIR%/EuroCropV2/data/points.csv.gz
```

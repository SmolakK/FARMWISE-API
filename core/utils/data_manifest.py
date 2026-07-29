"""
Manifest of adapter data files that are too large (or too licence-encumbered)
to ship inside the git repository / package distribution.

Each entry maps a path *relative to DATA_ROOT* (i.e. the same string you'd
pass to ``adapter_data(*parts)``, joined with "/") to where it can be fetched
from and how to verify it.

Two entry kinds:

    "file"    -- a single file downloaded directly to that relative path.
    "archive" -- a .zip downloaded and extracted; ``extract_to`` is the
                 directory (relative to DATA_ROOT) it should be unpacked into.
                 Use this for things like the IFSGRID shapefile bundle.

How to add an entry
--------------------
1. Upload the file to the project's Zenodo record (same DOI as the code
   release, or a linked "data" deposit -- check the source's licence permits
   redistribution first; if not, deregister the adapter instead).
2. Compute its checksum:  ``sha256sum path/to/file``
3. Add the entry below.
"""

from __future__ import annotations

REMOTE_DATA: dict[str, dict] = {
    "eea/eea_data/eea_r_3035_1_km_env-zones_p_2018_v01_r00.tif": {
        "kind": "file",
        "url": "https://zenodo.org/records/REPLACE_ME/files/eea_r_3035_1_km_env-zones_p_2018_v01_r00.tif",
        "sha256": "REPLACE_ME",
        "size_mb": 5,  # confirm from EEA source
    },
    "correctiv/data/data_points.parquet": {
        "kind": "file",
        "url": "https://zenodo.org/records/REPLACE_ME/files/data_points.parquet",
        "sha256": "REPLACE_ME",
        "size_mb": 1,  # likely small enough to just commit instead -- check
    },
    "EuroCropV2/data/points.csv": {
        "kind": "file",
        "url": "https://zenodo.org/records/REPLACE_ME/files/points.csv",
        "sha256": "REPLACE_ME",
        "size_mb": 1,  # likely small enough to just commit instead -- check
    },
    "IFSGRID/data/IFSGRID/data": {
        "kind": "archive",
        "url": "https://zenodo.org/records/REPLACE_ME/files/ifsgrid_shapefiles.zip",
        "sha256": "REPLACE_ME",
        "extract_to": "IFSGRID/data/IFSGRID/data",
        "size_mb": 50,  # confirm -- verify redistribution licence first
    },
}

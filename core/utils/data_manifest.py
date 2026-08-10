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
        "url": "https://sdi.eea.europa.eu/datastore/public?path=/eea_r_3035_1_km_env-zones_p_2018_v01_r00/#",
        "sha256": "4587A4ACCEE9053D8F7E5779A924911545EF75795F18FE846E082A6B453DDCB6",
        "size_mb": 57.2,
    },
    "EuroCropV2/data/points.csv": {
        "kind": "file",
        "url": "https://doi.org/10.5281/zenodo.21871068",
        "sha256": "D0E40DCAB9EDC7D653B7B40FF308C87B5F6C983F6A504BF5A6A20D34E8939987",
        "size_mb": 7_000_000,
    },
    "IFSGRID/data/IFSGRID/data": {
        "kind": "archive",
        "url": "http://ec.europa.eu/assets/estat/E/E4/gisco/farmstatistics/data.zip",
        "sha256": "0519EEBB3CA43C2FBC3FBFBD355C0CDF44252C021D4C8889AB0CE043C72581CA ",
        "extract_to": "IFSGRID/data/IFSGRID/data",
        "size_mb": 300,
    },
}

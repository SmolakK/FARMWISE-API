"""Point FARMWISE at a published Zenodo ``points.csv.gz`` file.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from urllib.parse import quote


START_MARKER = "    # EUROCROPV2_REMOTE_START"
END_MARKER = "    # EUROCROPV2_REMOTE_END"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def update_manifest(
    manifest_path: Path,
    *,
    record_id: str,
    data_file: Path,
) -> str:
    if not re.fullmatch(r"\d+", record_id):
        raise ValueError("Zenodo record ID must contain digits only.")
    if data_file.name not in {"points.csv", "points.csv.gz"}:
        raise ValueError("Data file must be named points.csv or points.csv.gz.")
    if not data_file.is_file():
        raise FileNotFoundError(data_file)

    text = manifest_path.read_text(encoding="utf-8")
    if text.count(START_MARKER) != 1 or text.count(END_MARKER) != 1:
        raise ValueError("EuroCropsV2 manifest markers are missing or duplicated.")
    start = text.index(START_MARKER)
    end = text.index(END_MARKER) + len(END_MARKER)

    filename = quote(data_file.name)
    url = f"https://zenodo.org/records/{record_id}/files/{filename}?download=1"
    size_mib = data_file.stat().st_size / (1024 * 1024)
    replacement = "\n".join(
        [
            START_MARKER,
            f'    "EuroCropV2/data/{data_file.name}": {{',
            '        "kind": "file",',
            f'        "url": "{url}",',
            f'        "sha256": "{_sha256(data_file)}",',
            f'        "size_mb": {size_mib:.3f},',
            "    },",
            END_MARKER,
        ]
    )
    updated = text[:start] + replacement + text[end:]
    manifest_path.write_text(updated, encoding="utf-8")
    return url


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-id", required=True)
    parser.add_argument("--data-file", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("core/utils/data_manifest.py"),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    url = update_manifest(
        args.manifest,
        record_id=args.record_id,
        data_file=args.data_file,
    )
    print(f"Updated {args.manifest}")
    print(f"Download URL: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

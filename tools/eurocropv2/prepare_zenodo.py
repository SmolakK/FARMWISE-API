"""Prepare metadata and sidecar files for a EuroCropsV2 Zenodo deposit.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import date
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE_DOI = "10.2905/b9fb9e67-78a9-4327-9d59-39a928d812d3"
REPOSITORY_URL = "https://github.com/SmolakK/FARMWISE-API"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _creator(name: str, affiliation: str | None, orcid: str | None) -> dict:
    if "," not in name or "REPLACE" in name.upper():
        raise ValueError("Creator must use the form 'Surname, Given names'.")
    result = {"name": name}
    if affiliation:
        result["affiliation"] = affiliation
    if orcid:
        result["orcid"] = orcid
    return result


def build_metadata(
    *,
    creator_name: str,
    creator_affiliation: str | None,
    creator_orcid: str | None,
    version: str,
) -> dict:
    return {
        "title": "FARMWISE EuroCropsV2.01 representative-point derivative",
        "upload_type": "dataset",
        "description": (
            "Representative-point derivative of the European Commission "
            "Joint Research Centre EuroCropsV2.01 parcel data. Parcel polygons "
            "were converted to interior representative points, transformed "
            "from EPSG:3035 to EPSG:4326, and their annual crop codes and "
            "parcel identifiers were retained for use by FARMWISE. See "
            "README.md and PROVENANCE.json for methods and limitations."
        ),
        "creators": [
            _creator(creator_name, creator_affiliation, creator_orcid)
        ],
        "license": "cc-by-4.0",
        "access_right": "open",
        "publication_date": date.today().isoformat(),
        "version": version,
        "keywords": [
            "EuroCropsV2",
            "agricultural parcels",
            "crop declarations",
            "representative points",
            "FARMWISE",
            "European Union",
        ],
        "related_identifiers": [
            {
                "identifier": SOURCE_DOI,
                "relation": "isDerivedFrom",
            },
            {
                "identifier": "10.5194/essd-18-4075-2026",
                "relation": "isDescribedBy",
            },
            {
                "identifier": REPOSITORY_URL,
                "relation": "isCompiledBy",
            },
        ],
        "notes": (
            "Source data copyright: European Union, 1995-2026. Changes: "
            "polygon geometries were replaced by representative points; "
            "coordinates were transformed to EPSG:4326; regional stack "
            "tables were concatenated and compressed as CSV.GZ."
        ),
    }


def prepare_deposit(
    *,
    data_file: Path,
    provenance_file: Path,
    output_dir: Path,
    creator_name: str,
    creator_affiliation: str | None = None,
    creator_orcid: str | None = None,
    version: str = "1.0.0",
) -> list[Path]:
    if data_file.name not in {"points.csv", "points.csv.gz"}:
        raise ValueError("The data file must be named points.csv or points.csv.gz.")
    if not data_file.is_file():
        raise FileNotFoundError(data_file)
    if not provenance_file.is_file():
        raise FileNotFoundError(provenance_file)

    provenance = json.loads(provenance_file.read_text(encoding="utf-8"))
    expected_digest = provenance.get("output", {}).get("sha256")
    actual_digest = _sha256(data_file)
    if expected_digest != actual_digest:
        raise ValueError(
            "The data file does not match PROVENANCE.json: "
            f"expected {expected_digest}, got {actual_digest}."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise FileExistsError(
            f"Deposit directory is not empty: {output_dir}. Use a new directory."
        )

    sidecars = []
    for source_name, destination_name in (
        ("README_ZENODO.md", "README.md"),
        ("DATA_DICTIONARY.md", "DATA_DICTIONARY.md"),
        ("DATA_LICENSE.txt", "LICENSE.txt"),
    ):
        destination = output_dir / destination_name
        shutil.copy2(HERE / source_name, destination)
        sidecars.append(destination)

    provenance_destination = output_dir / "PROVENANCE.json"
    shutil.copy2(provenance_file, provenance_destination)
    sidecars.append(provenance_destination)

    metadata = build_metadata(
        creator_name=creator_name,
        creator_affiliation=creator_affiliation,
        creator_orcid=creator_orcid,
        version=version,
    )
    metadata_path = output_dir / "zenodo_metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    upload_files = [data_file.resolve(), *sidecars]
    checksum_path = output_dir / "SHA256SUMS"
    checksum_lines = [
        f"{_sha256(path)}  {path.name}" for path in upload_files
    ]
    checksum_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    upload_files.append(checksum_path)

    upload_list = output_dir / "UPLOAD_FILES.txt"
    upload_list.write_text(
        "\n".join(str(path.resolve()) for path in upload_files) + "\n",
        encoding="utf-8",
    )
    return upload_files


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-file", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--creator-name", required=True)
    parser.add_argument("--creator-affiliation")
    parser.add_argument("--creator-orcid")
    parser.add_argument("--version", default="1.0.0")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    files = prepare_deposit(
        data_file=args.data_file,
        provenance_file=args.provenance,
        output_dir=args.output_dir,
        creator_name=args.creator_name,
        creator_affiliation=args.creator_affiliation,
        creator_orcid=args.creator_orcid,
        version=args.version,
    )
    print(f"Prepared {len(files)} files for upload in {args.output_dir}")
    print(f"Metadata: {args.output_dir / 'zenodo_metadata.json'}")
    print(f"Upload list: {args.output_dir / 'UPLOAD_FILES.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

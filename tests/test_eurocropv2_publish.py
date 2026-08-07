import gzip
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import shapely
from pyproj import CRS, Transformer

from adapters.API_readers.EuroCropV2 import EuroCropV2_read
from tools.eurocropv2.build_points import build_points_dataset, sha256_file
from tools.eurocropv2.finalize_manifest import update_manifest
from tools.eurocropv2.prepare_zenodo import prepare_deposit


def _write_stack(path: Path):
    to_source = Transformer.from_crs(4326, 3035, always_xy=True)
    x, y = to_source.transform(17.0, 50.0)
    polygon = shapely.box(x - 100, y - 100, x + 100, y + 100)
    table = pa.table(
        {
            "cropfield": [123],
            "c2022": ["wheat"],
            "cf2022": [456],
            "geom": [shapely.to_wkb(polygon)],
        }
    )
    geo = {
        "version": "1.0.0",
        "primary_column": "geom",
        "columns": {
            "geom": {
                "encoding": "WKB",
                "geometry_types": ["Polygon"],
                "crs": CRS.from_epsg(3035).to_json_dict(),
            }
        },
    }
    table = table.replace_schema_metadata(
        {b"geo": json.dumps(geo).encode("utf-8")}
    )
    pq.write_table(table, path)


def test_build_points_dataset_creates_deterministic_gzip_and_provenance(tmp_path):
    source = tmp_path / "pl_stack.parquet"
    _write_stack(source)
    output = tmp_path / "points.csv.gz"
    provenance_path = tmp_path / "PROVENANCE.json"

    provenance = build_points_dataset(
        {"pl": source},
        output,
        provenance_path,
        batch_size=1,
    )

    result = pd.read_csv(output)
    assert result.loc[0, "source_region"] == "pl"
    assert result.loc[0, "source_cropfield"] == 123
    assert result.loc[0, "c2022"] == "wheat"
    assert result.loc[0, "cf2022"] == 456
    assert result.loc[0, "lon"] == pytest.approx(17.0, abs=0.01)
    assert result.loc[0, "lat"] == pytest.approx(50.0, abs=0.01)
    assert provenance["counts"] == {
        "rows_read": 1,
        "rows_written": 1,
        "invalid_geometry_rows_skipped": 0,
    }
    assert provenance["output"]["sha256"] == sha256_file(output)
    assert json.loads(provenance_path.read_text(encoding="utf-8"))[
        "source_dataset"
    ]["license"] == "CC-BY-4.0"
    assert provenance["source_dataset"]["version"] == "2.01"

    with gzip.open(output, "rt", encoding="utf-8") as handle:
        assert handle.readline().startswith("source_region,source_cropfield,lon,lat")


def test_prepare_deposit_validates_checksum_and_creates_upload_sidecars(tmp_path):
    data_file = tmp_path / "points.csv.gz"
    with gzip.open(data_file, "wt", encoding="utf-8") as handle:
        handle.write("lon,lat\n17,50\n")
    provenance_file = tmp_path / "PROVENANCE.json"
    provenance_file.write_text(
        json.dumps(
            {
                "output": {
                    "filename": data_file.name,
                    "sha256": sha256_file(data_file),
                    "size_bytes": data_file.stat().st_size,
                }
            }
        ),
        encoding="utf-8",
    )

    output_dir = tmp_path / "deposit"
    files = prepare_deposit(
        data_file=data_file,
        provenance_file=provenance_file,
        output_dir=output_dir,
        creator_name="Smolak, Kamil",
        creator_affiliation="Example University",
        version="1.0.0",
    )

    assert data_file.resolve() in files
    assert (output_dir / "LICENSE.txt").is_file()
    assert (output_dir / "SHA256SUMS").is_file()
    metadata = json.loads(
        (output_dir / "zenodo_metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["license"] == "cc-by-4.0"
    assert metadata["creators"] == [
        {"name": "Smolak, Kamil", "affiliation": "Example University"}
    ]
    assert metadata["related_identifiers"][0]["relation"] == "isDerivedFrom"


def test_prepare_deposit_rejects_modified_data(tmp_path):
    data_file = tmp_path / "points.csv.gz"
    data_file.write_bytes(b"modified")
    provenance = tmp_path / "PROVENANCE.json"
    provenance.write_text(
        json.dumps({"output": {"sha256": "0" * 64}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match PROVENANCE"):
        prepare_deposit(
            data_file=data_file,
            provenance_file=provenance,
            output_dir=tmp_path / "deposit",
            creator_name="Smolak, Kamil",
        )


def test_finalize_manifest_uses_published_record_and_real_checksum(tmp_path):
    data_file = tmp_path / "points.csv.gz"
    data_file.write_bytes(b"data")
    manifest = tmp_path / "data_manifest.py"
    manifest.write_text(
        "REMOTE_DATA = {\n"
        "    # EUROCROPV2_REMOTE_START\n"
        "    # not configured\n"
        "    # EUROCROPV2_REMOTE_END\n"
        "}\n",
        encoding="utf-8",
    )

    url = update_manifest(
        manifest,
        record_id="123456",
        data_file=data_file,
    )

    updated = manifest.read_text(encoding="utf-8")
    assert url == (
        "https://zenodo.org/records/123456/files/points.csv.gz?download=1"
    )
    assert sha256_file(data_file) in updated
    assert '"EuroCropV2/data/points.csv.gz"' in updated
    assert updated.count("EUROCROPV2_REMOTE_START") == 1


def test_reader_prefers_compressed_points(monkeypatch):
    calls = []

    def resolve(*parts):
        calls.append(parts)
        return Path("points.csv.gz")

    monkeypatch.setattr(EuroCropV2_read, "adapter_data", resolve)

    assert EuroCropV2_read._resolve_points_data() == Path("points.csv.gz")
    assert calls == [("EuroCropV2", "data", "points.csv.gz")]


def test_reader_falls_back_to_uncompressed_points(monkeypatch):
    def resolve(*parts):
        if parts[-1].endswith(".gz"):
            raise FileNotFoundError
        return Path("points.csv")

    monkeypatch.setattr(EuroCropV2_read, "adapter_data", resolve)

    assert EuroCropV2_read._resolve_points_data() == Path("points.csv")

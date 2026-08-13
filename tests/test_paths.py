import hashlib
import zipfile
from pathlib import Path
from unittest.mock import Mock, call

import pytest

from farmwise_api.core.utils import paths


def test_adapter_data_returns_bundled_file(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    resource = data_root / "source" / "values.csv"
    resource.parent.mkdir(parents=True)
    resource.write_text("value\n1\n", encoding="utf-8")
    monkeypatch.setattr(paths, "DATA_ROOT", data_root)

    assert paths.adapter_data("source", "values.csv") == resource


def test_adapter_data_fetches_manifest_entry(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "DATA_ROOT", tmp_path / "missing-data")
    monkeypatch.setattr(
        paths,
        "REMOTE_DATA",
        {"source/values.csv": {"kind": "file", "url": "https://example.test/data"}},
    )
    expected = tmp_path / "cache" / "source" / "values.csv"
    fetch = Mock(return_value=expected)
    monkeypatch.setattr(paths, "fetch_remote", fetch)

    assert paths.adapter_data("source", "values.csv") == expected
    fetch.assert_called_once_with("source/values.csv")


def test_adapter_data_reports_missing_resource(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(paths, "REMOTE_DATA", {})

    with pytest.raises(FileNotFoundError, match="not listed"):
        paths.adapter_data("unknown", "missing.tif")


def test_sha256_reads_file_in_chunks(tmp_path):
    file_path = tmp_path / "payload.bin"
    payload = b"farmwise" * 200_000
    file_path.write_bytes(payload)

    assert paths._sha256(file_path) == hashlib.sha256(payload).hexdigest()


def test_download_streams_to_destination(monkeypatch, tmp_path):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            assert chunk_size == 1 << 20
            return iter((b"first", b"", b"second"))

    get = Mock(return_value=FakeResponse())
    monkeypatch.setattr("requests.get", get)
    destination = tmp_path / "nested" / "payload.bin"

    paths._download("https://example.test/payload", destination)

    assert destination.read_bytes() == b"firstsecond"
    assert not list(destination.parent.glob("*.part-*"))
    get.assert_called_once_with(
        "https://example.test/payload", stream=True, timeout=60
    )


def test_fetch_remote_returns_cache_hit_without_download(monkeypatch, tmp_path):
    rel = "source/cached.bin"
    target = tmp_path / rel
    target.parent.mkdir(parents=True)
    target.write_bytes(b"cached")
    monkeypatch.setattr(paths, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(
        paths,
        "REMOTE_DATA",
        {rel: {"kind": "file", "url": "https://example.test/cached.bin"}},
    )
    download = Mock()
    monkeypatch.setattr(paths, "_download", download)

    assert paths.fetch_remote(rel) == target
    download.assert_not_called()


def test_fetch_remote_downloads_and_verifies_file(monkeypatch, tmp_path):
    rel = "source/new.bin"
    payload = b"verified payload"
    monkeypatch.setattr(paths, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(
        paths,
        "REMOTE_DATA",
        {
            rel: {
                "kind": "file",
                "url": "https://example.test/new.bin",
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        },
    )

    def fake_download(_url, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)

    monkeypatch.setattr(paths, "_download", fake_download)

    target = paths.fetch_remote(rel)

    assert target.read_bytes() == payload


def test_fetch_remote_deletes_file_with_invalid_checksum(monkeypatch, tmp_path):
    rel = "source/corrupt.bin"
    monkeypatch.setattr(paths, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(
        paths,
        "REMOTE_DATA",
        {
            rel: {
                "kind": "file",
                "url": "https://example.test/corrupt.bin",
                "sha256": hashlib.sha256(b"expected").hexdigest(),
            }
        },
    )

    def fake_download(_url, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"corrupt")

    monkeypatch.setattr(paths, "_download", fake_download)

    with pytest.raises(ValueError, match="Checksum mismatch"):
        paths.fetch_remote(rel)

    assert not (tmp_path / rel).exists()


def test_fetch_remote_extracts_archive_and_removes_temporary_zip(
    monkeypatch, tmp_path
):
    rel = "bundle/ready.txt"
    monkeypatch.setattr(paths, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(
        paths,
        "REMOTE_DATA",
        {
            rel: {
                "kind": "archive",
                "url": "https://example.test/bundle.zip",
                "sha256": "REPLACE_ME",
                "extract_to": "bundle",
            }
        },
    )

    def fake_download(_url, destination):
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("ready.txt", "ready")

    monkeypatch.setattr(paths, "_download", fake_download)

    target = paths.fetch_remote(rel)

    assert target.read_text(encoding="utf-8") == "ready"
    assert not list(tmp_path.glob(".archive_*.zip"))


def test_fetch_remote_rejects_unknown_manifest_kind(monkeypatch, tmp_path):
    rel = "source/item"
    monkeypatch.setattr(paths, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(
        paths,
        "REMOTE_DATA",
        {rel: {"kind": "unsupported", "url": "https://example.test/item"}},
    )

    with pytest.raises(ValueError, match="Unknown manifest entry kind"):
        paths.fetch_remote(rel)


def test_prefetch_all_filters_sources(monkeypatch):
    monkeypatch.setattr(
        paths,
        "REMOTE_DATA",
        {
            "eea/raster.tif": {},
            "correctiv/data.parquet": {},
            "other/data.csv": {},
        },
    )
    fetch = Mock()
    monkeypatch.setattr(paths, "fetch_remote", fetch)

    paths.prefetch_all(["eea", "correctiv"])

    assert fetch.call_args_list == [
        call("eea/raster.tif"),
        call("correctiv/data.parquet"),
    ]


def test_cache_and_scratch_paths_are_writable_and_unique(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(paths.tempfile, "gettempdir", lambda: str(tmp_path))

    cache = paths.adapter_cache("adapter")
    first = paths.scratch_file("adapter", suffix=".csv", stem="result")
    second = paths.scratch_file("adapter", suffix=".csv", stem="result")

    assert cache.is_dir()
    assert first.parent == tmp_path / "farmwise" / "adapter"
    assert first.suffix == ".csv"
    assert first != second


def test_scratch_dir_is_removed_after_context():
    with paths.scratch_dir("adapter") as directory:
        created = Path(directory)
        (created / "result.txt").write_text("ok", encoding="utf-8")
        assert created.is_dir()

    assert not created.exists()

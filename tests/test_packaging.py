from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_public_package_excludes_egdi_and_large_adapter_data():
    with (ROOT / "pyproject.toml").open("rb") as config_file:
        config = tomllib.load(config_file)

    setuptools = config["tool"]["setuptools"]
    package_data = setuptools["package-data"]
    excluded_packages = setuptools["packages"]["find"]["exclude"]

    assert setuptools["include-package-data"] is False
    assert "adapters.API_readers.egdi*" in excluded_packages

    forbidden_suffixes = {".db", ".nc", ".parquet", ".sqlite", ".tif", ".tiff"}
    allowlisted_patterns = {
        pattern
        for patterns in package_data.values()
        for pattern in patterns
    }
    assert not any(Path(pattern).suffix in forbidden_suffixes
                   for pattern in allowlisted_patterns)


def test_sdist_manifest_prunes_private_and_large_data():
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    required_prunes = {
        "prune adapters/API_readers/egdi",
        "prune adapters/API_readers/EuroCropV2/data",
        "prune adapters/API_readers/correctiv/data",
        "prune adapters/API_readers/eea/eea_data",
        "prune adapters/API_readers/IFSGRID/data",
    }
    assert required_prunes <= set(manifest.splitlines())
    assert "exclude tests/test_egdi_read_d10.py" in manifest
    assert "exclude tests/test_egdi_read_hc.py" in manifest

from email.parser import BytesParser
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
from zipfile import ZipFile

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory):
    wheel_dir = tmp_path_factory.mktemp("farmwise-wheel")
    source_dir = tmp_path_factory.mktemp("farmwise-source")
    for filename in (
        "LICENSE",
        "MANIFEST.in",
        "README.md",
        "main.py",
        "main_call.py",
        "pyproject.toml",
        "quality_assess.py",
    ):
        shutil.copy2(ROOT / filename, source_dir / filename)
    for package in ("adapters", "core", "evaluation", "server"):
        shutil.copytree(
            ROOT / package,
            source_dir / package,
            ignore=shutil.ignore_patterns(
                "__pycache__",
                "*.pyc",
                "data",
                "eea_data",
                "temp_storage",
            ),
        )

    build_python = os.environ.get("FARMWISE_BUILD_PYTHON", sys.executable)
    result = subprocess.run(
        [
            build_python,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-cache-dir",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_dir),
        ],
        cwd=source_dir,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    wheels = list(wheel_dir.glob("farmwise_api-*.whl"))
    assert len(wheels) == 1
    return wheels[0]


def test_built_wheel_installs_and_exposes_local_api(built_wheel, tmp_path):
    install_dir = tmp_path / "installed"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--no-deps",
            "--target",
            str(install_dir),
            str(built_wheel),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    smoke_test = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {str(install_dir)!r}); "
                "from main_call import read_data; "
                "assert callable(read_data)"
            ),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert smoke_test.returncode == 0, smoke_test.stdout + smoke_test.stderr


def test_built_wheel_declares_runtime_and_server_dependencies(built_wheel):
    with ZipFile(built_wheel) as wheel:
        names = set(wheel.namelist())
        metadata_name = next(
            name for name in names if name.endswith(".dist-info/METADATA")
        )
        metadata = BytesParser().parsebytes(wheel.read(metadata_name))

    base_requirements = [
        requirement
        for requirement in metadata.get_all("Requires-Dist", [])
        if "extra ==" not in requirement
    ]
    assert "hubeaupyutils==0.1.0" in base_requirements

    assert "server" in metadata.get_all("Provides-Extra", [])
    server_requirements = [
        requirement
        for requirement in metadata.get_all("Requires-Dist", [])
        if 'extra == "server"' in requirement
    ]
    for dependency in ("fastapi", "sqlalchemy", "uvicorn"):
        assert any(requirement.startswith(dependency) for requirement in server_requirements)

    assert "main.py" in names
    assert "server/main.py" in names


def test_public_package_excludes_egdi_and_large_adapter_data():
    with (ROOT / "pyproject.toml").open("rb") as config_file:
        config = tomllib.load(config_file)

    setuptools = config["tool"]["setuptools"]
    package_data = setuptools["package-data"]
    excluded_packages = setuptools["packages"]["find"]["exclude"]

    assert setuptools["include-package-data"] is False
    assert "adapters.API_readers.egdi*" in excluded_packages
    assert "adapters.API_readers.imgw" not in package_data
    assert "adapters.API_readers.imgw_hydro" not in package_data

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
        "prune adapters/API_readers/imgw/constants",
        "prune adapters/API_readers/imgw_hydro/constants",
        "prune adapters/API_readers/eea/eea_data",
        "prune adapters/API_readers/IFSGRID/data",
    }
    assert required_prunes <= set(manifest.splitlines())
    assert "exclude tests/test_egdi_read_d10.py" in manifest
    assert "exclude tests/test_egdi_read_hc.py" in manifest

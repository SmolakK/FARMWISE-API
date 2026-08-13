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
        "DATA_LICENSES.md",
        "MANIFEST.in",
        "README.md",
        "pyproject.toml",
    ):
        shutil.copy2(ROOT / filename, source_dir / filename)
    shutil.copytree(
        ROOT / "farmwise_api",
        source_dir / "farmwise_api",
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            "data",
            "eea_data",
            "temp_storage",
        ),
    )
    bundled_license = Path(
        "internal-lib/hubeaupyutils/hubeaupyutils-main/LICENSE"
    )
    (source_dir / bundled_license).parent.mkdir(parents=True)
    shutil.copy2(ROOT / bundled_license, source_dir / bundled_license)

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
                "from farmwise_api import read_data; "
                "from farmwise_api import cli; "
                "from farmwise_api._vendor import hubeaupyutils; "
                "assert callable(read_data); "
                "assert hubeaupyutils.__version__ == '0.1.0'; "
                "assert callable(cli.run)"
            ),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert smoke_test.returncode == 0, smoke_test.stdout + smoke_test.stderr

    base_entrypoint_test = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import importlib.abc\n"
                "import sys\n"
                f"sys.path.insert(0, {str(install_dir)!r})\n"
                "class BlockServer(importlib.abc.MetaPathFinder):\n"
                "    def find_spec(self, fullname, path=None, target=None):\n"
                "        if fullname == 'farmwise_api.server' or fullname.startswith('farmwise_api.server.'):\n"
                "            raise ModuleNotFoundError(name=fullname)\n"
                "        return None\n"
                "sys.meta_path.insert(0, BlockServer())\n"
                "from farmwise_api import cli\n"
                "assert callable(cli.run)\n"
                "try:\n"
                "    cli.run()\n"
                "except SystemExit as error:\n"
                "    assert 'farmwise-api[server]' in str(error)\n"
                "else:\n"
                "    raise AssertionError('base CLI unexpectedly started the server')"
            ),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert base_entrypoint_test.returncode == 0, (
        base_entrypoint_test.stdout + base_entrypoint_test.stderr
    )


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
    assert not any(
        requirement.startswith("hubeaupyutils")
        for requirement in base_requirements
    )

    assert "server" in metadata.get_all("Provides-Extra", [])
    server_requirements = [
        requirement
        for requirement in metadata.get_all("Requires-Dist", [])
        if 'extra == "server"' in requirement
    ]
    for dependency in ("fastapi", "sqlalchemy", "uvicorn"):
        assert any(requirement.startswith(dependency) for requirement in server_requirements)
    assert any(requirement.startswith("PyJWT") for requirement in server_requirements)
    assert not any(requirement.startswith("python-jose") for requirement in server_requirements)

    assert "farmwise_api/__init__.py" in names
    assert "farmwise_api/cli.py" in names
    assert "farmwise_api/server/main.py" in names
    assert "farmwise_api/_vendor/hubeaupyutils/__init__.py" in names
    assert "farmwise_api/_vendor/hubeaupyutils/hubeau.py" in names
    assert "farmwise_api/_vendor/hubeaupyutils/wrappers.py" in names
    for generic_name in (
        "main.py",
        "main_call.py",
        "quality_assess.py",
        "adapters/__init__.py",
        "core/__init__.py",
        "server/__init__.py",
        "hubeaupyutils/__init__.py",
    ):
        assert generic_name not in names
    assert any(
        name.endswith(".dist-info/licenses/DATA_LICENSES.md") for name in names
    )
    assert any(
        "hubeaupyutils" in name and name.endswith("/LICENSE")
        for name in names
    )


def test_public_package_excludes_egdi_and_large_adapter_data():
    with (ROOT / "pyproject.toml").open("rb") as config_file:
        config = tomllib.load(config_file)

    setuptools = config["tool"]["setuptools"]
    package_data = setuptools["package-data"]
    excluded_packages = setuptools["packages"]["find"]["exclude"]

    assert setuptools["include-package-data"] is False
    assert "farmwise_api.adapters.API_readers.egdi*" in excluded_packages
    assert "farmwise_api.adapters.API_readers.imgw" not in package_data
    assert "farmwise_api.adapters.API_readers.imgw_hydro" not in package_data

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

    assert "include SECURITY.md" in manifest
    assert "include CITATION.cff" in manifest

    required_prunes = {
        "prune farmwise_api/adapters/API_readers/egdi",
        "prune farmwise_api/adapters/API_readers/EuroCropV2/data",
        "prune farmwise_api/adapters/API_readers/correctiv/data",
        "prune farmwise_api/adapters/API_readers/imgw/constants",
        "prune farmwise_api/adapters/API_readers/imgw_hydro/constants",
        "prune farmwise_api/adapters/API_readers/eea/eea_data",
        "prune farmwise_api/adapters/API_readers/IFSGRID/data",
        "prune farmwise_api/adapters/API_readers/quadica/data",
    }
    assert required_prunes <= set(manifest.splitlines())
    assert "exclude tests/test_egdi_read_d10.py" in manifest
    assert "exclude tests/test_egdi_read_hc.py" in manifest


def test_publication_governance_documents_are_present():
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")

    assert "GitHub Security Advisory" in security
    assert "REPLACE-WITH-SECURITY-CONTACT@example.com" in security
    assert citation.startswith("cff-version: 1.2.0\n")
    assert "title: FARMWISE-API" in citation
    assert "license: Apache-2.0" in citation
    assert "repository-code: \"https://github.com/SmolakK/FARMWISE-API\"" in citation

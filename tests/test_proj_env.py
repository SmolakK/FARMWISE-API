"""The PROJ guard must fix a stale host database without overreaching."""

import sqlite3

import pytest

from farmwise_api.core.utils import proj_env


def _make_proj_db(directory, minor):
    """Write a minimal proj.db carrying the given layout version."""
    directory.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(directory / "proj.db")
    connection.execute("CREATE TABLE metadata (key TEXT, value TEXT)")
    if minor is not None:
        connection.execute(
            "INSERT INTO metadata VALUES (?, ?)",
            ("DATABASE.LAYOUT.VERSION.MINOR", str(minor)),
        )
    connection.commit()
    connection.close()
    return directory


def test_stale_proj_lib_is_redirected_to_bundled_data(monkeypatch, tmp_path):
    stale = _make_proj_db(tmp_path / "conda", proj_env.MINIMUM_LAYOUT_MINOR - 4)
    monkeypatch.setenv("PROJ_LIB", str(stale))
    monkeypatch.delenv("PROJ_DATA", raising=False)
    monkeypatch.delenv(proj_env.DISABLE_ENV, raising=False)

    applied = proj_env.ensure_usable_proj_data()

    assert applied is not None, "a stale database should have been replaced"
    assert (applied / "proj.db").is_file()
    import os
    assert os.environ["PROJ_DATA"] == str(applied)
    # the host's own variable is deliberately left alone
    assert os.environ["PROJ_LIB"] == str(stale)


def test_current_proj_lib_is_left_alone(monkeypatch, tmp_path):
    current = _make_proj_db(tmp_path / "good", proj_env.MINIMUM_LAYOUT_MINOR)
    monkeypatch.setenv("PROJ_LIB", str(current))
    monkeypatch.delenv("PROJ_DATA", raising=False)
    monkeypatch.delenv(proj_env.DISABLE_ENV, raising=False)

    assert proj_env.ensure_usable_proj_data() is None
    import os
    assert "PROJ_DATA" not in os.environ


def test_unreadable_version_is_left_alone(monkeypatch, tmp_path):
    """An unusual database is the operator's business, not ours."""
    odd = _make_proj_db(tmp_path / "odd", None)
    monkeypatch.setenv("PROJ_LIB", str(odd))
    monkeypatch.delenv("PROJ_DATA", raising=False)
    monkeypatch.delenv(proj_env.DISABLE_ENV, raising=False)

    assert proj_env.ensure_usable_proj_data() is None


def test_explicit_proj_data_wins(monkeypatch, tmp_path):
    stale = _make_proj_db(tmp_path / "conda", 2)
    monkeypatch.setenv("PROJ_LIB", str(stale))
    monkeypatch.setenv("PROJ_DATA", str(tmp_path / "chosen"))
    monkeypatch.delenv(proj_env.DISABLE_ENV, raising=False)

    assert proj_env.ensure_usable_proj_data() is None
    import os
    assert os.environ["PROJ_DATA"] == str(tmp_path / "chosen")


@pytest.mark.parametrize("value", ["0", "false", "no", "OFF"])
def test_guard_can_be_disabled(monkeypatch, tmp_path, value):
    stale = _make_proj_db(tmp_path / "conda", 2)
    monkeypatch.setenv("PROJ_LIB", str(stale))
    monkeypatch.delenv("PROJ_DATA", raising=False)
    monkeypatch.setenv(proj_env.DISABLE_ENV, value)

    assert proj_env.ensure_usable_proj_data() is None


def test_no_proj_lib_is_a_no_op(monkeypatch):
    monkeypatch.delenv("PROJ_LIB", raising=False)
    monkeypatch.delenv("PROJ_DATA", raising=False)
    monkeypatch.delenv(proj_env.DISABLE_ENV, raising=False)

    assert proj_env.ensure_usable_proj_data() is None


def test_locating_bundled_data_does_not_import_rasterio():
    """Importing rasterio here would initialise GDAL before the fix applies.

    GDAL resolves the PROJ search path once, on first use. If this lookup
    imported rasterio, the stale database would already be loaded and setting
    PROJ_DATA afterwards would silently do nothing.
    """
    import subprocess
    import sys

    # The result is signalled by the exit code, not by stdout: importing the
    # package pulls in tqdm/colorama, which can append an ANSI reset sequence
    # to the captured output and defeat any string comparison.
    IMPORTED, NOT_IMPORTED = 3, 0
    probe = (
        "import sys;"
        "from farmwise_api.core.utils.proj_env import _bundled_proj_data;"
        "_bundled_proj_data();"
        f"sys.exit({IMPORTED} if 'rasterio' in sys.modules else {NOT_IMPORTED})"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True,
    )

    assert result.returncode in (IMPORTED, NOT_IMPORTED), (
        f"the probe itself failed ({result.returncode}):\n{result.stderr}"
    )
    assert result.returncode == NOT_IMPORTED, (
        "_bundled_proj_data imported rasterio, which defeats the guard"
    )

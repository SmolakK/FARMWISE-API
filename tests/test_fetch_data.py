import sys
from unittest.mock import MagicMock

import pytest

from core.utils import fetch_data


def test_fetch_data_lists_manifest_entries(monkeypatch, capsys):
    monkeypatch.setattr(
        fetch_data,
        "REMOTE_DATA",
        {"eea/raster.tif": {"kind": "file", "size_mb": 57}},
    )
    monkeypatch.setattr(sys, "argv", ["fetch_data", "--list"])

    fetch_data.main()

    output = capsys.readouterr().out
    assert "eea/raster.tif" in output
    assert "57 MB, file" in output


def test_fetch_data_prefetches_selected_sources(monkeypatch, capsys):
    prefetch = MagicMock()
    monkeypatch.setattr(fetch_data, "prefetch_all", prefetch)
    monkeypatch.setattr(fetch_data, "CACHE_ROOT", "/tmp/farmwise-cache")
    monkeypatch.setattr(
        sys,
        "argv",
        ["fetch_data", "--source", "eea", "--source", "correctiv"],
    )

    fetch_data.main()

    prefetch.assert_called_once_with(sources=["eea", "correctiv"])
    assert "Done. Cached under" in capsys.readouterr().out


def test_fetch_data_requires_an_action(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["fetch_data"])

    with pytest.raises(SystemExit) as exc_info:
        fetch_data.main()

    assert exc_info.value.code == 2

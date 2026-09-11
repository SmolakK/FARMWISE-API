"""The variable/source registry must stay in step with the dispatch code.

The manuscript audit recorded that the paper's source appendix had drifted
from the adapter registry. These tests make that class of drift a build
failure instead of something a reader discovers.
"""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
AUTHORED = ROOT / "registry" / "variables.yaml"
DOC = ROOT / "docs" / "registry.md"
CSV = ROOT / "docs" / "registry.csv"


def _build(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / "build_registry.py"), *args],
        cwd=ROOT, capture_output=True, text=True,
    )


def test_generated_registry_is_up_to_date():
    """docs/registry.* must match what the current code produces."""
    result = _build("--check")
    assert result.returncode == 0, (
        "registry is stale; run `python tools/build_registry.py`\n"
        + result.stdout + result.stderr
    )


def test_registry_covers_every_dispatchable_source():
    """Every registered adapter appears in the authored registry."""
    from farmwise_api.adapters.mappings.data_source_mapping import (
        API_PATH_RANGES, DISABLED_API_SOURCES,
    )

    authored = yaml.safe_load(AUTHORED.read_text(encoding="utf-8"))["sources"]
    expected = set(API_PATH_RANGES) | set(DISABLED_API_SOURCES)

    missing = expected - set(authored)
    assert not missing, f"sources absent from the registry: {sorted(missing)}"

    orphaned = set(authored) - expected
    assert not orphaned, (
        f"registry describes sources the code no longer dispatches: "
        f"{sorted(orphaned)}"
    )


def test_registry_factors_match_the_declared_factor_set():
    """No registry row claims a factor the dispatch registry does not know."""
    import csv as csv_module

    from farmwise_api.adapters.mappings.data_source_mapping import (
        API_PATH_RANGES, DATA_TYPE_HARMONIZATION_METHODS,
    )

    declared = {f for ranges in API_PATH_RANGES.values() for f in ranges[2]}
    # rows for sources with no per-variable table carry these placeholders
    placeholders = {"(unassigned)", "unspecified"}

    with open(CSV, encoding="utf-8", newline="") as handle:
        factors = {row["factor"] for row in csv_module.DictReader(handle)}

    unknown = factors - declared - placeholders
    assert not unknown, f"registry rows use unknown factors: {sorted(unknown)}"

    unconfigured = {
        f for f in factors - placeholders
        if f not in DATA_TYPE_HARMONIZATION_METHODS
    }
    assert not unconfigured, (
        f"factors without a harmonisation rule: {sorted(unconfigured)}"
    )


def test_registry_never_invents_missing_metadata():
    """Unsupplied authored fields stay empty rather than being filled in.

    The registry is scientific metadata. A plausible-looking guess is worse
    than a visible gap, so the generator must render unset fields as an
    explicit placeholder and the CSV must leave them empty.
    """
    import csv as csv_module

    authored = yaml.safe_load(AUTHORED.read_text(encoding="utf-8"))["sources"]
    with open(CSV, encoding="utf-8", newline="") as handle:
        rows = list(csv_module.DictReader(handle))

    for row in rows:
        entry = authored[row["source"]]
        variables = entry.get("variables") or {}
        declared = (variables.get(row["native_variable"]) or {}).get("native_unit")
        if declared in (None, ""):
            assert row["native_unit"] == "", (
                f"{row['source_short']}/{row['native_variable']}: native_unit "
                "appears in the output but was never supplied"
            )

    assert "_not supplied_" in DOC.read_text(encoding="utf-8"), (
        "the documentation should mark unsupplied fields explicitly"
    )


def test_data_licences_reference_real_adapter_modules():
    """Every adapter path in DATA_LICENSES.md must still import.

    Renaming an adapter silently invalidates its licensing entry: the terms
    stay in the register but no longer attach to any code. That is how the
    Met Éireann entry came to point at `Irish MS_daily` after the file was
    renamed, which in turn hid it from the registry builder.
    """
    import importlib.util
    import re as regex

    text = (ROOT / "DATA_LICENSES.md").read_text(encoding="utf-8")
    referenced = sorted(set(
        regex.findall(r"`(farmwise_api\.[A-Za-z0-9_. ]+)`", text)
    ))
    assert referenced, "no adapter modules referenced in DATA_LICENSES.md"

    unresolved = [
        path for path in referenced if importlib.util.find_spec(path) is None
    ]
    assert not unresolved, (
        f"DATA_LICENSES.md references modules that do not exist: {unresolved}"
    )


def test_every_dispatchable_source_has_a_licensing_entry():
    """A source that can return data must have recorded terms."""
    import re as regex

    from farmwise_api.adapters.mappings.data_source_mapping import API_PATH_RANGES

    text = (ROOT / "DATA_LICENSES.md").read_text(encoding="utf-8")
    referenced = set(regex.findall(r"`(farmwise_api\.[A-Za-z0-9_. ]+)`", text))

    undocumented = sorted(set(API_PATH_RANGES) - referenced)
    assert not undocumented, (
        f"dispatchable sources with no DATA_LICENSES.md entry: {undocumented}"
    )


@pytest.mark.parametrize("path", [AUTHORED, DOC, CSV])
def test_registry_artefacts_exist(path):
    assert path.is_file(), f"{path.relative_to(ROOT)} is missing"

"""The generated registry documentation must render as intact tables.

Authored values in registry/variables.yaml are often written as YAML folded
(`>`) blocks, which keep line breaks. A line break inside a markdown table
cell ends the row, so a single entry used to render as a truncated row plus a
stray paragraph. Separately, text in parentheses such as
"environmental data (EEA)" was being reported as a unit.
"""

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "registry.md"
CSV = ROOT / "docs" / "registry.csv"

_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
_SEPARATOR = re.compile(r"^\|(?:\s*:?-+:?\s*\|)+\s*$")


def _cell_count(line):
    return len(_UNESCAPED_PIPE.split(line)) - 2


def _tables(lines):
    """Yield (header_line_number, header_cells, [(line_number, cells), ...])."""
    index = 0
    while index < len(lines):
        if lines[index].startswith("|") and index + 1 < len(lines) \
                and _SEPARATOR.match(lines[index + 1]):
            header = (index + 1, _cell_count(lines[index]))
            body = []
            index += 2
            while index < len(lines) and lines[index].startswith("|"):
                body.append((index + 1, _cell_count(lines[index])))
                index += 1
            yield header[0], header[1], body
        else:
            index += 1


def test_every_table_row_has_as_many_cells_as_its_header():
    lines = DOC.read_text(encoding="utf-8").split("\n")
    tables = list(_tables(lines))
    assert tables, "the registry documentation contains no tables"

    broken = [
        (number, cells, expected)
        for header_line, expected, body in tables
        for number, cells in body
        if cells != expected
    ]
    assert broken == [], (
        "rows whose cell count differs from the header (line, cells, expected): "
        f"{broken[:5]}"
    )


def test_no_table_is_followed_by_a_stray_continuation_line():
    """A row split by a newline leaves its tail as a line starting with text."""
    lines = DOC.read_text(encoding="utf-8").split("\n")
    stray = [
        number + 1
        for number, (current, following) in enumerate(zip(lines, lines[1:]), start=1)
        if current.startswith("|")
        and following.strip()
        and not following.startswith("|")
        and not following.startswith("#")
    ]
    assert stray == [], f"text continuing a table row on lines: {stray[:5]}"


def test_csv_fields_are_single_line():
    with open(CSV, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    multiline = sorted({
        column
        for row in rows
        for column, value in row.items()
        if value and "\n" in value
    })
    assert multiline == [], f"CSV columns containing line breaks: {multiline}"


def test_parenthesised_text_is_not_reported_as_a_unit():
    """Only adapters whose labels use parentheses for units get that reading."""
    with open(CSV, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    not_units = {"EEA", "meadows and pastures", "e.g., orchards, plantations"}
    wrong = sorted(
        (row["source_short"], row["output_unit"])
        for row in rows
        if row["output_unit"] in not_units
    )
    assert wrong == [], f"label text reported as a unit: {wrong}"

    hubeau = [
        row for row in rows
        if row["source_short"] == "hubeau.hubeau_wq_read"
        and row["output_name"].endswith("(mg/L)")
    ]
    assert hubeau and hubeau[0]["output_unit"] == "mg/L", (
        "Hub'Eau units are written in parentheses and must still be read"
    )


def test_output_units_come_from_labels_or_authored_fallback():
    import csv as csv_module

    with open(ROOT / "docs" / "registry.csv", encoding="utf-8", newline="") as handle:
        rows = {
            (row["source_short"], row["native_variable"]): row
            for row in csv_module.DictReader(handle)
        }

    # ERA5 request names are joined to the netCDF labels that carry the unit.
    era5 = {name: rows[("cds.cds_single_levels", name)]["output_unit"]
            for name in ("2m_temperature", "total_precipitation",
                         "volumetric_soil_water_layer_1")}
    assert era5 == {"2m_temperature": "°C", "total_precipitation": "mm",
                    "volumetric_soil_water_layer_1": "%"}
    # A label without a unit falls back to the authored value.
    assert rows[("corine.corine_read", "(land cover)")]["output_unit"].startswith("none")


def test_authored_output_unit_does_not_override_the_adapter_label(capsys):
    sys.path.insert(0, str(ROOT / "tools"))
    import build_registry

    source = "farmwise_api.adapters.API_readers.cds.cds_single_levels"
    authored = {source: {"variables": {"2m_temperature": {"output_unit": "K"}}}}
    row = next(
        r for r in build_registry.collect_rows(authored)
        if r.source == source and r.native_variable == "2m_temperature"
    )
    assert row.output_unit == "°C"
    assert "authored output_unit 'K' ignored" in capsys.readouterr().err

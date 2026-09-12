"""Build the FARMWISE variable/source registry.

The registry describes every *source x native variable* pair FARMWISE can
return: what the provider calls it, what it means, the units in and out, the
spatial and temporal support, the transformation applied, how repeated values
from one source are reduced, and how values from different sources are
combined.

Two inputs, kept deliberately separate:

* the **code** (``API_PATH_RANGES``, each adapter's mapping tables, and the
  harmonisation configuration) is the authority for anything FARMWISE already
  knows. It is read live, so the registry cannot drift from the dispatch
  behaviour it documents.
* ``registry/variables.yaml`` carries only what code cannot state - native
  units, instrument/grid support, and literature references. Entries are
  seeded with ``null`` and must be filled in by a domain author. Nothing here
  is guessed: an unfilled field is reported as missing rather than inferred.

Outputs (generated, do not edit):

* ``docs/registry.md``  - documentation, grouped by variable then source
* ``docs/registry.csv`` - one row per source x native variable

Usage, from the repository root::

    python tools/build_registry.py            # regenerate docs + seed new rows
    python tools/build_registry.py --check    # fail if outputs are stale
    python tools/build_registry.py --report   # completeness summary only
"""

from __future__ import annotations

import argparse
import csv
import importlib
import io
import pkgutil
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AUTHORED = REPO_ROOT / "registry" / "variables.yaml"
DOC_OUT = REPO_ROOT / "docs" / "registry.md"
CSV_OUT = REPO_ROOT / "docs" / "registry.csv"

sys.path.insert(0, str(REPO_ROOT))

# --------------------------------------------------------------------------
# How each adapter records its variables.
#
# `aliases`  : dict symbol mapping a key -> logical factor
# `descr`    : dict symbol mapping a key -> "Human meaning [unit]"
# `key_is`   : what the alias key actually is -
#              "native"  provider's own variable name
#              "output"  FARMWISE's output column name (native name not in code)
# `extra`    : further dicts worth recording (conversion factors, depth bands)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Shape:
    aliases: str | None = "DATA_ALIASES"
    descr: str | None = "GLOBAL_MAPPING"
    key_is: str = "native"
    extra: tuple[str, ...] = ()


SHAPES: dict[str, Shape] = {
    "cds.cds_single_levels": Shape(),
    "epa_ireland.epa_gw": Shape(key_is="output"),
    "geosphere.geosphere": Shape(),
    "imgw.imgw_api_synop_daily": Shape(key_is="output"),
    "irish_meteo.irish_ms_daily": Shape(key_is="output"),
    "soilgrids.soilgrids_call": Shape(
        extra=("CONVERSION_DIVISORS", "DEPTH_MAPPING")),
    "wetterdienst.wetterdienst_dwd": Shape(),
    "IFSGRID.IFSGRID_read": Shape(),
    "UA_sw_quality.ukrainian_surface_water": Shape(descr=None),
    "gios.gios_scraper": Shape(descr=None, key_is="output"),
    "gios_gw.gios_gw": Shape(descr=None, key_is="output"),
    "imgw_hydro.imgw_api_hydro_daily": Shape(descr=None, key_is="output"),
    "correctiv.correctiv_read": Shape(aliases=None),
    "eea.eea_read": Shape(aliases=None),
    "EuroCropV2.EuroCropV2_read": Shape(aliases=None),
    # Hub'Eau: MAPPING is native determinand -> output name; the logical factor
    # comes from the registry entry for the source, not from a per-variable map.
    "hubeau.hubeau_wq_read": Shape(aliases=None, descr="MAPPING"),
    "hubeau.hubeau_sw_quality_read": Shape(aliases=None, descr="MAPPING"),
    "hubeau.hubeau_piezo_read_vbrgm": Shape(aliases=None, descr="MAPPING"),
    # No per-variable table in code: land-cover classes / adapter absent.
    "corine.corine_read": Shape(aliases=None, descr=None),
    "egdi.egdi_read_d10": Shape(aliases=None, descr=None),
    "egdi.egdi_read_hc": Shape(aliases=None, descr=None),
}

# Fields a domain author must supply; used for the completeness report.
AUTHORED_VARIABLE_FIELDS = ("native_unit", "transformation", "reference", "notes")
AUTHORED_SOURCE_FIELDS = (
    "provider", "dataset", "spatial_support", "spatial_resolution",
    "temporal_support", "reference",
)

UNIT_RE = re.compile(r"[\[(]([^\])]+)[\])]\s*$")


@dataclass
class Row:
    """One source x native variable pair."""
    source: str
    source_short: str
    native_variable: str
    native_name_is_output: bool
    factor: str
    physical_meaning: str | None
    output_name: str | None
    output_unit: str | None
    native_unit: str | None
    spatial_support: str | None
    spatial_resolution: str | None
    spatial_type: str
    temporal_support: str | None
    temporal_resolution: str
    transformation: str | None
    within_source_aggregation: str
    harmonisation_rule: str
    source_weight: float | None
    dispatch_status: str
    provider: str | None
    dataset: str | None
    reference: str | None
    notes: str | None = None
    unjoined_tables: bool = False
    missing: tuple[str, ...] = field(default_factory=tuple)


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ModuleNotFoundError:
        raise SystemExit(
            "PyYAML is required. Install the dev extra: "
            'python -m pip install -e ".[dev]"'
        )
    if not path.exists():
        return {"sources": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {"sources": {}}
    # A lost indent under `sources:` still parses: the first source becomes a
    # top-level key and every later source nests inside it, so `sources` reads
    # as empty. Seeding from that would rewrite the file and strand all the
    # authored metadata, so refuse to continue instead.
    misplaced = [key for key in data if str(key).startswith("farmwise_api.")]
    if data.get("sources") is None or misplaced:
        raise SystemExit(
            f"{path} is malformed: every source must be indented under "
            f"'sources:'. Found at top level: {misplaced or 'nothing under sources'}. "
            "Fix the indentation before running the builder."
        )
    return data


def _dump_yaml(data: dict, path: Path) -> None:
    import yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(
        data, sort_keys=True, allow_unicode=True, default_flow_style=False,
        width=88,
    )
    header = (
        "# FARMWISE variable/source registry - AUTHORED metadata.\n"
        "#\n"
        "# This file holds only what cannot be derived from the code: native\n"
        "# units, spatial/temporal support, and literature references. Everything\n"
        "# else (variable names, output units, aggregation and harmonisation\n"
        "# rules, coverage) is read live from the adapters by\n"
        "# tools/build_registry.py and must not be duplicated here.\n"
        "#\n"
        "# `null` means NOT YET SUPPLIED. It is reported as missing, never\n"
        "# guessed. Fill these in from provider documentation and cite the\n"
        "# source in `reference`.\n"
        "#\n"
        "# New source x variable pairs are appended automatically when the code\n"
        "# gains them; run: python tools/build_registry.py\n"
    )
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(header + text)


def _iter_mapping_modules(source: str):
    """Yield the adapter module and any mapping submodules beside it."""
    yield source
    package = source.rsplit(".", 1)[0]
    try:
        parent = importlib.import_module(package)
    except Exception:
        return
    for module in pkgutil.walk_packages(parent.__path__, package + "."):
        if "mapping" in module.name.lower():
            yield module.name


def _symbol(source: str, name: str) -> dict | None:
    """Find a mapping dict for `source`, preferring the adapter module."""
    for module_name in _iter_mapping_modules(source):
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        value = getattr(module, name, None)
        if isinstance(value, dict) and value:
            return value
    return None


def split_meaning_unit(label: str) -> tuple[str, str | None]:
    """Split 'Temperature [°C]' into ('Temperature', '°C')."""
    match = UNIT_RE.search(label)
    if not match:
        return label.strip(), None
    return label[: match.start()].strip(), match.group(1).strip()


def collect_rows(authored: dict | None = None) -> list[Row]:
    from farmwise_api.adapters.mappings.data_source_mapping import (
        API_PATH_RANGES,
        DATA_SOURCE_WEIGHTS,
        DATA_TYPE_HARMONIZATION_METHODS,
        DISABLED_API_SOURCES,
        PUBLIC_SERVER_DISABLED_SOURCES,
        WITHIN_SOURCE_AGGREGATION_METHODS,
    )

    if authored is None:
        authored = _load_yaml(AUTHORED).get("sources") or {}
    rows: list[Row] = []
    all_sources = sorted(set(API_PATH_RANGES) | set(DISABLED_API_SOURCES))

    for source in all_sources:
        short = source.split("API_readers.")[-1]
        shape = SHAPES.get(short, Shape())
        ranges = API_PATH_RANGES.get(source)

        if source in DISABLED_API_SOURCES:
            status = "disabled"
        elif source in PUBLIC_SERVER_DISABLED_SOURCES:
            status = "local-only"
        else:
            status = "public"

        spatial_type = "-"
        temporal_resolution = "-"
        source_factors: list[str] = []
        if ranges:
            source_factors = list(ranges[2])
            temporal_resolution = str(ranges[3])
            spatial_type = {1: "point", 2: "grid"}.get(ranges[4], str(ranges[4]))

        aliases = _symbol(source, shape.aliases) if shape.aliases else None
        descr = _symbol(source, shape.descr) if shape.descr else None
        # Some adapters key the two tables differently - ERA5 lists request
        # names ("2m_temperature") in DATA_ALIASES but netCDF short names
        # ("t2m") in GLOBAL_MAPPING - so meaning and unit cannot be joined to
        # the variable automatically. Record it instead of showing a silent gap.
        unjoinable = bool(
            aliases and descr and not (set(aliases) & set(descr))
        )
        extras = {
            name: _symbol(source, name) for name in shape.extra
        }

        src_meta = authored.get(source) or {}
        var_meta_all = src_meta.get("variables") or {}

        keys: list[str]
        if aliases:
            keys = list(aliases)
        elif descr:
            keys = list(descr)
        else:
            keys = []

        if not keys:
            # No per-variable table in code. Emit one row per declared factor
            # so the source is still represented and its gaps are visible.
            keys = [f"({factor})" for factor in source_factors] or ["(unspecified)"]

        # Mapping tables also rename index columns (e.g. Hub'Eau's
        # date_mesure -> Timestamp); those are not observed variables.
        if descr:
            keys = [key for key in keys if descr.get(key) != "Timestamp"]

        for key in keys:
            factor = None
            if aliases:
                factor = aliases.get(key)
            if factor is None:
                if key.startswith("(") and key.endswith(")"):
                    factor = key[1:-1]
                elif len(source_factors) == 1:
                    factor = source_factors[0]
                else:
                    factor = var_meta_all.get(key, {}).get("factor")
            label = (descr or {}).get(key)
            meaning, output_unit = (
                split_meaning_unit(label) if isinstance(label, str) else (None, None)
            )
            if shape.key_is == "output" and output_unit is None:
                # e.g. 'Water level [cm]' - the key itself carries the unit
                meaning, output_unit = split_meaning_unit(key)

            var_meta = var_meta_all.get(key) or {}
            transformation = var_meta.get("transformation")
            if transformation is None and extras.get("CONVERSION_DIVISORS"):
                divisor = extras["CONVERSION_DIVISORS"].get(key)
                if divisor:
                    transformation = f"native integer / {divisor}"
            if extras.get("DEPTH_MAPPING") and extras["DEPTH_MAPPING"].get(key):
                band = extras["DEPTH_MAPPING"][key]
                transformation = ((transformation + "; ") if transformation else "") \
                    + f"layer {band}"

            # `reference` and `notes` are optional at variable level: a source
            # level citation covers the whole dataset unless a variable needs
            # its own. `transformation` is required - "none" is a valid answer
            # and distinguishes "nothing is applied" from "nobody checked".
            missing = [
                name for name in AUTHORED_VARIABLE_FIELDS
                if name not in ("notes", "reference")
                and var_meta.get(name) in (None, "")
            ]
            missing += [
                f"source.{name}" for name in AUTHORED_SOURCE_FIELDS
                if src_meta.get(name) in (None, "")
            ]

            rows.append(Row(
                source=source,
                source_short=short,
                native_variable=key,
                native_name_is_output=(shape.key_is == "output"),
                factor=factor or "(unassigned)",
                physical_meaning=meaning or var_meta.get("physical_meaning"),
                output_name=label if isinstance(label, str) else (
                    key if shape.key_is == "output" else None),
                output_unit=output_unit,
                native_unit=var_meta.get("native_unit"),
                spatial_support=src_meta.get("spatial_support"),
                spatial_resolution=src_meta.get("spatial_resolution"),
                spatial_type=spatial_type,
                temporal_support=src_meta.get("temporal_support"),
                temporal_resolution=temporal_resolution,
                transformation=transformation,
                within_source_aggregation=WITHIN_SOURCE_AGGREGATION_METHODS.get(
                    factor, WITHIN_SOURCE_AGGREGATION_METHODS.get("default", "-")),
                harmonisation_rule=DATA_TYPE_HARMONIZATION_METHODS.get(
                    factor, DATA_TYPE_HARMONIZATION_METHODS.get("default", "-")),
                source_weight=DATA_SOURCE_WEIGHTS.get(source),
                dispatch_status=status,
                provider=src_meta.get("provider"),
                dataset=src_meta.get("dataset"),
                reference=var_meta.get("reference") or src_meta.get("reference"),
                notes=var_meta.get("notes"),
                unjoined_tables=unjoinable,
                missing=tuple(sorted(set(missing))),
            ))
    return rows


LICENCES = REPO_ROOT / "DATA_LICENSES.md"

# DATA_LICENSES.md uses several spellings for the same idea.
_LABEL_ALIASES = {
    "provider": "provider",
    "providers": "provider",
    "provider/authors": "provider",
    "originator": "provider",
    "distributor": "provider",
    "dataset/resource": "dataset",
    "underlying dataset": "dataset",
    "source": "reference",
    "source/doi": "reference",
    "doi": "reference",
    "source and terms": "reference",
    "eea source": "reference",
}
_ADAPTER_LABELS = {"adapter", "adapters", "adapter/helper"}
_CODE_SPAN = re.compile(r"`([^`]+)`")
_FIELD = re.compile(r"^-\s+\*\*([^:*]+):\*\*\s*(.*)$")
_URL = re.compile(r"<(https?://[^>]+)>|(https?://\S+)")


def parse_data_licences() -> dict[str, dict[str, str]]:
    """Pull provider/dataset/source URL per adapter out of DATA_LICENSES.md.

    The licensing register is already the authoritative, human-maintained
    record of where each dataset comes from. Reusing it keeps the registry
    consistent with it and means these fields are never invented here.
    """
    if not LICENCES.exists():
        return {}
    found: dict[str, dict[str, str]] = {}
    section: dict[str, str] = {}
    adapters: list[str] = []

    def flush() -> None:
        for path in adapters:
            entry = found.setdefault(path, {})
            for key, value in section.items():
                entry.setdefault(key, value)

    # Field values wrap onto indented continuation lines, so gather each
    # `- **Label:** ...` block before interpreting it.
    blocks: list[tuple[str, str, bool]] = []   # (label, value, starts_section)
    for raw in LICENCES.read_text(encoding="utf-8").splitlines():
        if raw.startswith("### "):
            blocks.append(("", "", True))
            continue
        match = _FIELD.match(raw)
        if match:
            blocks.append((match.group(1).strip().lower(), match.group(2).strip(), False))
        elif blocks and raw.startswith((" ", "\t")) and raw.strip():
            label, value, is_section = blocks[-1]
            if not is_section:
                blocks[-1] = (label, value + " " + raw.strip(), False)

    for label, value, is_section in blocks:
        if is_section:
            flush()
            section, adapters = {}, []
            continue
        if label in _ADAPTER_LABELS:
            adapters = [
                span for span in _CODE_SPAN.findall(value)
                if span.startswith("farmwise_api.")
            ]
        elif label in _LABEL_ALIASES:
            key = _LABEL_ALIASES[label]
            if key == "reference":
                url = _URL.search(value)
                value = (url.group(1) or url.group(2)) if url else value
            value = _CODE_SPAN.sub(r"\1", value).strip().rstrip(".")
            if value:
                section.setdefault(key, value)
    flush()
    return found


def seed_authored(rows: list[Row]) -> dict:
    """Add placeholders for any pair not yet present in the YAML.

    Provider, dataset and source reference are pre-filled from
    DATA_LICENSES.md when it records them; everything else starts as null so
    that an unsupplied value is visibly unsupplied rather than plausible.
    """
    data = _load_yaml(AUTHORED)
    sources = data.setdefault("sources", {}) or {}
    data["sources"] = sources
    licences = parse_data_licences()

    # Drop entries for sources the code no longer knows about, so the authored
    # file tracks the adapters rather than accumulating history. Removals are
    # announced because they discard authored text (git keeps the old copy).
    live = {row.source for row in rows}
    for gone in sorted(set(sources) - live):
        del sources[gone]
        print(f"removed registry entry for retired source: {gone}")

    # Likewise for variables a source no longer returns, e.g. after a column
    # rename - otherwise the authored metadata sits under a dead key.
    live_variables: dict[str, set[str]] = {}
    for row in rows:
        live_variables.setdefault(row.source, set()).add(row.native_variable)
    for source, entry in sources.items():
        variables = (entry or {}).get("variables") or {}
        for gone in sorted(set(variables) - live_variables.get(source, set())):
            del variables[gone]
            print(f"removed registry entry for retired variable: {source} / {gone}")

    for row in rows:
        entry = sources.setdefault(row.source, {})
        from_licence = licences.get(row.source, {})
        for name in AUTHORED_SOURCE_FIELDS:
            entry.setdefault(name, None)
            if entry[name] is None and name in from_licence:
                entry[name] = from_licence[name]
        variables = entry.setdefault("variables", {})
        var = variables.setdefault(row.native_variable, {})
        for name in AUTHORED_VARIABLE_FIELDS:
            var.setdefault(name, None)
    return data


CSV_COLUMNS = [
    "source", "source_short", "native_variable", "factor", "physical_meaning",
    "native_unit", "output_name", "output_unit", "spatial_support",
    "spatial_resolution", "spatial_type", "temporal_support",
    "temporal_resolution", "transformation", "within_source_aggregation",
    "harmonisation_rule", "source_weight", "dispatch_status", "provider",
    "dataset", "reference", "notes",
]


def render_csv(rows: list[Row]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    for row in sorted(rows, key=lambda r: (r.factor, r.source_short, r.native_variable)):
        record = asdict(row)
        writer.writerow({k: ("" if record[k] is None else record[k])
                         for k in CSV_COLUMNS})
    return buffer.getvalue()


def _cell(value) -> str:
    if value is None or value == "":
        return "_not supplied_"
    return str(value).replace("|", "\\|")


def render_markdown(rows: list[Row]) -> str:
    from collections import defaultdict

    by_factor: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        by_factor[row.factor].append(row)

    total = len(rows)
    complete = sum(1 for r in rows if not r.missing)
    sources = sorted({r.source for r in rows})

    out: list[str] = []
    out.append("# FARMWISE variable and source registry")
    out.append("")
    out.append(
        "Generated by `tools/build_registry.py` - **do not edit**. Variable "
        "names, output units, coverage, aggregation and harmonisation rules "
        "are read live from the adapters, so this document cannot drift from "
        "the dispatch behaviour it describes. Native units, spatial/temporal "
        "support and references come from "
        "[`registry/variables.yaml`](../registry/variables.yaml); fields shown "
        "as _not supplied_ have not been filled in yet."
    )
    out.append("")
    out.append(
        f"**{total}** source x variable pairs across **{len(sources)}** sources "
        f"and **{len(by_factor)}** logical variables. "
        f"**{complete}** pairs have complete authored metadata."
    )
    out.append("")
    out.append("## Contents")
    out.append("")
    for factor in sorted(by_factor):
        anchor = re.sub(r"[^a-z0-9]+", "-", factor.lower()).strip("-")
        out.append(f"- [{factor}](#{anchor}) — {len(by_factor[factor])} pairs")
    out.append("")

    for factor in sorted(by_factor):
        group = sorted(by_factor[factor], key=lambda r: (r.source_short, r.native_variable))
        out.append(f"## {factor}")
        out.append("")
        first = group[0]
        out.append(
            f"Within-source aggregation: `{first.within_source_aggregation}` · "
            f"cross-source harmonisation: `{first.harmonisation_rule}`"
        )
        out.append("")
        out.append(
            "| Source | Native variable | Physical meaning | Native unit | "
            "Output unit | Spatial support | Temporal support | Transformation | "
            "Weight | Status | Reference |"
        )
        out.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for row in group:
            spatial = row.spatial_resolution or row.spatial_support
            spatial = f"{spatial} ({row.spatial_type})" if spatial else row.spatial_type
            temporal = row.temporal_support or row.temporal_resolution
            native = row.native_variable
            if row.native_name_is_output:
                native = f"{native} ⁽ᵒ⁾"
            out.append(
                "| `{src}` | `{nat}` | {mean} | {nu} | {ou} | {sp} | {tp} | "
                "{tr} | {w} | {st} | {ref} |".format(
                    src=row.source_short, nat=native,
                    mean=_cell(row.physical_meaning), nu=_cell(row.native_unit),
                    ou=_cell(row.output_unit), sp=_cell(spatial),
                    tp=_cell(temporal), tr=_cell(row.transformation),
                    w="—" if row.source_weight is None else row.source_weight,
                    st=row.dispatch_status, ref=_cell(row.reference),
                )
            )
        out.append("")

    out.append("---")
    out.append("")
    out.append(
        "⁽ᵒ⁾ the code records only FARMWISE's output column name for this "
        "variable; the provider's own name has to be supplied in "
        "`registry/variables.yaml`."
    )
    out.append("")
    out.append("## Completeness")
    out.append("")
    out.append("| Source | Pairs | Complete | Missing fields |")
    out.append("|---|---|---|---|")
    by_source: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        by_source[row.source_short].append(row)
    for short in sorted(by_source):
        group = by_source[short]
        done = sum(1 for r in group if not r.missing)
        gaps = sorted({m for r in group for m in r.missing})
        out.append(
            f"| `{short}` | {len(group)} | {done}/{len(group)} | "
            f"{', '.join(f'`{g}`' for g in gaps) if gaps else '—'} |"
        )
    out.append("")

    unjoined = sorted({r.source_short for r in rows if r.unjoined_tables})
    if unjoined:
        out.append("### Mapping tables that do not join")
        out.append("")
        out.append(
            "In these adapters the variable-alias table and the "
            "description/unit table are keyed differently, so the physical "
            "meaning and output unit cannot be attached to the native variable "
            "automatically. ERA5 is the example: `DATA_ALIASES` lists request "
            "names (`2m_temperature`) while `GLOBAL_MAPPING` lists netCDF short "
            "names (`t2m`). Either align the keys in the adapter's mapping "
            "module, or supply `physical_meaning` and `native_unit` per "
            "variable in `registry/variables.yaml`."
        )
        out.append("")
        for short in unjoined:
            out.append(f"- `{short}`")
        out.append("")
    return "\n".join(out) + "\n"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail if the generated files are out of date")
    parser.add_argument("--report", action="store_true",
                        help="print a completeness summary and exit")
    args = parser.parse_args()

    # Seeding can add licence-derived values, so render from the *seeded*
    # state rather than from whatever the file happened to hold on entry -
    # otherwise the first run emits documentation that the next run disagrees
    # with, and --check never settles.
    seeded = seed_authored(collect_rows())
    rows = collect_rows(authored=seeded.get("sources") or {})
    markdown = render_markdown(rows)
    csv_text = render_csv(rows)

    if args.report:
        total, complete = len(rows), sum(1 for r in rows if not r.missing)
        print(f"{total} source x variable pairs, {complete} with complete metadata")
        gaps: dict[str, int] = {}
        for row in rows:
            for name in row.missing:
                gaps[name] = gaps.get(name, 0) + 1
        for name, count in sorted(gaps.items(), key=lambda kv: -kv[1]):
            print(f"  {count:4d} missing {name}")
        return

    if args.check:
        problems = []
        for path, text in ((DOC_OUT, markdown), (CSV_OUT, csv_text)):
            if not path.exists():
                problems.append(f"{path.relative_to(REPO_ROOT)} is missing")
            elif path.read_text(encoding="utf-8") != text:
                problems.append(f"{path.relative_to(REPO_ROOT)} is out of date")
        if seeded != _load_yaml(AUTHORED):
            problems.append(
                f"{AUTHORED.relative_to(REPO_ROOT)} is missing entries for "
                "source/variable pairs present in the code"
            )
        if problems:
            raise SystemExit(
                "; ".join(problems) + " - run: python tools/build_registry.py"
            )
        print("registry is up to date")
        return

    _dump_yaml(seeded, AUTHORED)
    write(DOC_OUT, markdown)
    write(CSV_OUT, csv_text)
    complete = sum(1 for r in rows if not r.missing)
    print(f"wrote {DOC_OUT.relative_to(REPO_ROOT)} and "
          f"{CSV_OUT.relative_to(REPO_ROOT)}: {len(rows)} pairs, "
          f"{complete} with complete authored metadata")
    print(f"seeded {AUTHORED.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()

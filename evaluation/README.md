# FARMWISE empirical data collection

The Python scripts in this directory collect raw empirical data. Analysis,
statistics, tables, and figures are prepared separately in the evaluation
notebooks.

## Running the collection

Run the standard collection from the repository root:

```powershell
python -m evaluation.collect_empirical
```

or:

```powershell
python -m evaluation.run_all
```

For the permitted local academic-research evaluation, set the file-level
option near the top of `evaluation/collect_empirical.py`:

```python
INCLUDE_IMGW_RESEARCH = True
```

Running `collect_empirical.py` directly from an IDE then includes IMGW without
command-line parameters. The setting does not enable IMGW in the public
server, and IMGW station files and downloaded source data remain excluded from
wheels and source distributions. `run_all.py` is only a short convenience
entry point; it does not calculate metrics or generate figures.

The scenario definitions are kept in `evaluation/scenarios.py`:

- `REQUEST_SCENARIOS` exercises coverage pre-check and ordinary requests;
- `CROSS_SOURCE_SCENARIOS` collects separate, non-harmonized source values,
  including an explicit IMGW--ERA5 comparison over central Poland;
- `LIVE_SCALING_SCENARIOS` varies S2 level, bounding-box area, factor count,
  and requested duration. The duration sweep covers 1, 7, 30, and 90 inclusive
  days while holding the other request parameters fixed.

Collection settings are explicit constants near the top of
`evaluation/collect_empirical.py`:

```python
OUTPUT_DIR = Path(__file__).resolve().parent / "empirical_input"
SCALING_REPEATS = 3
REQUEST_TIMEOUT_SECONDS = 600
```

Change those constants or the scenario lists directly when a different
experiment is needed.

## Raw output files

The collector writes the notebook inputs under `evaluation/empirical_input/`:

```text
empirical_input/
  empirical_runs.json
  cross_source_observations_live.csv
  quality/
    <collection-timestamp>/
      <request-id>_<source>.json
```

`empirical_runs.json` contains one record for every request, cross-source run,
and live-scaling repeat. Records include request parameters, run type, status,
wall time, peak Python-traced memory, returned data sizes, coverage-precheck
decisions, and per-adapter dispatch timing. Cross-source records also identify
required, observed, and missing sources and count exact timestamp--S2
cell--variable keys shared by all required sources. `comparison_ready` is true
only when both required sources returned data and at least one such key exists.

`cross_source_observations_live.csv` contains only the scenarios declared in
`CROSS_SOURCE_SCENARIOS`. Its columns are:

```text
timestamp, cell, variable, source, value, scenario
```

The timestamped directory recorded as `quality_report_dir` in
`empirical_runs.json` contains the per-source quality reports produced during
that collection. Reports from earlier runs remain available, but are not read
into the current notebook analysis.

Evaluation procedure is implemented in the jupyter notebook file called "Evaluation
summariser". It produces all the tables and plots used to evaluate the FARMWISE-API.

## External access and licensing

ERA5 collection requires an ECMWF/CDS account, acceptance of the dataset
terms, and a configured `.cdsapirc`. The FARMWISE server login is unrelated to
CDS authentication.

IMGW may be used locally for permitted academic research according to the
terms recorded in `DATA_LICENSES.md`. Research outputs must identify IMGW-PIB
as the source and state that the observations were processed. Do not bundle
IMGW station files or downloaded source datasets in the Python package; the
packaging manifest explicitly excludes them. Public-server dispatch remains
disabled.

The notebooks are intentionally not executed or modified by either collection
entry point.

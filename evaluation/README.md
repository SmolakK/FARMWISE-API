# FARMWISE empirical data collection

The Python scripts in this directory collect raw empirical data. Analysis,
statistics, tables, and figures are prepared separately in the evaluation
notebooks.

## Running the collection

Run either entry point from the repository root:

```powershell
python -m evaluation.collect_empirical
```

or:

```powershell
python -m evaluation.run_all
```

Both commands execute the same collection. There are no command-line
arguments or parser. `run_all.py` is only a short convenience entry point; it
does not calculate metrics or generate figures.

The scenario definitions are kept in `evaluation/scenarios.py`:

- `REQUEST_SCENARIOS` exercises coverage pre-check and ordinary requests;
- `CROSS_SOURCE_SCENARIOS` collects separate, non-harmonized source values;
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
    <request-id>_<source>.json
```

`empirical_runs.json` contains one record for every request, cross-source run,
and live-scaling repeat. Records include request parameters, run type, status,
wall time, peak Python-traced memory, returned data sizes, coverage-precheck
decisions, and per-adapter dispatch timing.

`cross_source_observations_live.csv` contains only the scenarios declared in
`CROSS_SOURCE_SCENARIOS`. Its columns are:

```text
timestamp, cell, variable, source, value, scenario
```

The files under `quality/` are the per-source quality reports produced during
all successful requests. Existing files in this directory are not removed by
a new run, while the JSON run bundle and cross-source CSV are overwritten.
Use a clean output directory when a notebook must represent exactly one
collection.

Evaluation procedure is implemented in the jupyter notebook file called "Evaluation
summariser". It produces all the tables and plots used to evaluate the FARMWISE-API.

## External access and licensing

ERA5 collection requires an ECMWF/CDS account, acceptance of the dataset
terms, and a configured `.cdsapirc`. The FARMWISE server login is unrelated to
CDS authentication.

IMGW may be used only according to the private, non-commercial policy recorded
in `DATA_LICENSES.md`. Do not publish raw or derived IMGW observations without
separate permission. The collector retains the safeguard that rejects IMGW
observations written into the repository.

The notebooks are intentionally not executed or modified by either collection
entry point.

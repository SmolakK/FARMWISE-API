# FARMWISE empirical evaluation

The evaluation is split into two layers that never mix:

| Layer | Files | Contacts live APIs | Computes statistics |
|---|---|---|---|
| Collection | `scenarios.py`, `collect_empirical.py`, `workload.py`, `run_instrumentation.py`, `coverage_baseline.py`, `collect_cross_source.py` | yes | no |
| Analysis | `analysis.py`, `Evaluation summariser.ipynb` | no | yes |

Collection writes **frozen** raw outputs. Analysis reads only those files, so
every published table and figure can be regenerated without querying an
upstream service again.

## Running a collection

From the repository root, with the evaluation extra installed:

```powershell
python -m pip install -e ".[evaluation]"
python -m evaluation.collect_empirical
```

`python -m evaluation.run_all` runs the same collection but does not
acknowledge the IMGW research-use terms (see below). Calling `collect()`
directly from an IDE or notebook does not acknowledge them either; the
collector prints a warning when an IMGW scenario would run without IMGW.

To collect only some experiments into a separate collection, for example to
repeat the cross-source experiment with IMGW enabled:

```powershell
python -m evaluation.collect_empirical --experiments cross-source --collection-id <new-id>
```

The analysis can then combine two collections without modifying either: set
`COLLECTION_ID` to the full collection and `CROSS_SOURCE_COLLECTION_ID` to the
cross-source collection in the notebook (or pass `cross_source_dir` to
`analysis.load_collection`). Cross-source runs, dispatch records and
observations are then taken from the second collection.

Every run creates a new directory and refuses to overwrite an existing one:

```text
evaluation/empirical_input/<collection-id>/      # UTC start time, e.g. 20261001T080000Z
  manifest.json                   provenance and complete configuration
  empirical_runs.json             one record per measured request
  cross_source_observations.csv   separate-source values for agreement analysis
  quality/                        per-source quality reports
```

To analyse it, open the notebook and set `COLLECTION_ID` to that directory
name. **Pin `COLLECTION_ID` for anything reported in the paper** and keep the
directory under version control (subject to the IMGW restriction below).

The files directly under `empirical_input/` (`empirical_runs.json`,
`cross_source_observations_live.csv`, `quality/<timestamp>/`) come from the
collection design before this revision. They are kept unchanged for
traceability but are not read by the current notebook.

## Experimental design

All settings are constants in `evaluation/scenarios.py`, and the complete
configuration is saved into every `manifest.json`.

### 1. Scaling

The scaling experiment measures FARMWISE's own work: processing, spatial and
temporal harmonisation and aggregation of the retrieved data.

* **One dimension at a time.** Three sweeps around a shared base request over
  central Ireland (1° × 1° box centred on 53.4° N, 8.2° W, S2 level 10, 7 days
  from 2018-01-01):
  * S2 level: 6, 8, 10, 12, 14;
  * spatial extent: square boxes 0.25°, 0.5°, 1°, 2°, 3° wide (wider boxes
    would leave the source's coverage);
  * temporal extent: 1, 7, 14, 30, 60, 90 inclusive days, all within 2018.
* **Fixed factor set, single backend.** Every sweep requests daily
  `precipitation` from the Met Éireann 1 km rainfall grid. ERA5 also covers
  precipitation over Ireland and is excluded through `disabled_sources`
  (recorded per run under `settings.disabled_sources`), so every request is
  served by the same single adapter.
* **Why this workload.** The grid is dense, so the number of returned values
  grows with area, S2 level and duration. A station-based source returns a few
  hundred values at most and barely exercises the processing being measured.
* **No factor-count sweep.** Requesting more factors also adds adapters, data
  models and processing steps, so a factor-count sweep confounds workload size
  with backend differences. It was removed and not replaced, because FARMWISE
  has no backend that serves several factors under otherwise identical
  conditions.
* **Quality assessment off.** Scaling runs use `assess_quality=False` and
  `persist_quality_reports=False`; the quality cost is measured separately
  (experiment 3).
* **Repetition.** `SCALING_REPEATS` (15) measured repeats per scenario. One
  warm-up per scenario runs first and is excluded from `runs` (it is listed
  under `warmup_runs`). Measured runs are executed in an order shuffled with
  `RANDOM_SEED = 42`.

The Met Éireann adapter caches each downloaded annual grid file, and all
durations lie within one year. After the warm-ups, measured runs therefore
read cached input: they describe FARMWISE's processing in a warm process, not
end-to-end latency including the upstream download. Live upstream behaviour is
part of the coverage and cross-source experiments.

Before a full collection, time the largest scenarios once (S2 level 14, the 3°
box, 90 days): dense grids at high S2 levels can produce very large results.

### 2. Cross-source agreement

National sources are compared with ERA5 in four regions, each in four
seasonal months of 2018 (January, April, July, October), at S2 level 10:

| Region | Sources | Variables |
|---|---|---|
| central Germany | DWD vs ERA5 | temperature, precipitation |
| eastern Austria | GeoSphere vs ERA5 | temperature, precipitation |
| central Ireland | Met Éireann vs ERA5 | precipitation |
| central Poland | IMGW vs ERA5 | temperature, precipitation |

Runs use `separate_api=True`, so each source's values are kept apart. They are
single observational collections, not timings, and run with quality
assessment on so that their quality reports are preserved.

This is reported as **cross-source agreement**, not accuracy: ERA5 is a
reanalysis, and neither it nor the national products is treated as ground
truth.

### 3. Quality-assessment overhead

The largest request of the spatial-extent sweep (3° box, S2 level 10, 7 days,
Met Éireann only) is run 10 times with quality assessment off and 10 times
with assessment and report persistence on (the server's default), after one
warm-up per mode, in shuffled order. A large request is used because on a
small one the assessment cost was indistinguishable from run-to-run noise.
This quantifies quality-control overhead independently of the scaling results.

### 4. Coverage pre-check

The eight coverage scenarios (six positive, one outside every groundwater
source's spatial coverage, one before every source's temporal coverage) each
run in two routing modes, 3 measured repeats each after one warm-up per
scenario and mode, interleaved in shuffled order:

* `precheck` - FARMWISE as shipped: a source is called only if its registry
  entry overlaps the request in space, time and factor;
* `factor-only` - baseline: every enabled source providing a requested factor
  is called, regardless of spatial and temporal coverage.

The baseline is implemented in `coverage_baseline.py` by replacing the routing
decision `read_data` uses, inside the evaluation process only; the library is
not modified. Disabled sources (licence restrictions, broken upstreams) stay
excluded in both modes. Quality assessment is off in both modes.

The spatial negative case uses a box at 11.5-12.5° E. An earlier box at
9.5-10.5° E overlapped the Hub'Eau (France) coverage box, which ends at
9.56° E, so Hub'Eau was dispatched and the case was not a true negative.

Adapter calls avoided are deterministic and are the primary result. Total
runtime differences between the modes are secondary: for scenarios involving
ERA5, CDS queueing can dominate them.

## What is recorded

### Per run (`empirical_runs.json` → `runs[]`)

* experiment, scenario, dimension, input value, mode, repeat, UTC start time;
* full request and effective settings (`assess_quality`, `separate_api`,
  routing mode, timeout);
* `request_wall_seconds`, measured around the `read_data` call only;
* `workload`:
  * requested: `area_km2` (spherical Earth), `requested_s2_cells` (cells at
    the requested level whose covering intersects the box), `duration_days`,
    `requested_factors`, box `width_deg`/`height_deg` (scenario metadata);
  * returned: `returned_s2_cells`, `returned_values` (non-missing values),
    `returned_rows`, `returned_columns`, `returned_factors`;
* `memory` (see below);
* `planned_coverage`: configured, enabled and factor-eligible sources, sources
  the pre-check dispatches, `requests_avoided_vs_factor_only`, and how many
  were rejected on spatial or temporal grounds;
* `coverage_precheck` (FARMWISE's own record, including `precheck_seconds`
  and the per-source decisions), `dispatch` (per adapter call: status and wall
  time), `source_wall_seconds`, `dispatch_status_counts`;
* cross-source runs: `cross_source_comparison` (required, observed and
  missing sources; number of shared keys).

Workload and planned coverage are computed before the timed section.

Note that FARMWISE's own `coverage_precheck.requests_avoided` counts every
configured source that was not dispatched, including sources that do not
provide the requested factor at all. The evaluation instead reports
`requests_avoided_vs_factor_only`, which counts only calls a factor-aware
system would otherwise have made.

### Memory

* **`peak_rss_mb` (primary)**: peak resident set size of the process during
  the request, sampled every 50 ms on a background thread with `psutil`. RSS
  includes native allocations by pandas, NumPy, GDAL/rasterio and other
  extensions, which `tracemalloc` does not fully see.
* `peak_rss_increase_mb`: peak RSS minus the RSS measured just before the
  request (after a garbage-collection pass).
* `peak_traced_memory_mb` (secondary): `tracemalloc` peak of Python-allocator
  memory.

Limitations: a peak shorter than the sampling interval can be missed; RSS
belongs to the whole long-running process, so memory retained by the allocator
from earlier runs is included in the absolute peak and can reduce the measured
increase. The shuffled execution order spreads this history effect across
scenarios instead of letting it follow one sweep. Without `psutil` installed
the RSS fields are `null` and only the `tracemalloc` peak is recorded.

### Provenance (`manifest.json`)

* Git commit SHA, branch, and whether tracked files had uncommitted changes
  (with their paths);
* Python version and implementation, FARMWISE version, all installed
  distributions and versions, the lockfile name and its SHA-256;
* OS, platform, machine, CPU model, logical and physical core counts, total RAM;
* collection start and finish time (UTC), collection id;
* random seed, the complete evaluation configuration, and the exact execution
  order (including warm-ups).

No hostnames, user names, file-system paths or environment variables are
recorded. The collection runs in whatever environment is active; the
lockfile digest identifies the locked dependency set, and the installed
distribution list records what was actually used.

## Analysis (`analysis.py`, notebook)

* **Runtime and memory** are summarised per scenario by median, quartiles and
  IQR, with a percentile-bootstrap 95 % confidence interval for the median
  (2000 resamples, fixed seed). Mean and standard deviation are included for
  reference only, because live-API latency is heavy-tailed.
* **Scaling** relates runtime and peak RSS to the actual workload (requested
  and returned S2 cells, returned values, requested days) rather than the
  nominal S2 level or box width. `scaling_fit` gives a descriptive log-log
  slope; it is not a hypothesis test. Failed runs are excluded from the
  summaries and counted in `failed_runs`.
* **Quality overhead**: median runtime with assessment on minus off, with a
  bootstrap CI of the difference in medians.
* **Coverage pre-check**: per scenario and mode, dispatched sources,
  requests avoided relative to factor-only routing, empty/failed/timed-out
  adapter calls, pre-check overhead (absolute and as a share of the request),
  and median runtime saved with a bootstrap CI.
* **Cross-source agreement**: values are paired strictly on scenario,
  timestamp, S2 cell and variable, with no interpolation or time shift.
  Differences are `national - ERA5`. Per region, variable and season (and
  pooled over seasons): number of pairs and cells, mean and median bias, MAE,
  RMSE, Pearson r and Spearman ρ. For precipitation additionally:
  * wet-day agreement at ≥ 1 mm/day (the ETCCDI wet-day threshold) as a 2 × 2
    contingency table, proportion of agreement and Cohen's κ;
  * accumulated totals per S2 cell over the days on which both sources have
    values, reported as source totals and median absolute and relative
    per-cell differences.

  National daily precipitation totals and ERA5 daily totals (summed over UTC
  days by the adapter) can use different daily accumulation windows. This is
  not corrected and contributes to the disagreement.

Figures are written to `evaluation/analysis_output/<collection-id>/`.

## External access and licensing

ERA5 collection requires an ECMWF/CDS account, acceptance of the dataset
terms, and a configured `.cdsapirc`. The FARMWISE server login is unrelated to
CDS authentication.

IMGW may be used locally for permitted academic research according to the
terms recorded in `DATA_LICENSES.md`. `collect_empirical.py` opts in through
the file-level constant `INCLUDE_IMGW_RESEARCH = True`, scoped to the
collection run; the public server keeps IMGW disabled. Research outputs must
identify IMGW-PIB as the source and state that the observations were
processed; the attribution is stored in `empirical_runs.json`. Do not bundle
IMGW station files or downloaded source datasets in the Python package, and
check the IMGW terms before publishing row-level IMGW values from
`cross_source_observations.csv`.

The collectors never execute or modify the notebook.

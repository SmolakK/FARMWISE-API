# FARMWISE evaluation suite

This directory contains reproducible experiments for the framework's quality,
efficiency, scaling, and cross-source agreement claims. Install the additional
plotting dependency with:

```powershell
python -m pip install -e ".[evaluation]"
```

## Empirical evaluation

The default evaluation is deliberately split into collection and analysis.
Collection calls the enabled live adapters, persists per-source quality
reports, and records the real dispatch metadata used by the analysis:

```powershell
python -m evaluation.collect_empirical
python -m evaluation.run_all --controlled-scaling-repeats 5
```

In PyCharm, one Run configuration can execute `evaluation/run_all.py` with
the script parameter `--collect`. The first run collects live inputs and then
analyses them; later runs may omit `--collect` to reuse those inputs.

Both commands use the private FARMWISE cache by default. This is required when
IMGW observations are present and keeps downloaded or derived restricted data
out of the repository. `run_all` has no synthetic fallback: it fails if the
live run bundle, overlapping observations, or quality reports are missing.
Configure the CDS/ERA5 credentials described in section 2.4 before collection;
otherwise there may be no ERA5 reference pairs and the analysis will stop.
IMGW remains optional and may be enabled only for acknowledged private,
non-commercial local use.

To start with a smaller live collection, select scenarios explicitly:

```powershell
python -m evaluation.collect_empirical `
  --scenario poland-temperature `
  --scenario germany-meteo
```

The command displays an overall stage bar plus request-level and scaling-case
bars in terminals such as the PyCharm Run console. Pass `--no-progress` when
machine-readable or CI logs should not contain progress output.

The resulting manifest is labelled
`empirical-live-with-controlled-supplement`. Coverage time saved is a
conservative lower-bound estimate based only on median source dispatch times
actually observed in other collected scenarios; its latency coverage is
reported explicitly.

## Offline smoke controls

Synthetic data remain useful for verifying the evaluation code itself, but
they are now behind an explicitly named command:

```powershell
python -m evaluation.run_smoke
```

This regenerates CSV/JSON logs under `evaluation/logs/` and four PNG figures
under `evaluation/figures/`:

1. `coverage_precheck.png`
2. `scaling_behaviour.png` (latency and memory panels)
3. `cross_source_agreement.png`
4. `cross_source_disagreement.png`

The committed outputs are deterministic offline controls. They demonstrate
that the measurement and plotting pipeline works, but they are deliberately
labelled **offline-smoke-test** in `logs/manifest.json`. Do not cite their
synthetic timing or agreement values as empirical findings.
`logs/quality_report_synthetic.json` is likewise a labelled control for the
per-source quality pipeline.

## 2.1 Per-source quality reports

`core.main_call.read_data` now assesses every successful source before
harmonization. Reports include:

- S2 completeness;
- overall and per-factor missing-value rates;
- missing-day rate;
- temporal delay and cut-short duration;
- returned-factor completeness;
- factor-specific implausible-value rates.

The reports are returned in `result["metadata"]["quality_reports"]` and, by
default, persisted to the FARMWISE cache directory. For an experiment-specific
directory:

```python
result = await read_data(
    ...,
    quality_report_dir="evaluation/logs/quality",
)
```

Set `persist_quality_reports=False` only when persistence is not wanted.
For latency-sensitive production calls, set `assess_quality=False`; this skips
both assessment and persistence. S2 coverings are cached, and enabled reports
are evaluated concurrently with subsequent adapter calls.

## 2.2 Coverage pre-check

The live `read_data` metadata now contains:

```text
metadata.coverage_precheck.candidate_sources
metadata.coverage_precheck.dispatched_sources
metadata.coverage_precheck.requests_avoided
metadata.coverage_precheck.precheck_seconds
metadata.dispatch[*].wall_seconds
```

The empirical collector varies country, S2 level, factor set, and time window
and records real `metadata.dispatch[*].wall_seconds` values. The standalone
projection command requires an observed latency profile:

```powershell
python -m evaluation.coverage_precheck `
  --latency-profile evaluation/logs/observed_source_latencies.json
```

The profile is a JSON object keyed by the full adapter module path, with median
observed latency in seconds as its value. Profile-based runs calculate a
projection and do not repeat waits. A simulated control is possible only with
the explicit `--synthetic-smoke` flag.

## 2.3 Scaling behaviour

The empirical collector runs 12 live scaling cases for each repeat: four S2
levels, four bounding-box areas, and four factor counts. Only the declared
dimension changes within each sweep. Configure repeat count during collection:

```powershell
python -m evaluation.collect_empirical --live-scaling-repeats 5
python -m evaluation.run_all
```

`logs/scaling_live.csv` contains end-to-end `read_data` wall time, dispatch
time, returned cells and values, successful source count, latency quartiles,
and peak traced memory. `figures/scaling_behaviour.png` is generated from this
live table.

The controlled algorithmic microbenchmark remains available separately:

```powershell
python -m evaluation.scaling --repeats 5
```

It performs a warm-up and then measures S2 covering, construction of two dense
controlled source frames, and harmonization. Its output is explicitly named
`scaling_controlled.csv`; the empirical runner includes it only as a separately
labelled supplement and writes `figures/scaling_controlled.png`.

## 2.4 Cross-source agreement

Live collection includes ERA5 and therefore requires an ECMWF/CDS account,
manual acceptance of the ERA5 dataset terms, and a personal API token in
`.cdsapirc`. Configure it using the
[official CDS API instructions](https://cds.climate.copernicus.eu/how-to-api)
before running the collector. The FARMWISE server login is not a CDS login.

Collect live overlapping data without harmonization:

```powershell
python -m evaluation.collect_cross_source `
  --country Poland `
  --level 10 `
  --time-from 2018-01-01 `
  --time-to 2018-03-31
```

When IMGW is enabled for permitted private, non-commercial research, the live
collector writes by default to
`FARMWISE_CACHE_DIR/evaluation/cross_source_observations_live.csv`, outside the
repository. It refuses to write live IMGW rows anywhere under the project
root. Keep subsequent statistics and figures in the same private location;
do not commit or publish them without a separate IMGW-PIB agreement.

Then calculate aligned cell-day statistics and regenerate figures:

```powershell
python -m evaluation.cross_source_agreement `
  --input <private-cache-path>/cross_source_observations_live.csv `
  --output <private-cache-path>/cross_source_agreement.csv `
  --differences-output <private-cache-path>/cross_source_differences.csv
python -m evaluation.plots
```

Omitting `--input` is no longer allowed unless `--synthetic-smoke` is supplied
explicitly.

Agreement is calculated only after an inner join on timestamp, S2 cell, and
logical variable. The output reports sample count, bias, MAE, RMSE, and Pearson
correlation for each ERA5–observational-source pair. Always inspect sample
counts and coverage reports before interpreting agreement.

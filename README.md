# FARMWISE API

[![CI](https://github.com/SmolakK/FARMWISE-API/actions/workflows/ci.yml/badge.svg)](https://github.com/SmolakK/FARMWISE-API/actions/workflows/ci.yml)

FARMWISE-API is a unified framework for accessing, standardising, and harmonising European agricultural and environmental data. It is developed within the FARMWISE project (https://farmwise-project.eu/) to support research and decision-making for sustainable agriculture. FARMWISE-API implements a common data processing layer together with an orchestration module that invokes a series of independent adapters that reach out to multiple external data services to gather data. Returned data are standardised and organised into a consistent geospatial format. Users request data via a unified data request model, which specifies area and time period, and requested factors such as temperature and precipitation. The platform can be used as either a Python library or an HTTP service.

FARMWISE has two usage modes:

- as a local Python library through `farmwise_api`;
- as an HTTP service through `farmwise_api.server`.

A request describes an area (a country or a bounding box), a date range, an S2 cell level, and one or more factors. FARMWISE selects matching adapters, downloads their data, normalises it to S2 cells, and returns the combined data with source metadata and an optional HTML map developed for quick data investigation.

## Quick start

Install the library:

```bash
pip install "farmwise-api==0.1.0rc1"
```

Then request data:

```
import asyncio
from farmwise_api import read_data

result = asyncio.run(
    read_data(
        country="Ireland",
        level=8,
        time_from="2018-01-01",
        time_to="2018-01-07",
        factors=["precipitation"],
    )
)

data = result["data"]
metadata = result["metadata"]
```

## Project layout

```text
farmwise_api/
  adapters/
    API_readers/     integrations with individual data providers
    mappings/        adapter registry and supported ranges
  core/
    main_call.py     adapter selection and result aggregation
    utils/           spatial, interpolation, mapping, and data-path helpers
  server/
    main.py          FastAPI application
    routers/         authentication, frontend, and data endpoints
    static/          packaged frontend assets
  cli.py             console and lazy ASGI entry point
evaluation/          empirical collection and analysis tools
tests/               unit and integration tests
```

All installed modules are contained under the `farmwise_api` namespace to avoid collisions with unrelated Python packages. Development commands should be run from the repository root.

## Installation

Python 3.11 or newer is required.

The library is now in the pre-release stage.
Pre-releases are not installed by default, so pin the version:

```
pip install "farmwise-api[server]==0.1.0rc1"
```

Library only, without the server extra:
```
pip install "farmwise-api==0.1.0rc1"
```
For development from a repository checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[server,dev]"
```

The Hub'Eau helper library is vendored privately under `farmwise_api._vendor.hubeaupyutils` and retains its MIT licence. It does not install a separate top-level `hubeaupyutils` package.

## Configuration

FARMWISE reads every secret from the process environment. The `.env` files described below are a convenience for local development only: they are loaded without overriding variables that are already set, so a deployment supplies the same settings directly and needs no credential file on disk at all.

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY`, `ALGORITHM` | JWT signing |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USER`, `EMAIL_PASS` | SMTP delivery, only when email is enabled |
| `PUBLIC_BASE_URL` | host and optional port, no URL scheme, e.g. `localhost:8000` |
| `FARMWISE_DATABASE_URL` | SQLAlchemy URL for the user database |
| `FARMWISE_CACHE_DIR`, `FARMWISE_DATA_DIR` | writable cache and bundled-data locations |
| `FARMWISE_FIX_PROJ_DATA` | set to `0` to keep the host's PROJ configuration (see below) |

### A stale PROJ database on the host

If the machine also carries a conda, OSGeo4W or PostGIS installation, its `PROJ_LIB` variable often points at an older `proj.db` than GDAL accepts:

```text
proj_create_from_database: ...\proj.db contains DATABASE.LAYOUT.VERSION.MINOR
= 2 whereas a number >= 6 is expected. It comes from another PROJ installation.
```

Every coordinate lookup then fails — `CRS.from_epsg(4326)` raises — so reprojection and the raster adapters stop working, and GDAL repeats the message on each attempt. At import, FARMWISE reads the configured database's
layout version directly and, if GDAL would reject it, points `PROJ_DATA` at the PROJ data shipped with rasterio for that process only. `PROJ_DATA` takes precedence over the legacy `PROJ_LIB` in PROJ 9+, so the host variable is left untouched and other software on the machine is unaffected. One warning is logged explaining what happened.

The permanent fix is to remove `PROJ_LIB` (and a stale `GDAL_DATA`) from the environment; modern `pyproj` and `rasterio` ship their own data and do not need them. Set `FARMWISE_FIX_PROJ_DATA=0` to disable the guard and keep the host configuration as-is.

### Local development

Copy the example files in a source checkout and fill in real values:

```powershell
Copy-Item fidel.env.example fidel.env
Copy-Item smtp.env.example smtp.env
Copy-Item public_host.env.example public_host.env
```

`FARMWISE_SMTP_ENV_FILE` overrides where the SMTP file is read from. It is consulted when `farmwise_api.server.email_utils` is first imported, so set it before the process starts.

### Deployment

Provide `SECRET_KEY` and any SMTP credentials through the environment, a secret manager, or your orchestrator's secret mechanism — not through files committed, copied, or baked into an image. If you do use a credential file,
keep it outside the repository and outside the installed `farmwise_api` package, give it owner-only permissions, and do not publish its location. Rotate any secret that has been committed, logged, or shared: removing a file afterwards does not undo the disclosure.

Credential files are excluded from Git by `.gitignore` and from both wheel and source distributions; `tests/test_packaging.py` enforces this on every CI run. FARMWISE does not put credential paths in the errors it raises, so exception text can be logged or surfaced without revealing where secrets are kept.

Large adapter datasets are intentionally excluded from both pip wheels and source distributions. This includes EuroCropV2, EEA, IFSGRID and QUADICA data. Supply redistributable datasets through `FARMWISE_DATA_DIR`, or configure a licence-compliant remote source with a real URL and checksum in `farmwise_api/core/utils/data_manifest.py`. Remote prefetching is disabled by default; enable it with `FARMWISE_PREFETCH_DATA=true` only after configuring that manifest.

CORRECTIV.Lokal data is treated as protected: its Parquet file is absent from the repository, packages and remote-data manifest, and its adapter is disabled from dispatch. Do not publish or mirror source or derived row-level data without explicit written permission covering the exact dataset and use.

IMGW-PIB data is enabled only for permitted local private/non-commercial or academic-research use. It is blocked by every server entry point and its station files are not distributed in pip packages. A permitted local user must privately populate `FARMWISE_DATA_DIR` and explicitly acknowledge the restriction before use:

```powershell
$env:FARMWISE_ENABLE_RESEARCH_IMGW = "1"
```

Do not set this variable on a public or commercial deployment. IMGW source datasets and station files must not be bundled in GitHub releases, PyPI, Zenodo, or container images. Academic outputs derived from IMGW observations must retain the attribution and processing notices in `DATA_LICENSES.md`.

Keep private datasets outside the repository, preferably in a directory mounted through `FARMWISE_DATA_DIR`. Local data directories, credentials, databases, archives, GIS files, rasters and columnar datasets are covered by `.gitignore` and distribution-manifest exclusions. 

EGDI HOVER WP7 is not licensed for redistribution. Its data, adapter and dispatch entries are therefore absent from public pip packages. A private source checkout can use a lawfully obtained local copy through `FARMWISE_DATA_DIR`, but FARMWISE must not expose it through the public API.

### ERA5/CDS authentication

ERA5 is not an anonymous upstream source. Before the ERA5 adapter can retrieve data, the operator must:

1. register and sign in to the ECMWF Climate Data Store;
2. manually accept the terms shown on the ERA5 dataset page; and
3. install their personal CDS API token as described in the
   [official CDS API setup](https://cds.climate.copernicus.eu/how-to-api),
   in the location that documentation specifies for their platform.

The FARMWISE application login is unrelated to the CDS account and does not grant ERA5 access. In server mode, `cdsapi.Client()` uses the credentials of the operating-system account running FARMWISE; API callers must never submit CDS passwords or tokens as request parameters. Do not commit `.cdsapirc`, copy it into a wheel/container image, or write its token to logs. A public deployment that requires every caller to accept CDS terms must disable ERA5 until it provides secure per-user credential delegation.

Writable cache files and the default SQLite database are stored under `FARMWISE_CACHE_DIR` (by default the user's `.cache/farmwise` directory). Set `FARMWISE_DATABASE_URL` to use another SQLAlchemy database URL.

## Local library usage

```python
import asyncio

from farmwise_api import read_data

result = asyncio.run(
    read_data(
        country="Poland",
        level=10,
        time_from="2018-01-01",
        time_to="2018-01-07",
        factors=["temperature", "precipitation"],
    )
)

data = result["data"]
metadata = result["metadata"]
```

`read_data` is asynchronous, so applications already using asyncio should call it with `await read_data(...)`.

Per-source quality assessment is disabled by default. It can be turned on by stating explicitly:

```python
result = await read_data(..., assess_quality=True)
```

When enabled, quality reports run concurrently with subsequent adapter calls and reuse cached S2 coverings.

When several sources provide the same value, FARMWISE harmonises them using the source weights and per-data-type methods defined in
`farmwise_api.adapters.mappings.data_source_mapping`. Both dictionaries can also be overridden for one call:

```python
result = await read_data(
    country="Poland",
    level=10,
    time_from="2018-01-01",
    time_to="2018-01-07",
    factors=["temperature", "precipitation"],
    source_weights={
        "farmwise_api.adapters.API_readers.imgw.imgw_api_synop_daily": 2.0,
        "farmwise_api.adapters.API_readers.cds.cds_single_levels": 1.0,
    },
    harmonization_methods={
        "temperature": "weighted_mean",
        "precipitation": "weighted_median",
    },
    within_source_aggregation_methods={
        "temperature": "mean",
        "precipitation": "median",
    },
)
```

`within_source_aggregation_methods` controls how multiple observations from a single adapter are reduced to one value per S2 cell and time. It is independent from `harmonization_methods`, which combines already aggregated values across different adapters. Supported within-source methods are `mean`, `median`, `mode`, `min`, `max`, `sum`, `first`, `last`, and `nunique`.

Supported methods are `weighted_mean`, `mean`, `weighted_median`, `median`, `weighted_mode`, `mode`, `priority`, `min`, `max`, and `sum`. The effective configuration used for a response is included in `result["metadata"]["harmonization"]`.

## Server usage

After installing `farmwise-api[server]`, start the service with:

```powershell
farmwise-api
```

For development with automatic reload:

```powershell
python -m uvicorn farmwise_api.server.main:app --reload
```

Open `http://localhost:8000`, or use the OpenAPI documentation at
`http://localhost:8000/docs`.

Run the test suite with:

```powershell
python -m pytest
```

## Variable and source registry

[`docs/registry.md`](docs/registry.md) documents every source × variable pair FARMWISE can return: the provider's own variable name, its physical meaning, native and output units, spatial and temporal support, the transformation applied, how repeated values from one source are reduced, and how values from different sources are combined. [`docs/registry.csv`](docs/registry.csv) is the same content as one row per pair, for analysis or inclusion in a paper appendix.

Both are generated:

```powershell
python tools\build_registry.py            # regenerate
python tools\build_registry.py --report   # completeness summary
```

Variable names, output units, coverage, dispatch status, aggregation and harmonisation rules are read **live from the adapters**, so the registry cannot drift from the behaviour it documents; CI fails if the committed files
are stale. Provider, dataset and source URL are taken from [`DATA_LICENSES.md`](DATA_LICENSES.md).

Everything a domain author must supply, native units, spatial and temporal support, per-variable transformations and literature references, lives in [`registry/variables.yaml`](registry/variables.yaml). Unset fields are `null` and are reported as missing rather than guessed; they render as _not supplied_ in the documentation. Run `--report` to see what is outstanding.

### Quality checks

The test suite reports coverage using the settings in `pyproject.toml` (branch coverage, vendored third-party code and the manual station-rebuild scripts excluded):

```powershell
python -m pytest --cov
```

Code-line coverage is currently **89%**. `fail_under` is set to 80, so a change that reduces coverage fails the run.

`core` and `server` are type-checked; the adapter layer is not yet:

```powershell
python -m mypy -p farmwise_api.core -p farmwise_api.server
```

Both checks run in CI across the whole Python matrix. Package mode (`-p`) is used rather than paths because the repository root contains an `__init__.py`, which otherwise makes mypy resolve each module under two names.

The EEA raster integration tests are opt-in:

```powershell
$env:FARMWISE_RUN_INTEGRATION_TESTS = "1"
python -m pytest tests\test_eea.py
```

## Main API request

Authenticated clients can call `POST /read-data-direct`:

```json
{
  "country": ["Poland"],
  "level": 10,
  "time_from": "2018-01-01",
  "time_to": "2018-01-07",
  "factors": ["temperature", "precipitation"],
  "separate_api": true,
  "interpolation": false,
  "produce_map": false
}
```

Requests are authenticated with a bearer token obtained from `POST /token`.

Every response carries an explicit `status`. In the default synchronous mode the call returns when processing has finished:

```json
{
  "status": "success",
  "data_url": "https://<host>/download/<name>.csv",
  "metadata_url": "https://<host>/download/<name>.json",
  "map_url": null
}
```

A request that no source can serve returns HTTP 404, and an internal failure HTTP 500; both carry `status`, `error_code` (`no_data`, `internal_error`) and a message.

Large requests take minutes, which is awkward for a client that must not block on one connection. Adding `"mode": "async"` makes the server accept the request and answer immediately with HTTP 202:

```json
{
  "job_id": "5f2b...",
  "status": "accepted",
  "status_url": "https://<host>/jobs/5f2b...",
  "poll_after_seconds": 5,
  "created_utc": "2026-09-24T09:15:00+00:00"
}
```

`GET /jobs/{job_id}` then reports `accepted`, `running`, and finally one of the terminal states `success` (with the same download links), `no_data` or `error`. A job is readable only by the user who created it; any other job id is reported as not found. Job records are kept for three hours.

Rate limits are 10 requests per minute for `/read-data-direct` and 60 per minute for `/jobs/{job_id}`. Generated files are removed about an hour after they are written, so download them promptly. `/download/{file_name}` is not authenticated: the link itself is the only protection, and it must not be shared.

The asynchronous job registry lives in the server process. Run the public server with a single worker, or replace `farmwise_api/server/jobs.py` with a shared store, before scaling to several workers.

## Web frontend

FARMWISE API includes an authenticated web interface for users who prefer not to interact with the Python library or REST endpoints directly. After signing in, users can select one or more countries or define a custom WGS 84 bounding box, choose a date range, set the S2 spatial resolution, and request multiple agricultural or environmental parameters. The interface also provides options to keep outputs from individual data sources in separate columns, enable interpolation, and generate an interactive HTML map. Requests are processed asynchronously, and links to the resulting CSV data, source metadata, and optional map are sent to the user by email.

## Evaluation and benchmarks

Raw empirical inputs for coverage pre-check, scaling, data quality, and cross-source comparisons are collected by the scripts in
[`evaluation/`](evaluation/README.md):

```powershell
python -m pip install -e ".[evaluation]"
python -m evaluation.run_all
```

For a permitted local academic evaluation that includes the IMGW--ERA5 Poland comparison, set the option in `evaluation/collect_empirical.py` and run that file from the IDE:

```python
INCLUDE_IMGW_RESEARCH = True
```

Scenario definitions and collection settings are explicit in the Python source. Statistical analysis and figure generation are performed separately in the evaluation notebook.

## Reproducibility

Dependencies are specified at two levels, for two different purposes.

`pyproject.toml` declares a supported *range* for every dependency. The floor of each range is the lowest version the test suite has actually been run against, and the ceiling is the next major release (the next minor for `0.x` projects, whose minor releases may break compatibility). Install this way to use FARMWISE as a library alongside other packages:

```powershell
python -m pip install -e ".[server,dev]"
```

[`requirements-lock.txt`](requirements-lock.txt) pins the *exact* transitive closure — 146 packages, each with SHA-256 hashes — of the environment the published results and the CI test runs were produced in. Install this way to reconstruct that environment:

```powershell
python -m pip install --require-hashes -r requirements-lock.txt
python -m pip install -e . --no-deps
```

Regenerate the lock after changing any dependency in `pyproject.toml`:

```powershell
python tools\make_lock.py
```

## License

The FARMWISE source code is licensed under the [Apache License 2.0](LICENSE). Third-party datasets accessed or processed by FARMWISE remain subject to their respective licences and are not relicensed under Apache-2.0. See the [data licensing and attribution register](DATA_LICENSES.md) for source-specific terms.

For responsible vulnerability reporting, see the [security policy](SECURITY.md). For software citation metadata, see [`CITATION.cff`](CITATION.cff).

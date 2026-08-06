# FARMWISE API

FARMWISE is dual-use:

- as a local Python library through `main_call`;
- as an HTTP service through `main`.

A request describes an area (a country or a bounding box), a date range, an S2
cell level, and one or more factors. FARMWISE selects matching adapters,
downloads their data, normalizes it to S2 cells, and returns the combined data
with source metadata and an optional HTML map.

## Project layout

```text
adapters/
  API_readers/       integrations with individual data providers
  mappings/          adapter registry and supported ranges
core/
  main_call.py       adapter selection and result aggregation
  utils/             spatial, interpolation, mapping, and data-path helpers
server/
  main.py            FastAPI application
  routers/           authentication, frontend, and data endpoints
  static/            packaged frontend assets
  *.py               persistence, security, and background services
tests/               unit and integration tests
main_call.py          stable local-library entry point
main.py               stable server entry point
```

All imports are rooted at one of the three top-level packages (`adapters`,
`core`, or `server`). Commands should be run from the repository root.

## Installation

Python 3.10 or newer is required.

Install the local-library variant:

```powershell
python -m pip install farmwise-api
```

Install the server variant, including FastAPI, authentication, persistence,
and the ASGI server:

```powershell
python -m pip install "farmwise-api[server]"
```

For development from a repository checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[server,dev]"
```

The Hub'Eau adapters use the bundled helper library:

```powershell
python -m pip install -e .\internal-lib\hubeaupyutils\hubeaupyutils-main
```

## Configuration

Copy the example files and provide real values:

```powershell
Copy-Item fidel.env.example fidel.env
Copy-Item server\smtp.env.example server\smtp.env
Copy-Item public_host.env.example public_host.env
```

`fidel.env` contains JWT settings. SMTP configuration is only required when
email delivery is used. `PUBLIC_BASE_URL` should contain a host and optional
port without a URL scheme, for example `localhost:8000`.

Large adapter datasets are intentionally excluded from both pip wheels and
source distributions. This includes EuroCropV2, EEA and IFSGRID data. Supply
redistributable datasets through `FARMWISE_DATA_DIR`, or configure a
licence-compliant remote source with a real URL and checksum in
`core/utils/data_manifest.py`.
Remote prefetching is disabled by default; enable it with
`FARMWISE_PREFETCH_DATA=true` only after configuring that manifest.

CORRECTIV.Lokal data is treated as protected: its Parquet file is absent from
the repository, packages and remote-data manifest, and its adapter is disabled
from dispatch. Do not publish or mirror source or derived row-level data
without explicit written permission covering the exact dataset and use.

IMGW-PIB data is enabled only for private, non-commercial local use. It is
blocked by every server entry point and its station files are not distributed
in pip packages. A permitted local user must privately populate
`FARMWISE_DATA_DIR` and explicitly acknowledge the restriction before use:

```powershell
$env:FARMWISE_ENABLE_PRIVATE_IMGW = "1"
```

Do not set this variable on a public or commercial deployment. IMGW source or
derived data must not be written to public exports, evaluation outputs, shared
caches, GitHub, PyPI, Zenodo, or container images.

Keep private datasets outside the repository, preferably in a directory
mounted through `FARMWISE_DATA_DIR`. Local data directories, credentials,
databases, archives, GIS files, rasters and columnar datasets are covered by
`.gitignore` and distribution-manifest exclusions. These rules protect new
files; they do not erase files already present in Git history.

EGDI HOVER WP7 is not licensed for redistribution. Its data, adapter and
dispatch entries are therefore absent from public pip packages. A private
source checkout can use a lawfully obtained local copy through
`FARMWISE_DATA_DIR`, but FARMWISE must not expose it through the public API.

### ERA5/CDS authentication

ERA5 is not an anonymous upstream source. Before the ERA5 adapter can retrieve
data, the operator must:

1. register and sign in to the ECMWF Climate Data Store;
2. manually accept the terms shown on the ERA5 dataset page; and
3. place their personal CDS API token in `%USERPROFILE%\.cdsapirc` on Windows
   or `$HOME/.cdsapirc` on Linux/macOS, following the
   [official CDS API setup](https://cds.climate.copernicus.eu/how-to-api).

The FARMWISE application login is unrelated to the CDS account and does not
grant ERA5 access. In server mode, `cdsapi.Client()` uses the credentials of
the operating-system account running FARMWISE; API callers must never submit
CDS passwords or tokens as request parameters. Do not commit `.cdsapirc`, copy
it into a wheel/container image, or write its token to logs. A public
deployment that requires every caller to accept CDS terms must disable ERA5
until it provides secure per-user credential delegation.

Writable cache files and the default SQLite database are stored under
`FARMWISE_CACHE_DIR` (by default the user's `.cache/farmwise` directory).
Set `FARMWISE_DATABASE_URL` to use another SQLAlchemy database URL.

## Local library usage

```python
import asyncio

from main_call import read_data

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

`read_data` is asynchronous, so applications already using asyncio should call
it with `await read_data(...)`.

Per-source quality assessment is enabled by default. For latency-sensitive
requests it can be skipped explicitly:

```python
result = await read_data(..., assess_quality=False)
```

When enabled, quality reports run concurrently with subsequent adapter calls
and reuse cached S2 coverings.

When several sources provide the same value, FARMWISE harmonizes them using
the source weights and per-data-type methods defined in
`adapters.mappings.data_source_mapping`. Both dictionaries can also be
overridden for one call:

```python
result = await read_data(
    country="Poland",
    level=10,
    time_from="2018-01-01",
    time_to="2018-01-07",
    factors=["temperature", "precipitation"],
    source_weights={
        "adapters.API_readers.imgw.imgw_api_synop_daily": 2.0,
        "adapters.API_readers.cds.cds_single_levels": 1.0,
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

`within_source_aggregation_methods` controls how multiple observations from a
single adapter are reduced to one value per S2 cell and time. It is independent
from `harmonization_methods`, which combines already aggregated values across
different adapters. Supported within-source methods are `mean`, `median`,
`mode`, `min`, `max`, `sum`, `first`, `last`, and `nunique`.

Supported methods are `weighted_mean`, `mean`, `weighted_median`, `median`,
`weighted_mode`, `mode`, `priority`, `min`, `max`, and `sum`. The effective
configuration used for a response is included in
`result["metadata"]["harmonization"]`.

## Server usage

After installing `farmwise-api[server]`, start the service with:

```powershell
farmwise-api
```

For development with automatic reload:

```powershell
python -m uvicorn main:app --reload
```

Open `http://localhost:8000`, or use the OpenAPI documentation at
`http://localhost:8000/docs`.

Run the test suite with:

```powershell
python -m pytest
```

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

The response contains download links for the data CSV, metadata JSON, and,
when requested, an HTML map.

## Evaluation and benchmarks

Reproducible experiments for per-source quality, coverage pre-check efficiency,
scaling, and ERA5-observational-source agreement live in
[`evaluation/`](evaluation/README.md). Install the plotting extra and regenerate
the offline controls with:

```powershell
python -m pip install -e ".[evaluation]"
python -m evaluation.run_all
```

The committed logs and figures are explicitly labelled synthetic controls.
Use `evaluation.collect_cross_source` and observed dispatch latencies before
reporting the results as empirical or publication-ready.

## License

The FARMWISE source code is licensed under the
[Apache License 2.0](LICENSE). Third-party datasets accessed or processed by
FARMWISE remain subject to their respective licences and are not relicensed
under Apache-2.0. See the [data licensing and attribution
register](DATA_LICENSES.md) for source-specific terms.

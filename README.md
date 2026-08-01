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

Large adapter datasets may be supplied under `adapters/API_readers` or through
`FARMWISE_DATA_DIR`. Remote prefetching is disabled by default; enable it with
`FARMWISE_PREFETCH_DATA=true` after replacing placeholder entries in
`core/utils/data_manifest.py` with real URLs and checksums.

The multi-gigabyte EuroCropV2 `points.csv` dataset is intentionally excluded
from the pip distribution. Provide it through `FARMWISE_DATA_DIR`, or configure
its remote source in the data manifest before using that adapter.

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

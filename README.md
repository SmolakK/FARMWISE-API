# FARMWISE API

FARMWISE aggregates agricultural and environmental data from European data
providers. A request describes an area (a country or a bounding box), a date
range, an S2 cell level, and one or more factors. The service selects matching
adapters, downloads their data, normalizes it to S2 cells, and returns a CSV
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
  *.py               persistence, security, and background services
static/              frontend assets
tests/               unit and integration tests
```

All imports are rooted at one of the three top-level packages (`adapters`,
`core`, or `server`). Commands should be run from the repository root.

## Installation

Python 3.10 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
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

Writable cache files and the default SQLite database are stored under
`FARMWISE_CACHE_DIR` (by default the user's `.cache/farmwise` directory).
Set `FARMWISE_DATABASE_URL` to use another SQLAlchemy database URL.

## Running

```powershell
python -m uvicorn server.main:app --reload
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

# FARMWISE API

FARMWISE API is a unified platform for accessing European agricultural and environmental data. It
is developed under the FARMWISE project (https://farmwise-project.eu/) to facilitate experiments and studies
on the sustainable agriculture and decision-making. FARMWISE-API brings together information from 
multiple sources, standardizes it, and organizes it into a consistent geospatial format. Users can 
request data for a specific area and time period, including factors such as temperature and precipitation. 
The platform can be used as either a Python library or an HTTP service, supporting research and 
informed decision-making for sustainable agriculture.

FARMWISE is dual-use:

- as a local Python library through `farmwise_api`;
- as an HTTP service through `farmwise_api.server`.

A request describes an area (a country or a bounding box), a date range, an S2
cell level, and one or more factors. FARMWISE selects matching adapters,
downloads their data, normalizes it to S2 cells, and returns the combined data
with source metadata and an optional HTML map.

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

All installed modules are contained under the `farmwise_api` namespace to
avoid collisions with unrelated Python packages. Development commands should
be run from the repository root.

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

The Hub'Eau helper library is vendored privately under
`farmwise_api._vendor.hubeaupyutils` and retains its MIT licence. It does not
install a separate top-level `hubeaupyutils` package.

## Configuration

Copy the example files and provide real values:

```powershell
Copy-Item fidel.env.example fidel.env
Copy-Item farmwise_api\server\smtp.env.example smtp.env
Copy-Item public_host.env.example public_host.env
```

`fidel.env` contains JWT settings. SMTP configuration is only required when
email delivery is used. By default it is read from `smtp.env` in the
repository root when FARMWISE runs from a source checkout, and from `smtp.env`
in the process working directory when it runs as an installed package. Never
place it inside the `farmwise_api` package directory: that directory may be
read-only once installed, and credentials must not sit next to the shipped
source. Set `FARMWISE_SMTP_ENV_FILE` to use another location; it is read when
`farmwise_api.server.email_utils` is first imported, so export it before
starting the server.
`PUBLIC_BASE_URL` should contain a host and optional port without a URL scheme,
for example `localhost:8000`.

Large adapter datasets are intentionally excluded from both pip wheels and
source distributions. This includes EuroCropV2, EEA, IFSGRID and QUADICA
data. Supply redistributable datasets through `FARMWISE_DATA_DIR`, or configure a
licence-compliant remote source with a real URL and checksum in
`farmwise_api/core/utils/data_manifest.py`.
Remote prefetching is disabled by default; enable it with
`FARMWISE_PREFETCH_DATA=true` only after configuring that manifest.
QUADICA v1 additionally requires the prepared filenames and provenance
described in `farmwise_api/adapters/API_readers/quadica/DATA_SETUP.md`.

CORRECTIV.Lokal data is treated as protected: its Parquet file is absent from
the repository, packages and remote-data manifest, and its adapter is disabled
from dispatch. Do not publish or mirror source or derived row-level data
without explicit written permission covering the exact dataset and use.

IMGW-PIB data is enabled only for permitted local private/non-commercial or
academic-research use. It is blocked by every server entry point and its
station files are not distributed in pip packages. A permitted local user must
privately populate
`FARMWISE_DATA_DIR` and explicitly acknowledge the restriction before use:

```powershell
$env:FARMWISE_ENABLE_RESEARCH_IMGW = "1"
```

Do not set this variable on a public or commercial deployment. IMGW source
datasets and station files must not be bundled in GitHub releases, PyPI,
Zenodo, or container images. Academic outputs derived from IMGW observations
must retain the attribution and processing notices in `DATA_LICENSES.md`.

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

`read_data` is asynchronous, so applications already using asyncio should call
it with `await read_data(...)`.

Per-source quality assessment is disabled by default. It can be turned on by stating explicitly:

```python
result = await read_data(..., assess_quality=True)
```

When enabled, quality reports run concurrently with subsequent adapter calls
and reuse cached S2 coverings.

When several sources provide the same value, FARMWISE harmonizes them using
the source weights and per-data-type methods defined in
`farmwise_api.adapters.mappings.data_source_mapping`. Both dictionaries can also be
overridden for one call:

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
python -m uvicorn farmwise_api.server.main:app --reload
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
when requested, an HTML map with data visualization.

## Web frontend

FARMWISE API includes an authenticated web interface for users who prefer not to interact with the Python library 
or REST endpoints directly. After signing in, users can select one or more countries or define a custom WGS 84 bounding
box, choose a date range, set the S2 spatial resolution, and request multiple agricultural or environmental parameters.
The interface also provides options to keep outputs from individual data sources in separate columns, enable
interpolation, and generate an interactive HTML map. Requests are processed asynchronously,
and links to the resulting CSV data, source metadata, and optional map are sent to the user by email.

## Evaluation and benchmarks

Raw empirical inputs for coverage pre-check, scaling, data quality, and
cross-source comparisons are collected by the scripts in
[`evaluation/`](evaluation/README.md):

```powershell
python -m pip install -e ".[evaluation]"
python -m evaluation.run_all
```

For a permitted local academic evaluation that includes the IMGW--ERA5 Poland
comparison, set the option in `evaluation/collect_empirical.py` and run that
file from the IDE:

```python
INCLUDE_IMGW_RESEARCH = True
```

Scenario definitions and collection settings are explicit in the Python
source. Statistical analysis and figure generation are performed separately
in the evaluation notebook.

## License

The FARMWISE source code is licensed under the
[Apache License 2.0](LICENSE). Third-party datasets accessed or processed by
FARMWISE remain subject to their respective licences and are not relicensed
under Apache-2.0. See the [data licensing and attribution
register](DATA_LICENSES.md) for source-specific terms.

For responsible vulnerability reporting, see the [security
policy](SECURITY.md). For software citation metadata, see
[`CITATION.cff`](CITATION.cff).

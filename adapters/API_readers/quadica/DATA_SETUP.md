# QUADICA v1 data setup

The adapter targets the published QUADICA v1 resource:

- Ebeling, P., Kumar, R., Weber, M., and Musolff, A. (2022),
  `https://doi.org/10.4211/hs.0ec5f43e43c349ff818a8d57699c0fe1`;
- Creative Commons Attribution 4.0 International;
- corresponding paper: `https://doi.org/10.5194/essd-14-3715-2022`.

QUADICA data are not bundled in FARMWISE. Place the following prepared files
under `<FARMWISE_DATA_DIR>/quadica/data/`:

```text
c_annual_with_coords.csv
n_surplus_with_coords.csv
pet_monthly_with_coords.csv
pre_monthly_with_coords.csv
q_annual_with_coords.csv
tavg_monthly_with_coords.csv
wrtds_monthly_with_coords_date_merged.csv
```

Every prepared file must retain `OBJECTID`, `lat`, and `lon`. Vertical annual
files additionally use `Year`; the WRTDS file uses `date`; prepared horizontal
meteorological files use ISO date strings as value-column names.

These filenames describe derivatives, not the untouched HydroShare archive.
Record how coordinates were joined, retain the provenance and licence of the
coordinate source, cite QUADICA, and state that FARMWISE filtered records and
aggregated stations into S2 cells. Do not silently substitute QUADICA v2 files:
their schema and upstream licensing/provenance require a separate review.

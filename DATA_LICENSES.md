# FARMWISE data licensing and attribution register

Last reviewed: 2026-08-05

This register covers third-party datasets accessed, cached, transformed, or
redistributed by FARMWISE. The Apache License 2.0 in [`LICENSE`](LICENSE)
applies to FARMWISE source code only. It does not relicense third-party data.

An API response or downloadable export containing third-party observations is
also a redistribution of data, even when FARMWISE deletes its temporary copy
after the response. Every export must therefore retain the applicable source,
licence, access date, and modification notices listed below.

## Status definitions

- **Allowed**: redistribution is permitted when the stated conditions are met.
- **Conditional**: do not mirror or bundle the dataset until the listed issue
  is resolved for the intended use.
- **Prohibited**: FARMWISE has not identified a licence granting redistribution.
- **Disabled**: the source is not dispatched and old cached copies must not be
  published without their original licence metadata.

## Source register

### GeoSphere Austria daily station data

- **Adapter:** `adapters.API_readers.geosphere.geosphere`
- **Dataset/resource:** Station Data-v2 (1 d), resource `klima-v2-1d`
- **Local persistence:** response data is processed in memory; derived server
  exports and quality reports may be persisted.
- **Provider:** GeoSphere Austria
- **Source:** <https://dataset.api.hub.geosphere.at/app/frontend/station/historical/klima-v2-1d>
- **Licence:** [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)
- **Required attribution:** identify GeoSphere Austria and Station Data-v2
  (1 d), link the source and CC BY 4.0, state the access date, and indicate
  that FARMWISE filtered and aggregated station records into S2 cells.
- **Redistribution status:** **Allowed**.

### Deutscher Wetterdienst observations

- **Adapter:** `adapters.API_readers.wetterdienst.wetterdienst_dwd`
- **Dataset/resource:** DWD Climate Data Center/Open Data observations accessed
  through Wetterdienst.
- **Local persistence:** Wetterdienst may maintain its own disk cache; derived
  server exports and quality reports may be persisted.
- **Provider:** Deutscher Wetterdienst (DWD)
- **Source:** <https://opendata.dwd.de/climate_environment/CDC/>
- **Licence:** [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)
- **Terms:** <https://www.dwd.de/DE/leistungen/opendata/faqs_opendata.html>
- **Required attribution:** identify Deutscher Wetterdienst and the source
  service. For aggregated FARMWISE output, use a modification notice such as
  `Datenbasis: Deutscher Wetterdienst, Einzelwerte gemittelt` and describe S2
  and temporal aggregation.
- **Redistribution status:** **Allowed**.

### SoilGrids

- **Adapter:** `adapters.API_readers.soilgrids.soilgrids_call`
- **Dataset/resource:** SoilGrids 2.0 predicted soil-property maps.
- **Local resources:** `adapters/API_readers/soilgrids/temp_storage/*.tif`
  and per-request scratch GeoTIFFs.
- **Provider:** ISRIC — World Soil Information
- **Source:** <https://soilgrids.org/>
- **Licence:** [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)
- **Terms and citation:** <https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_04.html>
- **Required attribution:** cite SoilGrids 2.0 and Poggio et al. (2021), link
  the licence and source, and indicate clipping/resampling/S2 aggregation.
- **Redistribution status:** **Allowed**.

### ERA5 single-level reanalysis

- **Adapter:** `adapters.API_readers.cds.cds_single_levels`
- **Dataset/resource:** `reanalysis-era5-single-levels`
- **Local persistence:** temporary NetCDF or ZIP-wrapped NetCDF files are
  created per request and removed after processing.
- **Provider:** Copernicus Climate Change Service (C3S), implemented by ECMWF
- **Source:** <https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels>
- **DOI:** <https://doi.org/10.24381/cds.adbb2d47>
- **Licence:** CC-BY licence displayed by the dataset catalogue.
- **Required attribution:** identify the Copernicus Climate Change Service,
  cite the DOI and access date, link the applicable licence, and state that
  FARMWISE converted units and aggregated hourly data to daily S2-cell output.
- **Redistribution status:** **Allowed**.

### CDS satellite land cover

- **Adapter/helper:** `adapters.API_readers.cds.cds_land_cover` (not currently
  registered for normal dispatch)
- **Dataset/resource:** `satellite-land-cover`
- **Local persistence:** ZIP and extracted products may be written to
  `adapters/API_readers/cds/temp_storage/`.
- **Source:** <https://cds.climate.copernicus.eu/datasets/satellite-land-cover>
- **DOI:** <https://doi.org/10.24381/cds.006f2c9a>
- **Licence:** the catalogue lists ESA CCI, CC-BY, and VITO licences. The
  applicable notices depend on product version and input provider.
- **Required attribution:** preserve all licence and provider notices supplied
  with the downloaded product, cite the DOI and access date, and state all
  transformations.
- **Redistribution status:** **Conditional**. Do not mirror a downloaded
  archive under a generic CC BY label; record the exact licences accompanying
  that archive first.

### Deprecated CDS agroproductivity indicators

- **Adapter:** `adapters.API_readers.cds.cds_vegetation`
- **Dataset/resource:** `sis-agroproductivity-indicators`
- **Local persistence:** historical ZIP/NetCDF cache files may exist under
  `adapters/API_readers/cds/temp_storage/`.
- **State:** downloads have been permanently retired and the adapter is listed
  in `DISABLED_API_SOURCES`.
- **Redistribution status:** **Disabled**. Do not publish an old cached copy
  unless its original dataset-specific licence and attribution record were
  retained with it.

### IMGW-PIB meteorological and hydrological observations

- **Adapters:** `adapters.API_readers.imgw.imgw_api_synop_daily` and
  `adapters.API_readers.imgw_hydro.imgw_api_hydro_daily`
- **Local resources:**
  `adapters/API_readers/imgw/constants/imgw_coordinates.csv`,
  `adapters/API_readers/imgw/constants/imgw_raw.csv`, and
  `adapters/API_readers/imgw_hydro/constants/imgw_coordinates.csv`.
- **Provider:** Instytut Meteorologii i Gospodarki Wodnej — Państwowy Instytut
  Badawczy (IMGW-PIB)
- **Source and terms:** <https://danepubliczne.imgw.pl/datastore>
- **Required attribution:** include the exact statement
  `Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy`.
  For processed data also include
  `Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu Badawczego zostały przetworzone`.
- **Redistribution status:** **Conditional**. The published terms allow reuse
  with attribution, but also require an agreement for specified business and
  agricultural-support uses unless the particular dataset is a high-value
  dataset. Obtain written confirmation from IMGW-PIB for a commercial or
  agriculture-facing hosted FARMWISE service. Until then, do not mirror full
  IMGW datasets; keep access local/on demand.

### GIOŚ soil monitoring and groundwater monitoring

- **Adapters:** `adapters.API_readers.gios.gios_scraper` and
  `adapters.API_readers.gios_gw.gios_gw`
- **Local resources:**
  `adapters/API_readers/gios/constants/gios_coordinates.csv` and
  `adapters/API_readers/gios_gw/constants/gios_gw_stations.csv`.
- **Provider:** Główny Inspektorat Ochrony Środowiska (GIOŚ)
- **Terms:** <https://www.gov.pl/web/gios/ponowne-wykorzystywanie-danych>
- **Required attribution:** use either `Źródło danych: Główny Inspektorat
  Ochrony Środowiska` or `Źródło danych: GIOŚ`; state that FARMWISE filtered,
  normalized, and aggregated the data.
- **Redistribution status:** **Allowed** for information published through
  GIOŚ systems, subject to the stated attribution and any dataset-specific
  conditions.

### CORINE Land Cover

- **Adapter:** `adapters.API_readers.corine.corine_read`
- **Dataset/resource:** CORINE Land Cover map services for requested reference
  years.
- **Local persistence:** fetched raster images are processed per request;
  derived server exports may be persisted.
- **Provider:** European Union's Copernicus Land Monitoring Service (CLMS)
- **Source:** <https://land.copernicus.eu/en/products/corine-land-cover>
- **Policy:** <https://land.copernicus.eu/en/data-policy>
- **Licence/policy:** full, open, and free access, including redistribution and
  commercial use, subject to source and modification notices.
- **Required attribution for derived output:** `Generated using European
  Union's Copernicus Land Monitoring Service information` followed by the
  dataset URL/DOI and access date. Clearly state FARMWISE modifications and do
  not imply EU endorsement.
- **Redistribution status:** **Allowed**.

### EGDI / GeoERA HOVER WP7 DRASTIC layers

- **Adapters:** `adapters.API_readers.egdi.egdi_read_hc` and
  `adapters.API_readers.egdi.egdi_read_d10`
- **Local resources:** not bundled. A local user may place lawfully obtained
  files under `egdi/data/` in `FARMWISE_DATA_DIR`.
- **Originator:** Federal Institute for Geosciences and Natural Resources
  (BGR), distributed through EGDI
- **Metadata:** <https://metadata.europe-geology.eu/record/basic/60e6fc02-e01c-40c5-b878-73990a010833>
- **Declared conditions:** `Copyright (All Rights Reserved)`; public access has
  no limitation, but no redistribution licence is granted.
- **Redistribution status:** **Prohibited** without written permission from
  the rights holder. These files must not be included in GitHub, PyPI, Zenodo,
  containers, releases, or public API downloads. Both EGDI adapters are
  excluded from public packages and from runtime dispatch. Local users may
  provide their own lawfully obtained files through `FARMWISE_DATA_DIR` only
  when using a private source checkout.

### Hub'Eau water data

- **Adapters:** `adapters.API_readers.hubeau.hubeau_wq_read`,
  `adapters.API_readers.hubeau.hubeau_piezo_read_vbrgm`, and
  `adapters.API_readers.hubeau.hubeau_sw_quality_read`
- **Local resources:** station and parameter selections under
  `adapters/API_readers/hubeau/constants/`.
- **Providers:** Office français de la biodiversité (OFB), BRGM, Service
  Central Vigicrues, and the producers identified by individual records.
- **Source:** <https://hubeau.eaufrance.fr/>
- **Terms:** <https://hubeau.eaufrance.fr/page/conditions-generales>
- **Licence:** Licence Ouverte / Open Licence Etalab 2.0
- **Required attribution:** identify Hub'Eau and the record's original
  producer(s), provide the source URL and access date, and indicate FARMWISE
  filtering and S2 aggregation.
- **Redistribution status:** **Allowed**.

### Ukrainian surface-water monitoring

- **Adapter:** `adapters.API_readers.UA_sw_quality.ukrainian_surface_water`
- **Dataset/resource:** state monitoring observations for Ukrainian surface
  waters.
- **Local persistence:** source CSVs are processed in memory; derived server
  exports may be persisted.
- **Provider:** State Agency of Water Resources of Ukraine
- **Source:** <https://data.gov.ua/dataset/surface-water-monitoring>
- **Licence:** [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)
- **Required attribution:** identify the State Agency of Water Resources of
  Ukraine, link the dataset and licence, state the access date, and describe
  FARMWISE cleaning, renaming, filtering, and S2 aggregation.
- **Redistribution status:** **Allowed**.

### EPA Ireland groundwater observations

- **Adapter:** `adapters.API_readers.epa_ireland.epa_gw`
- **Local resource:**
  `adapters/API_readers/epa_ireland/constants/EPA_coordinates.csv`.
- **Provider:** Environmental Protection Agency Ireland
- **Source:** station downloads referenced from EPA Hydronet; general EPA data
  portal at <https://data.epa.ie/>.
- **Policy:** <https://gis.epa.ie/ContactUs/Policy>
- **Licence:** EPA-produced data is made available under CC BY 4.0.
- **Required attribution:** identify EPA Ireland, link the source and licence,
  state the access date and FARMWISE modifications.
- **Special restriction:** Ordnance Survey Ireland base maps, aerial imagery,
  and other third-party map content displayed by EPA services are not covered
  by EPA's CC BY grant and must not be copied into FARMWISE exports.
- **Redistribution status:** **Allowed** for EPA-produced station data only.

### Met Éireann daily station observations

- **Adapter:** `adapters.API_readers.irish_meteo.Irish MS_daily`
- **Local resource:**
  `adapters/API_readers/irish_meteo/EPA_ireland_stations.csv`.
- **Provider:** Met Éireann
- **Source:** <https://cli.fusio.net/cli/climate_data/webdata/>
- **Published licence example and attribution terms:**
  <https://data.gov.ie/dataset/latest-observations>
- **Licence:** [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)
- **Required attribution:** retain all five statements required by Met Éireann:
  copyright Met Éireann; source `www.met.ie`; CC BY 4.0 licence and link; the
  Met Éireann no-liability disclaimer; and, where applicable, an indication
  that FARMWISE modified the material.
- **Redistribution status:** **Allowed**.

### EuroCropV2

- **Adapter:** `adapters.API_readers.EuroCropV2.EuroCropV2_read`
- **Local resource:** `adapters/API_readers/EuroCropV2/data/points.csv`.
- **Provider:** European Commission, Joint Research Centre (JRC), with the
  contributors identified in the dataset catalogue.
- **Source:** <https://data.jrc.ec.europa.eu/dataset/b9fb9e67-78a9-4327-9d59-39a928d812d3>
- **DOI:** <https://doi.org/10.2905/JRC.FX0BVKR>
- **Licence:** [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)
- **Copyright notice:** <https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/DRLL/EuroCropsV2/copyright.txt>
- **Required attribution:** cite `European Commission, Joint Research Centre
  (2026): EuroCropsV2`, the DOI, source, and CC BY 4.0; state that parcel
  geometry/attributes were converted or reformatted into FARMWISE point data.
- **Redistribution status:** **Allowed**, but the multi-gigabyte derived file
  must be hosted as a separately licensed data artifact, not embedded in the
  Git repository or PyPI wheel.

### CORRECTIV.Lokal groundwater data

- **Adapter:** `adapters.API_readers.correctiv.correctiv_read`
- **Local resource:**
  `adapters/API_readers/correctiv/data/data_points.parquet`.
- **Source:** <https://github.com/correctiv/grundwasser-data>
- **Declared repository licence:** GNU General Public License v3.0
- **Additional requirement:** the source README requires compliance with the
  linked rules for naming CORRECTIV.Lokal.
- **Required attribution:** identify CORRECTIV.Lokal and the original
  repository, preserve the GPL-3.0 notice, provide the preferred/source form
  or reproducible conversion script, and prominently state changes that
  produced the FARMWISE Parquet file.
- **Redistribution status:** **Conditional**. The repository contains a GPL-3.0
  file but does not explicitly separate the licensing of the compiled dataset
  from code, and the observations originate from multiple German authorities.
  Obtain written confirmation from CORRECTIV that the licence covers data
  redistribution before FARMWISE mirrors the Parquet file. Until then,
  distribute only a transformation script and fetch from the official source.

### IFSGRID agricultural census data

- **Adapter:** `adapters.API_readers.IFSGRID.IFSGRID_read`
- **Local resources:** shapefile layers under
  `adapters/API_readers/IFSGRID/data/IFSGRID/data/` and
  `adapters/API_readers/IFSGRID/utils/definitions.json`.
- **Provider:** Eurostat and contributing national statistical authorities
- **Source/DOI:** <https://doi.org/10.5281/zenodo.14852709>
- **Licence:** [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)
- **Required attribution:** cite Eurostat (2025), `Geospatial data from
  agricultural census, IFSGRID`, the DOI and CC BY 4.0; indicate FARMWISE
  filtering, field selection, and S2 aggregation.
- **Special restriction:** the official release excludes Germany because its
  release was not approved. Do not add German agricultural census microdata or
  inferred layers from a non-approved source.
- **Redistribution status:** **Allowed** for the official Zenodo release.

### EEA Environmental Zones 2018

- **Adapter:** `adapters.API_readers.eea.eea_read`
- **Local resource:**
  `adapters/API_readers/eea/eea_data/eea_r_3035_1_km_env-zones_p_2018_v01_r00.tif`.
- **Distributor:** European Environment Agency (EEA)
- **EEA source:** <https://www.eea.europa.eu/en/datahub/datahubitem-view/c8c4144a-8c0e-4686-9422-80dbf86bc0cb>
- **Underlying dataset:** Marc J. Metzger (2018), The Environmental
  Stratification of Europe, University of Edinburgh,
  <https://doi.org/10.7488/ds/2356>.
- **Licence/policy:** the EEA product is designated full and open; the
  underlying EnS dataset is CC BY 4.0.
- **Required attribution:** identify EEA as distributor and cite Marc J.
  Metzger/University of Edinburgh and the DOI; link CC BY 4.0 and state raster
  conversion, reprojection, clipping, and S2 aggregation performed by
  EEA/FARMWISE as applicable.
- **Redistribution status:** **Allowed**.

### Czech Hydrometeorological Institute historical daily observations

- **Adapter:** `adapters.API_readers.CHMI_Meteo.CHMI_meteo` (currently not
  registered for normal dispatch)
- **Local resources:**
  `adapters/API_readers/CHMI_Meteo/json_files_list.txt`, runtime
  `downloaded_json/`, and runtime `CHMI_merged_data.csv`.
- **Provider:** Český hydrometeorologický ústav (ČHMÚ/CHMI)
- **Source:** <https://opendata.chmi.cz/meteorology/climate/historical/data/daily/>
- **Metadata:** <https://geoportal.gov.cz/php/micka/record/basic/667bd7a6-4c94-4d23-833b-4f83fc0a8017c>
- **Licence:** [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)
- **Required attribution:** identify ČHMÚ, link the source and CC BY 4.0,
  record the access date, and describe merging, filtering, renaming, and S2
  aggregation.
- **Redistribution status:** **Allowed**.

## Generated FARMWISE artifacts

### Evaluation logs and figures

Files under `evaluation/logs/` and `evaluation/figures/` marked as synthetic
contain generated controls and may be distributed under the FARMWISE code or
documentation terms. Files generated from real source observations inherit
the attribution and licence obligations of every source represented in them.
Their accompanying manifest must distinguish synthetic and empirical output.

### Quality reports

Per-source JSON reports under the FARMWISE cache contain derived statistics,
not a licence-free replacement for the source data. A published report must
identify its source dataset(s), request period, processing date, and applicable
attribution. Reports must also be reviewed for user-identifying request data.

### Server exports

CSV, JSON, map, and ZIP responses produced by the server must carry a
machine-readable provenance record containing at least:

- adapter and dataset name;
- provider and source URL;
- licence identifier and URL;
- access/retrieval date;
- transformations performed by FARMWISE;
- required attribution and disclaimer text.

FARMWISE must not apply Apache-2.0 to the data portion of such exports.

## Non-data and sensitive files

`user_storage.db`, `server/user_storage.db`, and any database under the
FARMWISE cache contain authentication/application state, not source data. They
must never be published, bundled, or uploaded to a data repository.

Logos, photographs, map tiles, and provider trademarks are outside this data
register unless explicitly listed. Permission to redistribute observations
does not automatically grant permission to reuse provider logos or third-party
base maps.

## Adding or updating a source

Before registering a new adapter or changing a dataset version:

1. Record the exact dataset page, provider, version, access date, and licence.
2. Save the required attribution and disclaimer text.
3. Confirm whether commercial use, adaptation, and redistribution are allowed.
4. Identify third-party inputs or jurisdiction-specific restrictions.
5. Document every persisted local path and whether it is bundled, cached, or
   temporary.
6. Add provenance metadata to API exports and data manifests.
7. If the licence is absent or ambiguous, mark the source **Conditional** and
   do not mirror or bundle it until written permission is obtained.

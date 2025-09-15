from datetime import datetime, timedelta

# Constants defining the current day and a date five days prior
CURRENT_DAY = datetime.now().strftime('%Y-%m-%d')
FIVE_BEFORE = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')

# Dictionary mapping API paths to their corresponding parameters
# Each entry contains a tuple with:
# - Spatial range (bounding box) NSEW
# - Temporal range (start and end dates)
# - Parameters (data types requested)
# - Temporal type (daily, monthly, yearly)
# - Spatial type (1 for point-based, 2 for grid-based)
# - Quality (1 for best quality)
# - NName
API_PATH_RANGES = {
    'API_readers.geosphere.geosphere': (
        ((49.0, 46.0, 17.2, 9.5),
         ('1950-01-01', CURRENT_DAY),
         ['temperature', 'precipitation'],
         'none',
         1,
         1)
    ),
    'API_readers.wetterdienst.wetterdienst_dwd': (
        ((54.98, 47.30, 15.02, 5.99),
         ('1950-01-01', CURRENT_DAY),
         ['temperature', 'precipitation'],
         'none',
         1,
         1)
    ),
    'API_readers.soilgrids.soilgrids_call': (  # 11 datasets
        ((71, 34, 45, -25),
         ('1951-01-01', CURRENT_DAY),
         ['soil'],
         'none',
         2,
         1)
    ),
    'API_readers.cds.cds_single_levels': (
        ((71, 34, 45, -25),
         ('1950-01-01', FIVE_BEFORE),
         ['temperature', 'precipitation'],
         'daily',
         2,
         1)
    ),
    'API_readers.cds.cds_vegetation': (
        ((71, 34, 45, -25),
         ('2000-01-01', '2018-12-31'),
         ['potential evaporation'],
         'deca-daily',
         2,
         1)
    ),
    'API_readers.imgw.imgw_api_synop_daily': (
        ((54.8396, 49.0023, 24.1453, 14.1226),
         ('1960-01-01', CURRENT_DAY),
         ['temperature', 'precipitation'],
         'daily',
         1,
         1)
    ),
    'API_readers.gios.gios_scraper': (
        ((54.8396, 49.0023, 24.1453, 14.1226),
         ('1995-01-01', '2020-12-31'),
         ['soil'],
         'yearly',
         1,
         1)
    ),
    'API_readers.imgw_hydro.imgw_api_hydro_daily': (
        ((54.8396, 49.0023, 24.1453, 14.1226),
         ('1951-01-01', CURRENT_DAY),
         ['surface water quantity'],
         'daily',
         1,
         1)
    ),
    'API_readers.corine.corine_read': (  # 6 datasets
        ((71, 34, 45, -25),
         ('1990-01-01', CURRENT_DAY),
         ['land cover'],
         'none',
         2,
         1)
    ),
    'API_readers.egdi.egdi_read_hc': (
        ((71, 34, 45, -25),
         ('1950-01-01', CURRENT_DAY),
         ['hydraulic conductivity'],
         'none',
         2,
         1)
    ),
    'API_readers.egdi.egdi_read_d10': (
        ((71, 34, 30, -10),
         ('1950-01-01', CURRENT_DAY),
         ['depth to watertable'],
         'none',
         2,
         1)
    ),
    'API_readers.hubeau.hubeau_wq_read': (
        ((51.09, 41.33, 9.56, -5.14),
         ('1969-01-01', CURRENT_DAY),
         ['groundwater quality'],
         'none',
         1,
         1)
    ),
    'API_readers.hubeau.hubeau_piezo_read_vbrgm': (
        ((51.09, 41.33, 9.56, -5.14),
         ('1950-01-01', CURRENT_DAY),
         ['groundwater quantity'],
         'none',
         1,
         1)
    ),
    'API_readers.hubeau.hubeau_sw_quality_read': (
        ((51.09, 41.33, 9.56, -5.14),
         ('1950-01-01', CURRENT_DAY),
         ['surface water quality'],
         'none',
         1,
         1)
    ),
}

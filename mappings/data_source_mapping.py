from datetime import datetime, timedelta

# Constants defining the current day and a date five days prior
CURRENT_DAY = datetime.now().strftime('%Y-%m-%d')
FIVE_BEFORE = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')

# Dictionary mapping API paths to their corresponding parameters
# Each entry contains a tuple with:
# - Spatial range (bounding box)
# - Temporal range (start and end dates)
# - Parameters (data types requested)
# - Temporal type (daily, monthly, yearly)
# - Spatial type (1 for point-based, 2 for grid-based)
# - Quality (1 for best quality)
API_PATH_RANGES = {
    'API_readers.cds.cds_single_levels': (
        ((71, 34, 45, -25),
         ('1950-01-01', FIVE_BEFORE),
         ('temperature', 'precipitation'),
         'daily',
         2,
         1)
    ),
    'API_readers.cds.cds_vegetation': (
        ((71, 34, 45, -25),
         ('2000-01-01', '2018-12-32'),
         ('potential evaporation'),
         'deca-daily',
         2,
         1)
    ),
    'API_readers.imgw.imgw_api_synop_daily': (
        ((54.8396, 49.0023, 24.1453, 14.1226),
         ('1960-01-01', CURRENT_DAY),
         ('temperature', 'precipitation'),
         'daily',
         1,
         1)
    ),
    'API_readers.gios.gios_scraper': (
        ((54.8396, 49.0023, 24.1453, 14.1226),
         ('1995-01-01', '2020-12-31'),
         ('soil'),
         'yearly',
         1,
         1)
    ),
    'API_readers.imgw_hydro.imgw_hydro_daily': (
        ((54.8396, 49.0023, 24.1453, 14.1226),
         ('1951-01-01', CURRENT_DAY),
         ('water quantity'),
         'daily',
         1,
         1)
    ),
    'API_readers.soilgrids.soilgrids_call': (  # 11 datasets
        ((71, 34, 45, -25),
         ('1951-01-01', CURRENT_DAY),
         ('soil'),
         'none',
         2,
         1)
    ),
    'API_readers.corine.corine_read': (  # 6 datasets
        ((71, 34, 45, -25),
         ('1990-01-01', CURRENT_DAY),
         ('land cover'),
         'none',
         2,
         1)
    ),
}

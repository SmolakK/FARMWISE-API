from datetime import datetime, timedelta

CURRENT_DAY = datetime.now().strftime('%Y-%m-%d')
FIVE_BEFORE = datetime.now() - timedelta(days=5)
# import path (key): spatial range, temporal range, parameters (value),
# temporal type (daily, monthly, yearly), spatial type (1 - point-based, 2 - grid-based), quality (1-best)
API_PATH_RANGES = {
    'API_readers.imgw.imgw_api_synop_daily': (
        ((54.8396, 49.0023, 24.1453, 14.1226),
         ('1960-01-01',CURRENT_DAY),
         ('temperature','precipitation','snow cover'),
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
    'API_readers.cds.cds': (
        ((71, 34, -25, 45),
         ('1950-01-01', FIVE_BEFORE),
         ('temperature','precipitation','snow cover'),
         'daily',
         1,
         1)
    )
}

from datetime import datetime

CURRENT_DAY = datetime.now().strftime('%Y-%m-%d')
# import path (key): spatial range, temporal range, parameters (value),
# temporal type (daily, monthly, yearly), spatial type, quality (1-best)
API_PATH_RANGES = {
    'API_readers.imgw.imgw_api_synop_daily': (
        ((54.8396, 49.0023, 24.1453, 14.1226),
         ('1960-01-01',CURRENT_DAY),
         ('temperature','precipitation','snow cover','sunshine','cloud cover','wind','pressure','humidity'),
         'daily',
         1,
         1)
    )
}

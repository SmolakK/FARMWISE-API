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
    'farmwise_api.adapters.API_readers.geosphere.geosphere': (
        ((49.0, 46.0, 17.2, 9.5),
         ('1950-01-01', CURRENT_DAY),
         ['temperature', 'precipitation'],
         'none',
         1,
         1)
    ),
    'farmwise_api.adapters.API_readers.wetterdienst.wetterdienst_dwd': (
        ((54.98, 47.30, 15.02, 5.99),
         ('1950-01-01', CURRENT_DAY),
         ['temperature', 'precipitation'],
         'none',
         1,
         1)
    ),
    'farmwise_api.adapters.API_readers.soilgrids.soilgrids_call': (  # 11 datasets
        ((71, 34, 45, -25),
         ('1951-01-01', CURRENT_DAY),
         ['soil'],
         'none',
         2,
         1)
    ),
    'farmwise_api.adapters.API_readers.cds.cds_single_levels': (
        ((71, 34, 45, -25),
         ('1950-01-01', FIVE_BEFORE),
         ['temperature', 'precipitation', 'soil humidity'],
         'daily',
         2,
         1)
    ),
    'farmwise_api.adapters.API_readers.imgw.imgw_api_synop_daily': (
        ((54.8396, 49.0023, 24.1453, 14.1226),
         ('1960-01-01', CURRENT_DAY),
         ['temperature', 'precipitation'],
         'daily',
         1,
         1)
    ),
    'farmwise_api.adapters.API_readers.gios.gios_scraper': (
        ((54.8396, 49.0023, 24.1453, 14.1226),
         ('1995-01-01', '2020-12-31'),
         ['soil'],
         'yearly',
         1,
         1)
    ),
    'farmwise_api.adapters.API_readers.imgw_hydro.imgw_api_hydro_daily': (
        ((54.8396, 49.0023, 24.1453, 14.1226),
         ('1951-01-01', CURRENT_DAY),
         ['surface water quantity'],
         'daily',
         1,
         1)
    ),
    'farmwise_api.adapters.API_readers.corine.corine_read': (  # 6 datasets
        ((71, 34, 45, -25),
         ('1990-01-01', CURRENT_DAY),
         ['land cover'],
         'none',
         2,
         1)
    ),
    'farmwise_api.adapters.API_readers.hubeau.hubeau_wq_read': (
        ((51.09, 41.33, 9.56, -5.14),
         ('1969-01-01', CURRENT_DAY),
         ['groundwater quality'],
         'none',
         1,
         1)
    ),
    'farmwise_api.adapters.API_readers.hubeau.hubeau_piezo_read_vbrgm': (
        ((51.09, 41.33, 9.56, -5.14),
         ('1950-01-01', CURRENT_DAY),
         ['groundwater quantity'],
         'none',
         1,
         1)
    ),
    # 'farmwise_api.adapters.API_readers.CHMI_Meteo.CHMI_meteo': (
    #     ((51.0557, 48.5518, 18.8592, 12.0907),
    #      ('1961-01-01', CURRENT_DAY),
    #      ['precipitation'],
    #      'daily',
    #      1,
    #      1)
    # ),
    'farmwise_api.adapters.API_readers.UA_sw_quality.ukrainian_surface_water': (
        ((52.3791, 44.3824, 40.2276, 22.1371),
         ('1950-01-01', CURRENT_DAY),
         ['surface water quality'],
         'monthly',
         1,
         1)
    ),
    'farmwise_api.adapters.API_readers.epa_ireland.epa_gw': (
        ((55.3822, 51.4476, -6.0024, -10.4781),
         ('1970-01-01', CURRENT_DAY),
         ['groundwater quantity'],
         'daily',
         1,
         1)
    ),
    'farmwise_api.adapters.API_readers.gios_gw.gios_gw': (
        ((54.8396, 49.0023, 24.1453, 14.1226),
         ('1990-01-01', CURRENT_DAY),
         ['groundwater quantity', 'groundwater quality'],
         'daily',
         1,
         1)
    ),
    'farmwise_api.adapters.API_readers.irish_meteo.irish_ms_daily': (
        ((55.3822, 51.4476, -6.0024, -10.4781),
         ('1941-01-01', '2025-12-31'),
         ['precipitation'],
         'daily',
         1,
         1)
    ),
    'farmwise_api.adapters.API_readers.hubeau.hubeau_sw_quality_read': (
        ((51.09, 41.33, 9.56, -5.14),
         ('1950-01-01', CURRENT_DAY),
         ['surface water quality'],
         'none',
         1,
         1)
    ),
    'farmwise_api.adapters.API_readers.EuroCropV2.EuroCropV2_read': (
        ((80, -21.7, 55.97, -61.95),
         ('2008-01-01', '2023-12-31'),
         ['land cover'],
         'none',
         1,
         1)
    ),
    'farmwise_api.adapters.API_readers.IFSGRID.IFSGRID_read': (
        ((80, -21.7, 55.97, -61.95),
        ('2020-01-01', CURRENT_DAY),
        [
            'livestock pressure',
            'surface water quality',
            'land cover',
            'agricultural structure'
        ],
        'none',
        1,
        1)
    ),
    'farmwise_api.adapters.API_readers.eea.eea_read': (
        ((73, 24, 73, -56),
         ('2018-01-01', CURRENT_DAY),
         ['environmental data (EEA)'],
         'none',
         1,
         1)
    ),
    # 'farmwise_api.adapters.API_readers.quadica.quadica_read': (
    #     ((55.1, 47.3, 15, 6),
    #      ('1950-01-01', '2015-12-31'),
    #      [
    #          'potential evaporation',
    #          'temperature',
    #          'precipitation',
    #          'surface water quantity',
    #          'surface water quality'
    #      ],
    #      'monthly/yearly',
    #      1,
    #      1)
    # ),
}

# Sources retained for provenance but intentionally excluded from dispatch.
# The CDS agroproductivity collection is still visible in the catalogue, but
# its API now returns HTTP 403 because downloads have been permanently retired.
DISABLED_API_SOURCES = {
    'farmwise_api.adapters.API_readers.egdi.egdi_read_hc': (
        'EGDI HOVER WP7 data is not licensed for redistribution. The adapter '
        'is excluded from public packages and dispatch.'
    ),
    'farmwise_api.adapters.API_readers.egdi.egdi_read_d10': (
        'EGDI HOVER WP7 data is not licensed for redistribution. The adapter '
        'is excluded from public packages and dispatch.'
    ),
    'farmwise_api.adapters.API_readers.correctiv.correctiv_read': (
        'CORRECTIV.Lokal research data is protected and has no confirmed '
        'redistribution permission. The source is excluded from dispatch.'
    ),
    'farmwise_api.adapters.API_readers.IFSGRID.IFSGRID_read': (
        'The current upstream IFSGRID archive does not match the pinned '
        'checksum. Dispatch is disabled until the replacement release is '
        'independently verified.'
    ),
}

# Sources available only to an informed local, private, non-commercial user.
# Server entry points always apply this mapping in addition to globally
# disabled sources. This is deliberately not controlled by request payloads.
PUBLIC_SERVER_DISABLED_SOURCES = {
    **DISABLED_API_SOURCES,
    'farmwise_api.adapters.API_readers.imgw.imgw_api_synop_daily': (
        'IMGW-PIB data is restricted to acknowledged private, '
        'non-commercial local use.'
    ),
    'farmwise_api.adapters.API_readers.imgw_hydro.imgw_api_hydro_daily': (
        'IMGW-PIB data is restricted to acknowledged private, '
        'non-commercial local use.'
    ),
}

PUBLIC_SERVER_API_PATH_RANGES = {
    source: ranges
    for source, ranges in API_PATH_RANGES.items()
    if source not in PUBLIC_SERVER_DISABLED_SOURCES
}

# Relative confidence assigned to each source during cross-source
# harmonization. The values are deliberately neutral until they are
# calibrated against reference datasets. A missing future source also
# receives a weight of 1.0 in the harmonization layer.
#
# Keep this dictionary separate from ``API_PATH_RANGES`` so the established
# six-element tuple format remains backwards compatible.
DATA_SOURCE_WEIGHTS = {
    api_path: 1.0
    for api_path in API_PATH_RANGES
}


# Harmonization method selected for each logical data type. New data types
# can be added here without changing the aggregation code. A caller can also
# override these values for a single ``read_data`` call.
#
# Available methods:
# - weighted_mean, mean, weighted_median, median
# - weighted_mode, mode, priority
# - min, max, sum
DATA_TYPE_HARMONIZATION_METHODS = {
    "default": "weighted_mean",
    "temperature": "weighted_mean",
    "precipitation": "weighted_mean",
    "soil": "weighted_mean",
    "soil humidity": "weighted_mean",
    "surface water quantity": "weighted_mean",
    "land cover": "weighted_mode",
    "hydraulic conductivity": "weighted_mean",
    "depth to watertable": "weighted_mean",
    "groundwater quality": "weighted_mean",
    "groundwater quantity": "weighted_mean",
    "surface water quality": "weighted_mean",
    "livestock pressure": "weighted_mean",
    "agricultural structure": "weighted_mean",
    "environmental data (EEA)": "weighted_mean",
}


# Aggregation used inside an individual adapter when several source records,
# stations, or raster pixels fall into the same S2 cell and time period. This
# policy is deliberately independent of cross-source harmonization above.
WITHIN_SOURCE_AGGREGATION_METHODS = {
    "default": "mean",
    "temperature": "mean",
    "precipitation": "mean",
    "soil": "mean",
    "soil humidity": "mean",
    "surface water quantity": "mean",
    "land cover": "mode",
    "hydraulic conductivity": "mean",
    "depth to watertable": "mean",
    "groundwater quality": "mean",
    "groundwater quantity": "mean",
    "surface water quality": "mean",
    "livestock pressure": "mean",
    "agricultural structure": "mean",
    "environmental data (EEA)": "mean",
}

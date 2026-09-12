from farmwise_api.adapters.mappings.units import GROUNDWATER_LEVEL_COLUMN

# EPA HydroNet publishes the daily mean groundwater level in metres above
# Ordnance Datum Malin (OSGM02); the source column name records that datum.
DATA_ALIASES = {
    'groundwater level [m OD Malin]': 'groundwater quantity'
}

# Global mapping of source columns to FARMWISE output names.
GLOBAL_MAPPING = {
    'groundwater level [m OD Malin]': GROUNDWATER_LEVEL_COLUMN
}

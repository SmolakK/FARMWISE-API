# list of parameters in the parameter column
PARAMETER_VALUES = [
    '2m_temperature', 'total_precipitation', 'snowfall',
    'volumetric_soil_water_layer_1', 'evaporation',
    '10m_u_component_of_wind', '10m_v_component_of_wind',
    'surface_pressure', 'surface_solar_radiation_downwards', "volumetric_soil_water_layer_1"
]

# selection list for parameters
PARAMETER_SELECTION = [
    '2m_temperature', 'total_precipitation', 'snowfall',
    'volumetric_soil_water_layer_1', 'evaporation',
    '10m_u_component_of_wind', '10m_v_component_of_wind',
    'surface_pressure', 'surface_solar_radiation_downwards', "volumetric_soil_water_layer_1"
]

# aliases for the data fields
DATA_ALIASES = {
    '2m_temperature': 'temperature',
    'total_precipitation': 'precipitation',
    "volumetric_soil_water_layer_1": 'soil humidity'
}

# CDS request names differ from the netCDF variable names the download
# contains; this links the two so each request maps to its output label.
NETCDF_SHORT_NAMES = {
    '2m_temperature': 't2m',
    'total_precipitation': 'tp',
    'volumetric_soil_water_layer_1': 'swvl1',
}

# global mapping of parameter codes to descriptions and units
GLOBAL_MAPPING = {
    't2m': "Temperature [°C]",
    'tp': "Precipitation total [mm]",
    'sf': "Snowfall [mm]",
    'swvl1': 'Soil moisture [%]',
    'e': "Evaporation [m]",
    'evavt': "Vegetation transpiration [m]",
    'u10': "U-component of wind [m/s]",
    'v10': "V-component of wind [m/s]",
    'sp': "Surface pressure [Pa]",
    'ssrd': "Surface solar radiation downwards [J/m^2]"
}

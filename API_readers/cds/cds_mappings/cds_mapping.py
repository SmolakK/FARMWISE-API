# list of parameters in the parameter column
PARAMETER_VALUES = ['2m_temperature', 'total_precipitation', 'snowfall',
                    'volumetric_soil_water_layer_1','evaporation']
PARAMETER_SELECTION = ['2m_temperature', 'total_precipitation', 'snowfall',
                       'volumetric_soil_water_layer_1','evaporation']
DATA_ALIASES = {'2m_temperature': 'temperature',
                'total_precipitation': 'precipitation',
                'snowfall': 'snow',
                'evaporation': 'evaporation',
                'volumetric_soil_water_layer_1': 'soil_moisture',}
GLOBAL_MAPPING = {'t2m': "Temperature [°C]",
                'tp': "Precipitation total [mm]",
                'sf': "Snowfall [mm]",
                  'swvl1': 'Soil moisture [%]',
                  'evavt': "Vegetation transpiration [m]",
                  "e": "Evaporation [m]"}

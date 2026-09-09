DATA_ALIASES = {
    'bdod': 'soil',
    'cec': 'soil',
    'cfvo': 'soil',
    'clay': 'soil',
    'nitrogen': 'soil',
    'phh2o': 'soil',
    'sand': 'soil',
    'silt': 'soil',
    'soc': 'soil',
    'ocs': 'soil',
    'ocd': 'soil',
}

GLOBAL_MAPPING = {
    'bdod': 'Bulk density [kg/dm3]',
    'cec': 'Cation exchange capacity at pH 7 [cmol(c)/kg]',
    'cfvo': 'Coarse fragments [%]',
    'clay': 'Clay content [%]',
    'nitrogen': 'Total nitrogen [g/kg]',
    'phh2o': 'Soil pH in H2O [pH]',
    'sand': 'Sand content [%]',
    'silt': 'Silt content [%]',
    'soc': 'Soil organic carbon [g/kg]',
    'ocs': 'Soil organic carbon stock [kg/m2]',
    'ocd': 'Organic carbon density [kg/m3]',
}

# SoilGrids maps store integer values with property-specific scale factors.
# Dividing by these values converts the rasters to the units above.
CONVERSION_DIVISORS = {
    'bdod': 100,
    'cec': 10,
    'cfvo': 10,
    'clay': 10,
    'nitrogen': 100,
    'phh2o': 10,
    'sand': 10,
    'silt': 10,
    'soc': 10,
    'ocs': 10,
    'ocd': 10,
}

DEPTH_MAPPING = {
            'bdod': 'bdod_0-5cm_mean',
           'cec': 'cec_0-5cm_mean',
           'cfvo': 'cfvo_0-5cm_mean',
           'clay': 'clay_0-5cm_mean',
           'nitrogen': 'nitrogen_0-5cm_mean',
           'phh2o': 'phh2o_0-5cm_mean',
           'sand': 'sand_0-5cm_mean',
           'silt': 'silt_0-5cm_mean',
           'soc': 'soc_0-5cm_mean',
           'ocs': 'ocs_0-30cm_mean',
           'ocd': 'ocd_0-5cm_mean',
}

# list of parameters in the parameter column
PARAMETER_VALUES = ['min_gwl','mean_gwl','max_gwl']

# selection list for parameters
PARAMETER_SELECTION = []

# aliases for the data fields
DATA_ALIASES = {}

# global mapping of parameter codes to descriptions and units
# CORRECTIV publishes monthly minimum, mean and maximum groundwater levels in
# metres above sea level (NHN). These are elevations, not depths - the old
# labels said "Depth" - and follow the shared groundwater-level convention.
GLOBAL_MAPPING = {
    'min_gwl': 'Minimum groundwater level [m a.s.l.]',
    'mean_gwl': 'Mean groundwater level [m a.s.l.]',
    'max_gwl': 'Maximum groundwater level [m a.s.l.]',
}

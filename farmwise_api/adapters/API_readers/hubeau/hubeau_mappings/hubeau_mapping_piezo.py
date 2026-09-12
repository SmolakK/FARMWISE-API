from farmwise_api.adapters.mappings.units import GROUNDWATER_LEVEL_COLUMN

# Hub'Eau "niveaux_nappes/chroniques" fields.
#   niveau_nappe_eau  - groundwater level in metres NGF (an elevation).
#   profondeur_nappe  - depth in metres below the local *measuring reference*,
#                       which is often not the ground surface, so it is neither
#                       a depth below ground nor an elevation. Not requested by
#                       the adapter; named here so it is never mistaken for one.
MAPPING = {'date_mesure': 'Timestamp',
           'niveau_nappe_eau': GROUNDWATER_LEVEL_COLUMN,
           'profondeur_nappe': 'Groundwater depth below measuring reference [m]'}

# BETA copy of .py file for GW (groundwater) but here for SW (surface water) QUALITY monitoring data
# TODO Those two mappings should probably be combined or simplified some way, but that would need some discussion (2025?) to adjust with other data sources & countries.

CODES = {
    # English Name: [Parameter Code based on the 'SANDRE' ref framwork of France]
    ## physico-chemical parameters:
    'pH': ['1302'], # (eng "Potential of Hydrogen", unitless "pH units")
    'Salinity': ['1303'],  # Electrical Conductivity
    ## major (mg/L):
    'Phosphorus': ['1350'],  # Phosphates (fr "Phosphore total" = eng "Total Phosphorus", in mg(P)/L)
    'Nitrate': ['1340'],  # Nitrates (in mg(NO3)/L)
    'Calcium': ['1374'], # (in mg(Ca)/L)
    'Potassium': ['1367'], # (in mg(K)/L)
    'Sodium': ['1375'], # (in mg(Na)/L)
    'Magnesium': ['1372'], # (in mg(Mg)/L)
    'Chlorine': ['1337'], # (in mg(Cl)/L)
    ## minor/trace/pesticides/pfas/etc. (µg/L):
    'Arsenic': ['1369'], # (µg/L)
    'Cadmium': ['1388'], # (µg/L)
    'Zinc': ['1383'], # (µg/L)
    'Lead': ['1382'], # (µg/L) (fr "Plomb", element "Pb")
    'Pesticides': ['6276'], # (fr "Somme de l'ensemble des pesticides analysés" = eng "Total sum of pesticides", in µg/L)
    'Perfluorodecane sulfonic acid (PFDS)': ['6550'],
    'Perfluoro-n-hexanoic acid (PFHxA)': ['5978'],
    'Perfluorodecanoic acid (PFDA)': ['6509'],
    'Perfluorododecanoic acid (PFDoA)': ['6507'],
    'Perfluoropentane sulfonic acid (PFPeS)': ['8738'],
    'Perfluorooctanoic acid (PFOA)': ['5347'],
    'Perfluorododecane sulfonic acid (PFDoDS)': ['8741'],
    'Perfluoro-n-nonanoic acid (PFNA)': ['6508'],
    'Perfluorononane sulfonic acid (PFNS)': ['8739'],
    'Perfluoroundecane sulfonic acid (PFUnDS)': ['8740'],
    'Perfluoro-n-butanoic acid (PFBA)': ['5980'],
    'Perfluorotridecanoic acid (PFTriDA)': ['6549'],

    #REPLACED this to have 1 parameter per key:    'Perfluorooctane sulfonate (PFOS)': [['6561'], ['6560']], # 2 parameters here!
    #SIMPLIFIED CODE is thus:
    'Perfluorooctane sulfonate (PFOS)': ['6561'],
    'Perfluorooctane sulfonic acid (PFOS)': ['6560'],

    'Perfluorohexane sulfonic acid (PFHxS)': ['6830'],
    'Perfluoro-n-pentanoic acid (PFPeA)': ['5979'],
    'Perfluoro-n-heptanoic acid (PFHpA)': ['5977'],
    'Perfluorotridecane sulfonic acid (PFTriDS)': ['8742'],
    'Perfluoroheptane sulfonic acid (PFHpS)': ['6542'],
    'Perfluorobutane sulfonic acid (PFBS)': ['6025'],
    'Perfluoro-n-undecanoic acid (PFUnA)': ['6510'],
    'Pentacosafluorotridecanoic acid (PFTriDA)': ['6549']
}

COLUMNS = ['lat', 'lon', 'Timestamp',
           'Acide pentacosafluorotridecanoique',
           'Acide perfluoro-dodecanoïque',
           'Acide perfluoro-n-butanoïque',
           'Acide perfluoro-n-heptanoïque',
           'Acide perfluoro-n-nonanoïque',
           'Acide perfluoro-n-pentanoïque',
           'Acide perfluoro-n-undecanoïque',
           'Acide perfluoro-octanoïque',
           'Acide perfluorodecane sulfonique',
           'Acide perfluorododecane sulfonique',
           'Acide perfluoroheptane sulfonique',
           'Acide perfluorononane sulfonique',
           'Acide perfluoropentane sulfonique',
           'Acide perfluorotridecane sulfonique',
           'Acide perfluoroundecane sulfonique',
           'Acide sulfonique de perfluorobutane',
           'Acide sulfonique de perfluorooctane',
           'Arsenic',
           'Cadmium',
           'Calcium',
           'Chlorures',
           'Conductivité à 25°C',
           'Magnésium',
           'Nitrates',
           'Perfluorohexanesulfonic acid',
           'Phosphore total',
           'Plomb',
           'Potassium',
           'Potentiel en Hydrogène (pH)',
           'Sodium',
           'Somme des pesticides totaux',
           'Sulfonate de perfluorooctane',
           'Zinc']

# To translate original French (ADES, Sandre reference) to English FARMWISE names
MAPPING = {
    'Acide pentacosafluorotridecanoique': 'SW Pentacosafluorotridecanoic acid (µg/L)',
    'Acide perfluoro-dodecanoïque': 'SW Perfluorododecanoic acid (µg/L)',
    'Acide perfluoro-n-butanoïque': 'SW Perfluorobutanoic acid (µg/L)',
    'Acide perfluoro-n-heptanoïque': 'SW Perfluoroheptanoic acid (µg/L)',
    'Acide perfluoro-n-nonanoïque': 'SW Perfluorononanoic acid (µg/L)',
    'Acide perfluoro-n-pentanoïque': 'SW Perfluoropentanoic acid (µg/L)',
    'Acide perfluoro-n-undecanoïque': 'SW Perfluoroundecanoic acid (µg/L)',
    'Acide perfluoro-octanoïque': 'SW Perfluorooctanoic acid (µg/L)',
    'Acide perfluorodecane sulfonique': 'SW Perfluorodecane sulfonic acid (µg/L)',
    'Acide perfluorododecane sulfonique': 'SW Perfluorododecane sulfonic acid (µg/L)',
    'Acide perfluoroheptane sulfonique': 'SW Perfluoroheptane sulfonic acid (µg/L)',
    'Acide perfluorononane sulfonique': 'SW Perfluorononane sulfonic acid (µg/L)',
    'Acide perfluoropentane sulfonique': 'SW Perfluoropentane sulfonic acid (µg/L)',
    'Acide perfluorotridecane sulfonique': 'SW Perfluorotridecane sulfonic acid (µg/L)',
    'Acide perfluoroundecane sulfonique': 'SW Perfluoroundecane sulfonic acid (µg/L)',
    'Acide sulfonique de perfluorobutane': 'SW Perfluorobutane sulfonic acid (µg/L)',

    'Acide sulfonique de perfluorooctane': 'SW Perfluorooctane sulfonic acid (mµg/L)', # TODO maybe 'mµg/L' is wrong units? In ADES database = "µg/L"
    'Sulfonate de perfluorooctane': 'SW Perfluorooctane sulfonate (mµg/L)',            # TODO maybe 'mµg/L' is wrong units? In ADES database = "µg/L"

    'Arsenic': 'SW Arsenic (µg/L)',
    'Cadmium': 'SW Cadmium (µg/L)',
    'Calcium': 'SW Calcium (mg/L)',
    'Chlorures': 'SW Chlorides (mg/L)',
    'Conductivité à 25°C': 'SW Conductivity at 25°C (µS/cm)',
    'Magnésium': 'SW Magnesium (mg/L)',
    'Nitrates': 'SW Nitrates (mg/L)',
    'Perfluorohexanesulfonic acid': 'SW Perfluorohexanesulfonic acid (µg/L)',
    'Phosphore total': 'SW Total Phosphorus (mg/L)',
    'Plomb': 'SW Lead (µg/L)',
    'Potassium': 'SW Potassium (mg/L)',
    'Potentiel en Hydrogène (pH)': 'SW Hydrogen Potential (pH)',
    'Sodium': 'SW Sodium (mg/L)',
    'Somme des pesticides totaux': 'SW Total Pesticides (µg/L)',
    'Sulfonate de perfluorooctane': 'SW Perfluorooctane sulfonate (µg/L)',
    'Zinc': 'SW Zinc (µg/L)'
}

PARAMETERS_MAPPING = {
    'phosphorus': CODES['Phosphorus'],
    'nitrate': CODES['Nitrate'],
    'heavy metals': [CODES['Arsenic'], CODES['Cadmium'], CODES['Zinc'], CODES['Lead']],
    'salinity': CODES['Salinity'],
    'calcium': CODES['Calcium'],
    'potassium': CODES['Potassium'],
    'sodium': CODES['Sodium'],
    'magnesium': CODES['Magnesium'],
    'ph': CODES['pH'],
    'chlorine': CODES['Chlorine'],
    'pfas': [
        CODES['Perfluorooctane sulfonate (PFOS)'],
        CODES['Perfluorooctane sulfonic acid (PFOS)'],
        CODES['Perfluoro-n-hexanoic acid (PFHxA)'],
        CODES['Perfluoro-n-nonanoic acid (PFNA)'],
        CODES['Perfluorohexane sulfonic acid (PFHxS)'],
    ],
    'pesticides': CODES['Pesticides'],
    'surface water quality': [x[0] for x in CODES.values()] # SW specific id here!
}

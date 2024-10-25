import requests
import pandas as pd
from hubeau_mappings.hubeau_mapping_wq import MAPPING, CODES, PARAMETERS_MAPPING
from utils.coordinates_to_cells import prepare_coordinates
import warnings
from utils.interpolate_data import interpolate
from utils.data_operators import flatten_list


def read_data(spatial_range, time_range, data_range, level):
    """
    read_data((51.09, 41.33, 9.56, -5.14),('1950-01-01','1980-01-01'),['phosphorus'],8)

    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param time_range: A tuple containing the start and end timestamps defining the time range.
    :param data_range: A list of properties requested.
    :param level: S2Cell level.
    :return: A pandas DataFrame containing the processed data.
    """
    url = 'https://hubeau.eaufrance.fr/api/v1/qualite_nappes/analyses'

    north, south, east, west = spatial_range
    bbox = [west, south, east, north]  # Create bbox
    data_range = list(map(lambda x: x.lower(),data_range))
    data_requested = list([v for k, v in PARAMETERS_MAPPING.items() if k in data_range])  # get all requested codes
    data_requested = flatten_list(data_requested)

    all_analyses = []
    params = {
        'bbox': bbox,
        'date_debut_prelevement': time_range[0],
        'date_fin_prelevement': time_range[1],
        'code_param': ','.join(data_requested),
        'size': 10000,
        'page': 1
    }
    while True:
        response = requests.get(url, params=params)
        data = response.json()
        if not response.ok:
            break
        analyses = data['data']
        all_analyses.extend(analyses)
        # Check if there is a next page
        if data.get('next'):
            params['page'] += 1
        else:
            break

    df = pd.DataFrame(all_analyses)
    df = df[['latitude', 'longitude', 'nom_param', 'resultat', 'symbole_unite','date_debut_prelevement']]
    df = df.drop_duplicates()
    df = pd.pivot_table(df,index=['latitude', 'longitude', 'date_debut_prelevement'],
         columns='nom_param',
         values=['resultat','symbole_unite'],
         aggfunc={'resultat': 'mean', 'symbole_unite': lambda x: x.mode().iloc[0]}).reset_index()
    df = df.rename({'latitude':'lat','longitude':'lon','date_debut_prelevement':'Timestamp'},axis=1)

    phosphore_column = [x for x in df.columns if "Phosphore total" in x]
    if len(phosphore_column) > 0:  # P2O5 to P
        df[('resultat', 'Phosphore total')][df[('symbole_unite', 'Phosphore total')] == 'mg(P2O5)/L'] = \
        df[('resultat', 'Phosphore total')][df[('symbole_unite', 'Phosphore total')] == 'mg(P2O5)/L'] * 0.436

    df = df[[x for x in df.columns if 'unite' not in x[0]]]  # drop units
    df = df.droplevel(0, axis=1)  # clear columns
    df.columns = ['lat','lon','Timestamp'] + list(df.columns[3:])

    df = df.rename(MAPPING, axis=1)  # Map to English names

    # To S2CELLs
    df = prepare_coordinates(df, spatial_range, level)
    original_size = df.shape[0]
    df = df.groupby(['S2CELL', 'Timestamp']).mean()
    if original_size != df.shape[0]:
        warnings.warn("Some data were aggregated")

    # Resample days
    df.reset_index(inplace=True)
    df.Timestamp = pd.to_datetime(df.Timestamp)
    df = df.set_index("Timestamp").groupby('S2CELL').resample('1D').first()
    df = df.drop('S2CELL',axis=1)
    df[['lat','lon']] = df[['lat','lon']].ffill()
    df = df.reset_index()

    # Data interpolation
    if level >= 10:
        df = interpolate(df, spatial_range, level)
        df = df.reset_index().rename({'level_0': 'S2CELL', 'level_1': 'Timestamp'}, axis=1)
    else:
        df = df.drop(['lat', 'lon'], axis=1)

    # Pivot the DataFrame
    df = df.pivot_table(index='Timestamp', columns='S2CELL')

    return df

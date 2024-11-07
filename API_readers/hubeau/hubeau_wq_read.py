# TODO DEVEL ***************** ici Temporaire, car je teste ce script qui est 2 niveaux ss-dossiers > la racine FARMWISE !
# Ajouter le chemin du dossier parent au sys.path
import sys
import os
if True:
    print(os.path.abspath(__file__))
    add_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) #+ r"\API_readers\hubeau"
    print(add_path)
    sys.path.append(add_path)
    #sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    #print(os.getcwd())

import requests
import json
import pandas as pd
from API_readers.hubeau.hubeau_mappings.hubeau_mapping_wq import MAPPING, CODES, PARAMETERS_MAPPING
from utils.coordinates_to_cells import prepare_coordinates
import warnings
from utils.interpolate_data import interpolate
from utils.data_operators import flatten_list

#import API_readers.hubeau.hubeaupyutils as hub
import hubeaupyutils as hub


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

    #NO MORE NEEDED: north, south, east, west = spatial_range
    #NO MORE NEEDED: bbox = [west, south, east, north]  # Create bbox

    # Get all possible parameters, if None is specified:
    if data_range is None:
        data_range = list([k for k, v in PARAMETERS_MAPPING.items() if True])  # get all possible mapping keys

    data_range = list(map(lambda x: x.lower(),data_range))
    data_requested = list([v for k, v in PARAMETERS_MAPPING.items() if k in data_range])  # get all requested codes
    data_requested = flatten_list(data_requested)

    # Remove duplicates by converting to a set (and back to list):
    data_requested = list(set(data_requested))
    # TODO TMP Marc to test fast the case of param Phosphorus ('Phosphore total') only: data_requested = 1350
    # print(data_requested)
    # print(len(data_requested))

    print("DOWNLOADING: HubEau (France) GW Quality data")

    print("Selecting France GW monitoring points inside the Spatial Range...")
    coors = pd.read_csv(r'API_readers/hubeau/constants/farmwise_gwquality_points_sel_for_hubeau.csv')
    coordinates = prepare_coordinates(coordinates=coors, spatial_range=spatial_range, level=level)
    if coordinates is None:
        return None

    #TMP DEVEL faster tests: #<<<< TMP
    coordinates = coordinates.head(3)  #<<<< TMP
    print(coordinates) #<<<< TMP

    print("  {} points are selected for this query".format(len(coordinates)))

    # Not required for now:
    gwquality_params_df = pd.read_csv(r'API_readers/hubeau/constants/farmwise_gwquality_parameters.csv', dtype=str)
    # So even the code_param column (e.g., 1340 for Nitrates) will be imported as text (type str) here (in Python).
    #print(gwquality_params_df)

    accum_dfs = [] # to accumulate a LIST of dataframes that we get for the N points

    # params = {
    #     'bbox': bbox,
    #     'date_debut_prelevement': time_range[0],
    #     'date_fin_prelevement': time_range[1],
    #     'code_param': ','.join(data_requested),
    #     'size': 10000,
    #     'page': 1
    # }
    # while True:
    #     response = requests.get(url, params=params)
    #     data = response.json()
    #     if not response.ok:
    #         break
    #     analyses = data['data']
    #     all_analyses.extend(analyses)
    #     # Check if there is a next page
    #     if data.get('next'):
    #         params['page'] += 1
    #     else:
    #         break

    pt_ids_lst = coordinates["code_bss_new"].to_list()
    print(pt_ids_lst)

    # he_params = {
    #     'bss_id': 'UPDATED.IN.LOOP',
    #     'date_debut_prelevement': time_range[0],
    #     'date_fin_prelevement': time_range[1],
    #     'code_param': ','.join(data_requested),
    #     'size': 10000,
    #     'page': 1
    # }

    # TODO : Define a var he_req_fields = [] to redure the nb of columns of data to get and thus make the get ops faster!!!
    he_req_fields = ['bss_id', 'latitude', 'longitude', 'code_param', 'nom_param', 'date_debut_prelevement', 'resultat', 'symbole_unite','code_remarque_analyse']

    api = hub.init_api('groundwater_qual')

    for pt_id in pt_ids_lst:
        print(pt_id)
        # he_params['bss_id'] = bss_id
        # print(he_params)

        df = api.get_data(code_station=pt_id, code_param=data_requested, fields=he_req_fields, only_valid_data=True) #(because the pkg uses the pseudo 'code_station' instead )
        df = df.rename_axis('date_debut_prelevement').reset_index() # to have back the original name for that column (since hub pkg renamed it to date as put it as the index)
        print(df.head(3))

        #print(df.columns.names())
        # print(df)
        # print(len(df))

        # response = requests.get(url, params=he_params)
        # # URL max length is about 420 chararacters, with the full list of 35 GW quality parameters,
        # # which is okay: below the Max URL length for HubEau <= 2083 chararacters.

        # print(response.url)
        # print(response.status_code)

        # if not response.ok and response.status_code == 200:
        #     break
        #     # TODO here we should develop some protections to deal with errors, e.g., to try again...
        #     # Deal with the different response.status_code, 
        #     # and also maybe add a try() on the requests.get()...?

        # resp = response.json()
        # # resp is a dict with: dict_keys(['count', 'first', 'last', 'prev', 'next', 'api_version', 'data'])

        # analyses = resp['data']
        # print(json.dumps(resp, indent=4, sort_keys=True))

        # # print(analyses.head(5))
        # # print(len(analyses))
        # return(999)

        accum_dfs.append(df)

        #exit() # TMP DEVEL to stop after 1st iteration of the for loop.

    # Finally create a DataFrame from the list of accumulated df's:
    # based on: https://stackoverflow.com/questions/27929472/improve-row-append-performance-on-pandas-dataframes
    df = pd.concat(accum_dfs, sort=False)

    print(df)
    print(len(df))
    print(df['bss_id'].unique())
    
    print(df.columns)
    #NOT NEEDED?: df.set_index(['latitude', 'longitude', 'date_debut_prelevement'])

    #NO MORE: df = pd.DataFrame(all_analyses)

    df = df[['latitude', 'longitude', 'nom_param', 'resultat', 'symbole_unite','date_debut_prelevement']] # TODO (Marc) ADD 'code_remarque_analyse' !!
    df = df.drop_duplicates()
    df = pd.pivot_table(df,index=['latitude', 'longitude', 'date_debut_prelevement'],
         columns='nom_param',
         values=['resultat','symbole_unite'],
         aggfunc={'resultat': 'mean', 'symbole_unite': lambda x: x.mode().iloc[0]}).reset_index()
    df = df.rename({'latitude':'lat','longitude':'lon','date_debut_prelevement':'Timestamp'},axis=1)

    # TODO Marc please CHECK if this works!!? Not sure it does: 'resultat' column no more existing I think??
    phosphore_column = [x for x in df.columns if "Phosphore total" in x]
    if len(phosphore_column) > 0:  # P2O5 to P
        df[('resultat', 'Phosphore total')][df[('symbole_unite', 'Phosphore total')] == 'mg(P2O5)/L'] = \
        df[('resultat', 'Phosphore total')][df[('symbole_unite', 'Phosphore total')] == 'mg(P2O5)/L'] * 0.436

    df = df[[x for x in df.columns if 'unite' not in x[0]]]  # drop units
    df = df.droplevel(0, axis=1)  # clear columns
    df.columns = ['lat','lon','Timestamp'] + list(df.columns[3:])

    print(df)
    return(True) # MARC working here last!

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
    if level >= 18:
        df = interpolate(df, spatial_range, level)
        df = df.reset_index().rename({'level_0': 'S2CELL', 'level_1': 'Timestamp'}, axis=1)
    else:
        df = df.drop(['lat', 'lon'], axis=1)

    # Pivot the DataFrame
    df = df.pivot_table(index='Timestamp', columns='S2CELL')

    return df


if __name__ == "__main__":
    N = 49.0
    S = 47.0
    E = -2.0
    W = -5.0
    LEVEL = 8
    TIME_FROM = '2010-01-01'
    TIME_TO = '2023-12-31'
    #FACTORS = ['temperature','precipitation','vegetation_transpiration','soil_moisture']

    bounding_box = (N, S, E, W)
    level = LEVEL
    time_from = TIME_FROM
    time_to = TIME_TO
    #factors = FACTORS

    spatial_range = bounding_box

    # from datetime import datetime, timedelta
    # FIVE_BEFORE = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')

    time_range = (time_from, time_to)

    data_range = None #('var1','var2')

    print(spatial_range)
    print(time_range)
    print(data_range)

    print("\nTEST calling function read_data of hubeau_wq_read...")

    read_data(spatial_range,time_range,data_range,LEVEL)

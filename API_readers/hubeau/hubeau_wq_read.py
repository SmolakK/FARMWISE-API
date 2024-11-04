if __name__ == "__main__":
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

import requests
import json
import pandas as pd
from API_readers.hubeau.hubeau_mappings.hubeau_mapping_wq import MAPPING, CODES, PARAMETERS_MAPPING
from utils.coordinates_to_cells import prepare_coordinates
import warnings
from utils.interpolate_data import interpolate
from utils.data_operators import flatten_list

# Important reminder: "hubeaupyutils" is a library that must be installed running/using this API reader, cf. file "hubeaupyutils-main.tar.gz"
import hubeaupyutils as hub
from datetime import datetime

def read_data(spatial_range, time_range, data_range, level):
    """
    read_data((51.09, 41.33, 9.56, -5.14),('1950-01-01','1980-01-01'),['phosphorus'],8)

    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param time_range: A tuple containing the start and end timestamps defining the time range. 2 text dates (str) of format YYYY-mm-dd
    :param data_range: A list of GW quality parameters requested, e.g., ('nitrate', 'phosphorus', 'potassium', 'pesticides') (not case sensitive) (see PARAMETERS_MAPPING)
    :param level: S2Cell level.
    :return: A pandas DataFrame containing the processed data.
    """
    url = 'https://hubeau.eaufrance.fr/api/v1/qualite_nappes/analyses'

    #NO MORE NEEDED: north, south, east, west = spatial_range
    #NO MORE NEEDED: bbox = [west, south, east, north]  # Create bbox

    # Protection in case of bad type of argument data_range:
    # because without this conversion, next operations would fragment the string to a list of individual characters!
    if(isinstance(data_range, str)):
        data_range = [data_range]

    # Get all possible parameters, if None is specified:
    if data_range is None:
        data_range = list([k for k, v in PARAMETERS_MAPPING.items() if True])  # get all possible mapping keys

    # Protection: convert to lower case:
    data_range = list(map(lambda x: x.lower(),data_range))
    # Convert to set, to remove duplicates (if any):
    data_asked_raw_set = set(data_range) #(raw but after lower case)

    # Diagnostic info:
    print("Asked parameter names (data_range set, all made lower case) =")
    print(data_asked_raw_set)

    data_requested_keys_set = data_asked_raw_set & set(PARAMETERS_MAPPING.keys())

    # Diagnostic check:
    data_asked_not_recognized = data_asked_raw_set - set(data_requested_keys_set)
    # print(data_asked_raw_set)
    # print(data_requested)

    # Diagnostic info:
    print("Verified (recognized) parameter names (data_requested_keys_set) =")
    print(data_requested_keys_set)
    if(len(data_asked_not_recognized) > 0):
        print("NOT recognized parameter names (data_asked_not_recognized) =")
        print(data_asked_not_recognized)

    if(data_asked_raw_set.issubset(data_requested_keys_set)):
        print(" OK, all of the {} requested parameters are recognized by the API reader.".format(len(data_asked_raw_set)))
    else:
        print(" OOPS! {} of the {} requested parameters are recognized by the API reader.".format(len(data_asked_not_recognized), len(data_asked_raw_set)))

    # Get the parameter CODES, that will serve as parameter IDs for HubEau:
    data_requested_codes = list([v for k, v in PARAMETERS_MAPPING.items() if k in data_requested_keys_set])  # get all requested CODES
    data_requested_codes = flatten_list(data_requested_codes)
    # Remove duplicates by converting to a set (and back to list):
    data_requested_codes = list(set(data_requested_codes))

    # TODO TMP Marc to test fast the case of param Phosphorus ('Phosphore total') only: data_requested = 1350
    # print(data_requested)
    # print(len(data_requested))

    # Diagnostic info:
    print("Parameter CODES that will be requested in HubEau queries (data_requested_codes) =")
    print(data_requested_codes)

    if len(data_requested_codes) == 0:
        return None

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

    # Date (extraction period) parameters for the HubEau query:
    # (input argument should be text dates YYYY-mm-dd, else datetime/timestamp compatible types)
    he_period_bounds = [None, None] # (list, not tuple)
    # Remark (reminder): An internal function of lib hubeaupyutils, _check_parameters(**kwargs), will remove unused (empty: =None or ="") kw arguments.
    #
    #  Start of period:
    if(isinstance(time_range[0], str)):
       he_period_bounds[0] = time_range[0]
    else:
       he_period_bounds[0] = "{:%Y-%m-%d}".format(time_range[0])
    #
    #  End of period:
    if(isinstance(time_range[1], str)):
       he_period_bounds[1] = time_range[1]
    else:
       he_period_bounds[1] = "{:%Y-%m-%d}".format(time_range[1])

    api = hub.init_api('groundwater_qual')

    for pt_id in pt_ids_lst:
        print(pt_id)
        print("he_period_bounds =")
        print(he_period_bounds)
        # he_params['bss_id'] = bss_id
        # print(he_params)

        # See this online help of HubEau for documentation on the available query parameters -> as kwargs here :
        # https://hubeau.eaufrance.fr/page/api-qualite-nappes#/qualite-nappes/analyses
        df = api.get_data(code_station=pt_id, date_debut_prelevement=he_period_bounds[0], date_fin_prelevement=he_period_bounds[1], code_param=data_requested_codes, fields=he_req_fields, only_valid_data=True) #(because the pkg uses the pseudo 'code_station' instead )
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

    ##########################################################################################################################
    #TMP DEVEL for DEBUGGING pivot_table Issue with the aggfunc argument:
    print(os.getcwd())
    df.to_csv(r"""API_readers\hubeau\tmp_check_df.csv""", sep=";", encoding="Windows-1252")
    ##########################################################################################################################

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
    if level >= 10:
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
    TIME_FROM = '2020-01-01'
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

    data_range = ('roger') #None #('var1','var2')

    print(spatial_range)
    print(time_range)
    print(data_range)

    print("\nTEST calling function read_data of hubeau_wq_read...")

    read_data(spatial_range,time_range,data_range,LEVEL)

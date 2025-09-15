import pandas as pd
from API_readers.hubeau.hubeau_mappings.hubeau_mapping_sw_quality import MAPPING, CODES, PARAMETERS_MAPPING
from utils.coordinates_to_cells import prepare_coordinates
import warnings
from utils.data_operators import flatten_list
import asyncio

# Important reminder: "hubeaupyutils" is a library that must be installed running/using this API reader, cf. file "hubeaupyutils-main.tar.gz"
import hubeaupyutils as hub


async def fetch_data(api, pt_id, he_period_bounds, data_requested_codes, verbose_level):
    """
    Asynchronous function to fetch data for a specific point.
    """
    if verbose_level >= 1:
        print(f"Fetching data for point ID: {pt_id} with parameters: {data_requested_codes}")

    try:
        # TMP DEV TEST here we test getting info on the monitoring STATION (before the Time Series data):
        # dftest = api.get_station(code_station=pt_id)
        # print(dftest)
        
        # Fetch data using the hub API
        df = await asyncio.to_thread(
            api.get_data,
            code_station=pt_id,
            code_parametre=data_requested_codes,
            code_support='3', # Code 3 = 'Eau' (only data for water)
            # Note that start_date, end_date arguments are not yet defined in api(HubQualRiv).get_data function,
            # that is why we use the HubEau online API official argument names here:
            date_debut_prelevement=he_period_bounds[0],
            date_fin_prelevement=he_period_bounds[1],
            # Ignore data qualified of Incorrect ou Uncertain:
            code_qualification='0,1,4'
            # NOT AVAILABLE in hub lib for this type of data: only_valid_data=True
        )

        # Ensure proper DataFrame formatting
        if not df.empty:
            df = df.rename_axis('date_debut_prelevement').reset_index()
            if verbose_level >= 2:
                print(f"Data fetched for point {pt_id}:")
                print(df.head())
        return df
    except Exception as e:
        if verbose_level >= 1:
            print(f"Error fetching data for point {pt_id}: {e}")
        return None


async def read_data(spatial_range, time_range, data_range, level, nmax_pts=None, verbose_level=0):
    """
    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param time_range: A tuple containing the start and end timestamps defining the time range. 2 text dates (str) of format YYYY-mm-dd
    :param data_range: A list of SW quality parameters requested, e.g., ('nitrate', 'phosphorus', 'potassium', 'pesticides') (not case sensitive) (see PARAMETERS_MAPPING)
    :param level: S2Cell level.
    :param nmax_pts: maximum number of points to select for data extraction (an optional limitation that may be used only during tests)
    :param verbose_level: level of details to write in the console (0: none; 1: some; >=2: lots of details)
    :return: A pandas DataFrame containing the processed data.
    """
    url = 'https://hubeau.eaufrance.fr/api/v2/qualite_rivieres/analyse_pc' # NOT USED IN THIS SCRIPT (but indireclty via hub)

    # NO MORE NEEDED: north, south, east, west = spatial_range
    # NO MORE NEEDED: bbox = [west, south, east, north]  # Create bbox

    # Protection in case of bad type of argument data_range:
    # because without this conversion, next operations would fragment the string to a list of individual characters!
    if isinstance(data_range, str):
        data_range = [data_range]

    # Get all possible parameters, if None is specified:
    if data_range is None:
        data_range = list([k for k, v in PARAMETERS_MAPPING.items() if True])  # get all possible mapping keys

    # Protection: convert to lower case:
    data_range = list(map(lambda x: x.lower(), data_range))
    # Convert to set, to remove duplicates (if any):
    data_asked_raw_set = set(data_range)  # (raw but after lower case)

    ################### PARAMETERS (preparing list of...) ###################

    # Diagnostic info:
    if (verbose_level >= 1):
        print("\nPARAMETERS (SW Quality)...\n")
        print("Asked parameter names (data_range set, all made lower case) =")
        print(data_asked_raw_set)

    data_requested_keys_set = data_asked_raw_set & set(PARAMETERS_MAPPING.keys())

    # Diagnostic check:
    data_asked_not_recognized = data_asked_raw_set - set(data_requested_keys_set)

    # Diagnostic info:
    if (verbose_level >= 1):
        print("Verified (recognized) parameter names (data_requested_keys_set) =")
        print(data_requested_keys_set)
        if (len(data_asked_not_recognized) > 0):
            print("NOT recognized parameter names (data_asked_not_recognized) =")
            print(data_asked_not_recognized)

        if (data_asked_raw_set.issubset(data_requested_keys_set)):
            print(" OK, all of the {} requested parameters are recognized by the API reader.".format(
                len(data_asked_raw_set)))
        else:
            print(" OOPS! {} of the {} requested parameters are recognized by the API reader.".format(
                len(data_asked_not_recognized), len(data_asked_raw_set)))

    # Get the parameter CODES, that will serve as parameter IDs for HubEau:
    data_requested_codes = list(
        [v for k, v in PARAMETERS_MAPPING.items() if k in data_requested_keys_set])  # get all requested CODES
    data_requested_codes = flatten_list(data_requested_codes)
    # Remove duplicates by converting to a set (and back to list):
    data_requested_codes = list(set(data_requested_codes))

    # Diagnostic info:
    if (verbose_level >= 1):
        print("Parameter CODES that will be requested in HubEau queries (data_requested_codes) =")
        print(data_requested_codes)

    # Exiting here if there is no valid parameter code:
    if len(data_requested_codes) == 0:
        return None

    ################### POINTS (preparing list of...) ###################

    if (verbose_level >= 1):
        print("\nPOINTS...\n")
        print("Selecting France SW monitoring STATIONS (points x long.,y lat.) inside the Spatial Range...")

    coords = pd.read_csv(r'API_readers/hubeau/constants/farmwise_sw_quality_stations_sel_for_hubeau.csv')
    # Renaming to make compatible with the function:
    coords.rename(columns={'x_longitude':'lon', 'y_latitude':'lat'}, inplace=True)
    coordinates = prepare_coordinates(coordinates=coords, spatial_range=spatial_range, level=level)

    # Exiting here if no point was selected (0 point found in the specified spatial_range):
    if coordinates is None:
        return None

    # Optional limitation for faster tests (only!):
    if nmax_pts is not None:
        if (verbose_level >= 1):
            print(
                "  {} points INITIALLY found (pre-selected) based on the constants list & spatial_range constraint".format(
                    len(coordinates)))
        coordinates = coordinates.head(nmax_pts)

    if (verbose_level >= 1):
        print("  {} points are selected for this query".format(len(coordinates)))

    # List of point IDs to iterate (loop) over:
    pt_ids_lst = coordinates["code_station"].to_list()
    if (verbose_level >= 2):
        print(pt_ids_lst)

    ################### Preparing the GET arguments... ###################

    if (verbose_level >= 2):
        print("GET (Preparing the arguments for the api.get_data() calls...")

    # LIST of dataframes to accumulate what we get for the N points (inside the loop below)
    accum_dfs = []

    # Date (extraction period) parameters for the HubEau query:
    # (input argument should be text dates YYYY-mm-dd, else datetime/timestamp compatible types)
    he_period_bounds = [None, None]  # (list, not tuple)
    # Remark (reminder): An internal function of lib hubeaupyutils, _check_parameters(**kwargs), will remove unused (empty: =None or ="") kw arguments.
    #
    #  Start of period:
    if (isinstance(time_range[0], str)):
        he_period_bounds[0] = time_range[0]  # (text date: YYYY-mm-dd)
    else:
        he_period_bounds[0] = "{:%Y-%m-%d}".format(time_range[0])
    #
    #  End of period:
    if (isinstance(time_range[1], str)):
        he_period_bounds[1] = time_range[1]  # (text date: YYYY-mm-dd)
    else:
        he_period_bounds[1] = "{:%Y-%m-%d}".format(time_range[1])

    if (verbose_level >= 1):
        print("\nDOWNLOADING: HubEau (France) SW Quality (Naïades) data...\n")

    # Initialisation of the hubeaupyutils API object
    api = hub.init_api('river_qual', version=2) # (Important to use V2!)

    # Prepare tasks for asynchronous data fetching
    tasks = [
        fetch_data(api, pt_id, he_period_bounds, data_requested_codes, verbose_level)
        for pt_id in pt_ids_lst
    ]
    responses = await asyncio.gather(*tasks)

    # Collect and process responses
    accum_dfs = [df for df in responses if (df is not None) and (not df.empty)]

    if not accum_dfs:
        return None

    if (verbose_level >= 2):
        print("Number of dataframes obtained (before concatenating them): len(accum_dfs) =")
        print(len(accum_dfs))

    df = pd.concat(accum_dfs, ignore_index=True)
    # TODO (not essential, 2025 maybe?):
    # Could prevent a warning here, by pre-selecting only the useful columns inside accum_dfs creation from responses...
    # ...the warning being related to "empty or all-NA columns when determining the result dtypes".

    # Renaming to keep a Python code more similar to that for GW quality data...:
    df.rename(columns={'libelle_parametre':'nom_param', 'code_station':'point_id', 'code_parametre':'code_param'}, inplace=True)

    # If no data, there is nothing else to do:
    if (len(df) == 0):
        return None

    if (verbose_level >= 1):
        print("\nPREVIEW of the whole data table (concatenation of all points' data frames):")
        print(df)

    if (verbose_level >= 2):
        print("\nList of all {} point IDs ('code_station'):".format(df['point_id'].nunique()))
        print(df['point_id'].unique())
        print("\nList of all column names (before further processing of the DataFrame):")
        print(df.columns.to_list())

    # NOT NEEDED anymore I think: df.set_index(['latitude', 'longitude', 'date_debut_prelevement'])

    # Selecting columns to discard some columns that are not used anymore (for now)
    df = df[['point_id', 'latitude', 'longitude', 'code_param', 'nom_param', 'resultat', 'symbole_unite', 'code_remarque', 'date_debut_prelevement', 'libelle_support', 'libelle_fraction']]
    # Remarks:
    # * The libelle_fraction field is kept temporarily just to allow a more detailed inspection of the data we got, although all "fractions" are kept.
    # * TODO (Marc) We should USE the 'code_remarque' info ... but HOW, and what to do then in .pivot_table() !? (TO discuss in 2025)
    #   This 'code_remarque' --> 'mnemo_remarque' text field, indicates whether the result is quantitative (>LOQ) or censored data (<LOQ or <LOD), or other special cases.

    # Removing fully redundant data rows, if any (altough it should not)
    df = df.drop_duplicates()

    # DEVELOPER NOTE: I have chosen to aggregate with point_id, in case there would be unexcepted variability
    # in the point's coordinate values (although it should not).
    # Still we assume that for a given point (point_id) we should always get the same lat,long (unique) coordinate values,
    # so that we can get a point's coordinates from its first values of 'latitude' and 'longitude' (see below).

    # This reference DataFrame of point coordinates (df_ref_coords) will be used later to merge those coordinates back
    # with the point they belong to. That is used here because we prefer to aggregate by point_id rather than lat,long.
    df_ref_coords = df[['point_id', 'latitude', 'longitude']].rename(
        {'point_id': 'point_id', 'latitude': 'lat', 'longitude': 'lon'}, axis=1).groupby(
        'point_id').first()  # (by key = "point_id")
    if (verbose_level >= 2):
        print("\nPOINT COORDINATES ref. DataFrame df_ref_coords =")
        print(df_ref_coords)

    # Aggregating the data by Point ID and by Date,
    # with aggregated value = mean of raw values, and info on measurement units = first (heading) most frequent (mode) text info)
    df = pd.pivot_table(df, index=['point_id', 'date_debut_prelevement'],
                        columns='nom_param',
                        values=['resultat', 'symbole_unite'],
                        aggfunc={'resultat': 'mean', 'symbole_unite': lambda x: x.mode().head(
                            1)}).reset_index()  # (protected in case of symbole_unite all empty = None)
    df = df.rename({'point_id': 'point_id', 'date_debut_prelevement': 'Timestamp'}, axis=1)

    # Reminder of the DataFrame format at this stage:
    # It looks like this (example):
    #
    #                point_id  Timestamp resultat                 symbole_unite
    #    nom_param                        Nitrates Phosphore total      Nitrates Phosphore total
    #    0          BSS000QSNW 2020-05-19     64.0             NaN     mg(NO3)/L             NaN
    #    1          BSS000QSNW 2020-06-03     64.0           0.080     mg(NO3)/L         mg(P)/L
    #
    # That is, the columns have two levels: two outer 'groups' (resultat, symbole_unite) and
    # as many inner columns inside those groups as there are parameters (here = 2 substances).

    # TODO Marc please CHECK if relevant for Naiades SW quality data?? First tests suggest that symbole_unite = mg/L (no molecule detail) for 'Phosphore total' (code 1350).
    phosphore_column = [x for x in df.columns if "Phosphore total" in x]
    if len(phosphore_column) > 0:  # P2O5 to P
        df.loc[df.loc[:, ('symbole_unite', 'Phosphore total')] == 'mg(P2O5)/L', (
        'resultat', 'Phosphore total')] *= 0.436  # (inplace multiplication)
        df.loc[df.loc[:, ('symbole_unite', 'Phosphore total')] == 'mg(P2O5)/L', (
        'symbole_unite', 'Phosphore total')] = "mg(P)/L"  # (updating the unit)

    # Simplifying the DataFrame:
    # TODO (TO discuss in 2025) Marc thinks it would be better & more robust workflow if we included the units info in the output. But for now, it is removed here:
    df = df[[x for x in df.columns if 'unite' not in x[0]]]  # drop columns having a name "*unite*"
    df = df.droplevel(0, axis=1)  # clear the "resultat" columns' grouping (multi-indexing) to get normal columns
    df.columns = ['point_id', 'Timestamp'] + list(df.columns[
                                                  2:])  # setting names for the first columns and use the others' (Reminder: column index starts at [0])

    df = df.rename(MAPPING,
                   axis=1)  # Map the values-of-interest columns with Parameter names, to English FARMWISE-defined parameter names

    # Computing S2CELLs from the point coordinates:
    tmp_prep_coords_df = prepare_coordinates(df_ref_coords, spatial_range, level)
    # TODO QUESTION TO ASK ASAP: Should we use the input argument 'level' here (also) or only later in a "Data interpolation" step (not clear yet by the way; see below)

    # Merging the DataFrame of obtained data, with the coordinates(lat,lon)+S2CELL table, to join those columns:
    df = pd.merge(df, tmp_prep_coords_df, on='point_id', how='left')

    # Spatial aggregation of the measured values, by S2CELL (of the level specified in function's arguments)
    original_size = df.shape[0]  # for later diagnostic info display
    df = df.groupby(['S2CELL', 'Timestamp']).agg({
        'point_id': lambda x: x.nunique(),
        # to help understand the degree of upscaling (averaging) that took place (if a coarse S2CELL level is used)
        'lat': 'mean',  # average point coordinates if >1 points in that S2CELL
        'lon': 'mean',  # ...
        **{col: 'mean' for col in df.columns if col not in ['point_id', 'Timestamp', 'lat', 'lon', 'S2CELL']}
        # mean value for each parameter (column of data)
    }).rename({'point_id': 'nb_points'}, axis=1)

    # Diagnostic message:
    if (verbose_level >= 0):  # (show it whatever the verbose_level is, because it is an important User Warning)
        if original_size != df.shape[0]:
            warnings.warn("Some data were aggregated")

    # Resample days
    df.reset_index(inplace=True)
    df = df.set_index("Timestamp").groupby('S2CELL').resample('1D').first()
    # TODO QUESTION: What is this for? Is it really important that the time series in df have a regular 1-day time step here???

    df = df.drop('S2CELL',
                 axis=1)  # to remove the redundant not-index S2CELL column (now that a duplicate is included in the multi-index)
    df = df.reset_index()
    df.Timestamp = pd.to_datetime(df.Timestamp).dt.date

    # TODO QUESTION: Marc does not feel comfortable with this fill operation! Actually, for each combination of ['S2CELL', 'Timestamp'],
    # there can be a variable number of points with data available for a given parameter, so that the calculated AVERAGE lat,lon coords
    # for the current S2CELL can vary!
    # ==> Thus, I would like to know more about the Data Interpolation step that followed this (further below), which may be the reason
    # for this fill operation I guess!? And if we all agree to abandon "Data Interpolation" for the HubEau POINT-scale time-series data,
    # I will then suggest that we abandon that fill operation, as well as the daily resample to regular time step (see above)...
    # ===========> TODO to DISCUSS ASAP... although if we do abandon Data Interpolation, those columns do not play any role thereafter.

    # Removal of the diagnostic column "nb_points", to simplify next steps, notably the call to interpolate():
    # TODO But this info may be kept in the output in a future version, if it is not a problem in the rest of the tool's workflow? (TO discuss in 2025)
    df.drop('nb_points', axis=1, inplace=True)

    # At this stage, df looks like:
    # (columns:)   S2CELL  Timestamp  lat  lon  GW Nitrates (mg/L)  GW Total Phosphorus (mg/L) ...

    df.drop(['lat', 'lon'], axis=1,
            inplace=True)  # (to remove those two columns, and keep only the S2CELL spatial index)

    # Pivot the DataFrame (to return a DataFrame with distinct increasing Dates in Rows,
    # observed Parameter names as Column GROUPS, and S2CELLs (with some data for that paramter) as Columns in that group
    df = df.pivot_table(index='Timestamp', columns='S2CELL')

    return df

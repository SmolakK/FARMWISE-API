import pandas as pd
from API_readers.hubeau.hubeau_mappings.hubeau_mapping_piezo import MAPPING
from utils.coordinates_to_cells import prepare_coordinates
import warnings
from utils.data_operators import flatten_list
import asyncio

# Important reminder: "hubeaupyutils" is a library that must be installed running/using this API reader,
# cf. file "hubeaupyutils-main.tar.gz"
import hubeaupyutils as hub


async def fetch_data(api, pt_id, he_period_bounds, data_requested_varnames, verbose_level):
    """
    Asynchronous function to fetch data for a specific point.
    """
    if verbose_level >= 1:
        print(f"Fetching data for point ID: {pt_id} for variables: {data_requested_varnames}")

    try:
        # Fetch data using the hub API (Note: Here argument names are specific to the hubeaupyutils lib functions,
        # and thus differ from the online HubEau API parameters.)
        df = await asyncio.to_thread(
            api.get_data,
            code_station=pt_id,
            start_date=he_period_bounds[0],
            end_date=he_period_bounds[1],
            only_valid_data=True, # Remark: This will also filter out "dynamic" water levels... but that is okay for
            # the purposes of the study.
            add_real_time=False,
            verbose=(verbose_level >= 2)
        )

        # Column names of df at this stage (output from 1 api.get_data call):
        #   date & indice as 2 indexes; and a value regular column

        # Ensure proper DataFrame formatting Remark: Those column names and contents result from special formatting
        # of the output by hubeaupyutils lib's "piezometry" wrapper (e.g., 'indice').
        if not df.empty:
            df = df.rename_axis(['date_mesure','xINDICEx']).reset_index().drop(columns=['xINDICEx']).rename(columns={"value": "niveau_nappe_eau"})
            df['code_bss_old'] = pt_id
            if verbose_level >= 2:
                print(f"Data fetched for point {pt_id}:")
                print(df.head())
        
        # Output table column names (if not empty): date_mesure, niveau_nappe_eau, code_bss_old.
        return df
    except Exception as e:
        if verbose_level >= 1:
            print(f"Error fetching data for point {pt_id}: {e}")
        return None


async def read_data(spatial_range, time_range, data_range, level, nmax_pts=None, verbose_level=0):
    """
    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param time_range: A tuple containing the start and end timestamps defining the time range. 2 text dates (str) of format YYYY-mm-dd
    :param data_range: A list of the GW quantity variables requested ('gwlevel' is the only variable allowed in this list) (or None will apply the default = ['gwlevel']) (not case sensitive)
    :param level: S2Cell level.
    :param nmax_pts: maximum number of points to select for data extraction (an optional limitation that may be used only during tests)
    :param verbose_level: level of details to write in the console (0: none; 1: some; >=2: lots of details)
    :return: A pandas DataFrame containing the processed data.
    """
    url = 'https://hubeau.eaufrance.fr/api/v1/niveaux_nappes/chroniques'

    # REMARKS on the function arguments:
    # data_range:
    #  GW depth is not allowed beause the GWL depth values in ADES database are ~raw measures relative to a local reference elevation that is often NOT the ground level!

    # NO MORE NEEDED: north, south, east, west = spatial_range
    # NO MORE NEEDED: bbox = [west, south, east, north]  # Create bbox

    # Protection in case of bad type of argument data_range:
    # because without this conversion, next operations would fragment the string to a list of individual characters!
    if isinstance(data_range, str):
        data_range = [data_range]

    # Apply the default data_range, if None is specified:
    if data_range is None:
        data_range = 'gwlevel'

    # Protection: convert to lower case:
    data_range = list(map(lambda x: x.lower(), data_range))
    # Convert to set, to remove duplicates (if any):
    data_asked_raw_set = set(data_range)  # (raw but after lower case)

    ################### PARAMETERS (preparing list of...) ###################

    # Not required for now (but kept here in case it is needed in a future version...):
    # gwquality_params_df = pd.read_csv(r'API_readers/hubeau/constants/farmwise_gwquality_parameters.csv', dtype=str)
    # With argument dtype=str so that even the code_param column (e.g., 1340 for Nitrates) will be read as text here.

    # Diagnostic info:
    if (verbose_level >= 1):
        print("\nPARAMETERS (GW Quantity)...\n")
        print("Asked parameter names (data_range set, all made lower case) =")
        print(data_asked_raw_set)

    data_requested_keys_set = data_asked_raw_set & set(['groundwater quantity']) # Note that 'gwdepth' is no longer allowed!

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

    data_requested_varnames = list(data_requested_keys_set)

    # Diagnostic info:
    if (verbose_level >= 1):
        print("Parameters that will be extracted from HubEau 'Piézométrie' (GWL) API results (data_requested_codes) =")
        print(data_requested_varnames) # (variable names... of columns in the obtained data tables)

    # Exiting here if there is no valid parameter code:
    if len(data_requested_varnames) == 0:
        return None

    ################### POINTS (preparing list of...) ###################

    if (verbose_level >= 1):
        print("\nPOINTS...\n")
        print("Selecting France GW LEVEL monitoring points (Piezometers) inside the Spatial Range...")

    coors = pd.read_csv(r'API_readers/hubeau/constants/farmwise_gwquantity_piezos_sel_for_hubeau.csv')
    coordinates = prepare_coordinates(coordinates=coors, spatial_range=spatial_range, level=level)

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
    pt_ids_lst = coordinates["code_bss_old"].to_list()
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
        print("\nDOWNLOADING: HubEau (France) GW Quantity (GW LEVEL) data...\n")

    # Initialisation of the hubeaupyutils API object
    api = hub.init_api('piezometry')

    # Prepare tasks for asynchronous data fetching
    tasks = [
        fetch_data(api, pt_id, he_period_bounds, data_requested_varnames, verbose_level)
        for pt_id in pt_ids_lst
    ]
    responses = await asyncio.gather(*tasks)

    # Collect and process responses
    accum_dfs = [df for df in responses if df is not None and not df.empty]

    if not accum_dfs:
        return None

    df = pd.concat(accum_dfs, ignore_index=True)

    # Adding code_bss_new point ids, based on the reference list of points, now that the old ids have been used to get the data,
    # and other columns too:
    df = df.merge(coordinates[['code_bss_old', 'code_bss_new', 'lon', 'lat']], left_on='code_bss_old', right_on='code_bss_old').rename({})
    # Also add a reminder of the measurement units:
    # (NGF = General levelling of France, see https://epsg.io/5119-datum and https://en.wikipedia.org/wiki/General_levelling_of_France)
    df['symbole_unite'] = "meters NGF" # Note that further below, meters are transformed into cm.
    # TODO Maybe we could transform (translate) the values to an international (EU) standard vertical reference?

    # Renaming:
    df = df.drop(columns=['code_bss_old']).rename(columns={'code_bss_new':'point_id'})

    # If no data, there is nothing else to do:
    if (len(df) == 0):
        return None

    if (verbose_level >= 1):
        print("\nPREVIEW of the whole data table (concatenation of all points' data frames):")
        print(df)

    if (verbose_level >= 2):
        print("\nList of all {} point IDs (also called 'bss_id'):".format(df['point_id'].nunique()))
        print(df['point_id'].unique())
        print("\nList of all column names (before further processing of the DataFrame):")
        print(df.columns.to_list())

    # Column names of df at this stage :
    #   date_mesure  niveau_nappe_eau    point_id       lon        lat symbole_unite

    # Selecting columns to discard some columns that are not used anymore (for now)
    df = df[['point_id', 'date_mesure', 'lat', 'lon', 'niveau_nappe_eau']]

    # Removing fully redundant data rows, if any (altough it should not)
    df = df.drop_duplicates()

    # FARMWISE-specific renaming:
    df = df.rename(MAPPING, axis=1)    

    # Change m to cm
    df[['Groundwater Level [cm]']] *= 100

    # Column names of df at this stage :
    #   point_id  Timestamp        lat       lon  "Groundwater Level [cm]"

    # To S2CELLs
    # (This adds a column 'S2CELL' to df.)
    df = prepare_coordinates(df, spatial_range, level)
    original_size = df.shape[0]

    df = df[['S2CELL', 'Timestamp', 'Groundwater Level [cm]', 'lon', 'lat']].groupby(['S2CELL', 'Timestamp']).mean()
    # Ok, mean of GWL is acceptable, although a bit too simple in case of large cell size
    # And mean will be consisdered ok for lon and lat coordinates too:
    # - only 1 unique value of each (lat, lon) per point...
    # - So if cell size is very small, mean of 1 coord. = that coordinate.
    # - In case of large cell size, however, the calculated lon,lat coordinate of the S2CELL will be an approximate, virtual, kind of "center of mass" point.

    # But that is not an issue, since those lon,lat coordinates are dropped in the output:
    df = df.drop(['lat', 'lon'], axis=1)
    # TODO Maybe this drop() could be applied sooner, before the .groupby(), since the aggregated mean coordinates are not used.

    if original_size != df.shape[0]:
        warnings.warn("Some data were aggregated")

    # Resample days
    df.reset_index(inplace=True)

    df = df.set_index("Timestamp").groupby('S2CELL').resample('1D').first()
    df = df.drop('S2CELL', axis=1) # to remove the redundant not-index S2CELL column (now that a duplicate is included in the multi-index)
    df = df.reset_index()
    df.Timestamp = pd.to_datetime(df.Timestamp).dt.date


    # Pivot the DataFrame
    df = df.pivot_table(index='Timestamp', columns='S2CELL')

    return df

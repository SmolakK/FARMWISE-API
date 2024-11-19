if __name__ == "__main__":
    # DEVEL section, useful to test this script without having to launch the whole thing
    import sys
    import os
    print(os.path.abspath(__file__))
    add_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) #+ r"\API_readers\hubeau"
    print(add_path)
    sys.path.append(add_path)
    #sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    #print(os.getcwd())

import API_readers.hubeau.hubeau_wq_read as hewq
from API_readers.hubeau.hubeau_wq_read import read_data

#TEST example (TODO develop further, based on this, to create real & useful tests)
if True:

    # x = PARAMETERS_MAPPING["groundwater quality"]
    # print(x)
    # exit()

    print("TEST: Preparing parameters -> arguments for calling function read_data()...\n")
    N = 49.0
    S = 47.0
    E = -2.0
    W = -5.0
    LEVEL = 15
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

    data_range = ['phosphorus', 'nitrate'] #['phosphorus', 'pesticides','pfas'][2] #None #'pesticides'
    # data_range = 'pesticides'
    # data_range = ['groundwater quality']

    print(spatial_range)
    print(time_range)
    print(data_range)

    print("\nTEST: calling function read_data of hubeau_wq_read...")

    whatweget = read_data(spatial_range,time_range,data_range,LEVEL, nmax_pts=10, verbose_level=1)

    print("\n\nWHAT we got with this test =")
    print(whatweget)
    if whatweget is not None:
        print(len(whatweget))

    # whatweget.to_csv("API_readers/hubeau/tmp_check_returned_whatweget_df.csv", sep=";")

    print("\nTEST: The End.")

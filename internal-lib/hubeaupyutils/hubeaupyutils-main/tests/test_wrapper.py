#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from time import time
import hubeaupyutils as hub

start_time = time()

api = hub.init_api(api='piezometry')
sta = api.get_station(code_station='00197X0049/F2')
df = api.get_data(code_station='00197X0049/F2')
# dir(api)
# type(df)
# df.tail()

api = hub.init_api(api='hydrometry')
sta = api.get_station(code_station='E3511210')
df = api.get_data(code_station='E351121001')
# dir(api)
# type(df)
# df.tail()

# toto = hub.HubeauUtils('hydrometrie', 'obs_elab')
# df = toto.get_from_api({'code_entite': 'E3511210', 'size':20_000})

api = hub.init_api(api='withdrawal')
sta = api.get_station(code_station='OPR0000000003')
df = api.get_data(code_ouvrage='OPR0000000003')

api = hub.init_api(api='groundwater_qual')
sta = api.get_station(code_station='00197X0403/PZ1BIS')
df = api.get_data(code_station='00197X0403/PZ1BIS')
df = api.get_data(code_station='00197X0403/PZ1BIS', code_param=1371)
df = api.get_data(code_station='BSS000BYEN', code_param=1340)
df = api.get_data(code_station='BSS000XUUM', code_param=1340)

end_time = time()
print("dev: Execution time : --- %.5f seconds ---" % (end_time - start_time))

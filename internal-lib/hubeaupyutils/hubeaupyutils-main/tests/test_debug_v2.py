import hubeaupyutils as hub
# -- debug marc
# check available apis
print(hub.API.keys())
stid = '01000172'
# intiate one
api = hub.init_api('river_qual') 
# --- get stations
# help(api.get_station)
print('Request with v1:')
sta  = api.get_station(code_station=stid, verbose=True)
print(sta)

print('Request with v2:')
api = hub.init_api('river_qual', version=2) 
sta  = api.get_station(code_station=stid, verbose=True)
print(sta)
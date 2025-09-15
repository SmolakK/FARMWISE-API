from hubeaupyutils import HubeauUtils as hub

api = hub('qualite_nappes', 'analyses')

print(api.all_endpoints)
doc = api.get_apis_documentation()
op  = api.get_operators()
par = api.get_parameters()

answ, answ_json, no3_df = api.get_from_api(
    parameters={'size':10, 'bss_id':'BSS000XUUM', 'code_param':1340},
    return_type='answ'
)

no3_df.columns
no3_df.resultat.min()
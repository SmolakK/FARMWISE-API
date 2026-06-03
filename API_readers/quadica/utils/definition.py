DATA_FRAME = {
    'c_annual_with_coords.csv' : 'year_vertical',
    'n_surplus_with_coords.csv' : 'year_vertical',
    'pet_monthly_with_coords.csv' : 'monthly_horizontal',
    'pre_monthly_with_coords.csv' : 'monthly_horizontal',
    'q_annual_with_coords.csv' : 'year_vertical',
    'tavg_monthly_with_coords.csv' : 'monthly_horizontal',
    'wrtds_monthly_with_coords_date_merged.csv' : 'date_vertical'
}

DATA_RANGES = {
    'c_annual_with_coords.csv' : ['n_Q_annual','median_Q_annual','n_NO3','median_NO3N','n_Nmin','median_Nmin','n_TN','median_TN','n_PO4','median_PO4P','n_TP','median_TP','n_DOC','median_DOC','n_TOC','median_TOC'],
    'n_surplus_with_coords.csv' : ['N_nonagri','N_agri','N_total','N_agri_frac'],
    'pet_monthly_with_coords.csv' : ['pet'],
    'pre_monthly_with_coords.csv' : ['pre'],
    'q_annual_with_coords.csv' : ['n_Qdaily','median_Qdaily'],
    'tavg_monthly_with_coords.csv' : ['tavg'],
    'wrtds_monthly_with_coords_date_merged.csv' : ['n_Q_wrtds','n_C_NO3','n_C_PO4','n_C_Nmin','n_C_TN','n_C_TP','n_C_DOC','n_C_TOC','n_FNC_NO3','n_FNC_PO4','n_FNC_Nmin','n_FNC_TN','n_FNC_TP','n_FNC_DOC','n_FNC_TOC','median_Q_wrtds','median_C_NO3','median_C_PO4','median_C_Nmin','median_C_TN','median_C_TP','median_C_DOC','median_C_TOC','median_FNC_NO3','median_FNC_PO4','median_FNC_Nmin','median_FNC_TN','median_FNC_TP','median_FNC_DOC','median_FNC_TOC','mean_Flux_NO3','mean_Flux_PO4','mean_Flux_Nmin','mean_Flux_TN','mean_Flux_TP','mean_Flux_DOC','mean_Flux_TOC','mean_FNFlux_NO3','mean_FNFlux_PO4','mean_FNFlux_Nmin','mean_FNFlux_TN','mean_FNFlux_TP','mean_FNFlux_DOC','mean_FNFlux_TOC']
}
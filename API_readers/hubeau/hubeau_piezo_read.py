import requests
import pandas as pd
from hubeau_mappings.hubeau_mapping_piezo import MAPPING
from utils.coordinates_to_cells import prepare_coordinates
import warnings
from utils.interpolate_data import interpolate
from get_piezo_stations import get_station_codes


def read_data(spatial_range, time_range, data_range, level):
    """
    read_data((51.09, 41.33, 9.56, -5.14),('1950-01-01','1980-01-01'),['phosphorus'],8)

    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param time_range: A tuple containing the start and end timestamps defining the time range.
    :param data_range: A list of properties requested.
    :param level: S2Cell level.
    :return: A pandas DataFrame containing the processed data.
    """
    url = 'https://hubeau.eaufrance.fr/api/v1/niveaux_nappes/chroniques'

    north, south, east, west = spatial_range
    bbox = [west, south, east, north]  # Create bbox
    station_codes = get_station_codes(bbox, time_range)

    all_analyses = []
    num_of_stations = station_codes.shape[0]

    for chunk in range(0, num_of_stations, 200):
        cur_station_codes = station_codes.iloc[chunk:chunk + 200]
        params = {
            'code_bss': ','.join(cur_station_codes['code_bss'].values),
            'date_debut_mesure': time_range[0],
            'date_fin_mesure': time_range[1],
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
    df = df[['date_mesure', 'niveau_nappe_eau', 'profondeur_nappe', 'code_bss']]
    df = df.drop_duplicates()
    df = df.rename(MAPPING, axis=1)
    # Change m to cm
    df[['Groundwater Level [cm]', 'Groundwater Depth [cm]']] = df[['Groundwater Level [cm]', 'Groundwater Depth [cm]']] * 100
    df = df.join(station_codes,rsuffix='r')
    df = df[['Timestamp','Groundwater Level [cm]', 'Groundwater Depth [cm]','x','y']]
    df = df.rename({'x':'lon','y':'lat'},axis=1)

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
    df = df.drop('S2CELL', axis=1)
    df[['lat', 'lon']] = df[['lat', 'lon']].ffill()
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

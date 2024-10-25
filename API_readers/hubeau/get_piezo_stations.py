import requests
import pandas as pd


def get_station_codes(bbox, time_range, size=10000):
    """
    Queries the Hub'eau Piezometry API to retrieve station codes (code_bss)
    within a specified bounding box.

    Parameters:
    - bbox (str): Bounding box in the format "min_lon,min_lat,max_lon,max_lat"
    - size (int): Number of results per request (default 10000)

    Returns:
    - List[str]: List of station codes (code_bss)
    """
    url = 'https://hubeau.eaufrance.fr/api/v1/niveaux_nappes/stations'

    day_by_day = pd.date_range(time_range[0],time_range[1],periods=200)

    params = {
        'bbox': bbox,
        'size': size,
        'srid': 4326,
        'page': 1,
        'date_recherche': ','.join([str(x.date()) for x in day_by_day])
    }
    all_stations = []
    while True:
        response = requests.get(url, params=params)
        data = response.json()
        if not response.ok:
            break
        stations = data['data']
        all_stations.extend(stations)
        # Check if there is a next page
        if data.get('next'):
            params['page'] += 1
        else:
            break

    # Extract the station codes (code_bss)
    stations = pd.DataFrame(all_stations)[['code_bss','x','y']]
    return stations

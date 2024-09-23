import requests
import pandas as pd
import warnings
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from zipfile import ZipFile
import io
from utils.coordinates_to_cells import prepare_coordinates
from utils.imgw_utils import create_timestamp_from_row, get_years_between_dates
from tqdm import tqdm
from API_readers.imgw_hydro.imgw_mappings.imgw_hydro_mappings import WATER_COLUMNS, WATER_SELECTED, DATA_ALIASES

URL = r'https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_hydrologiczne/dobowe/'
SPACE_TIME_COLUMNS = ['Station code', 'Hydrological year', 'Day', 'Calendar month']


def read_data(spatial_range, time_range, data_range, level):
    """

    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param time_range: A tuple containing the start and end timestamps defining the time range.
    :param data_range: A list of data types requested.
                       Allowed data types: 'precipitation', 'sunlight', 'cloud cover', 'temperature',
                       'wind', 'pressure', 'humidity'.
    :param level: S2Cell level.
    :return:
    """
    print("DOWNLOADING: IMGW hydro data")
    coors = pd.read_csv(r'API_readers/imgw_hydro/constants/imgw_coordinates.csv')
    coordinates = prepare_coordinates(coordinates=coors, spatial_range=spatial_range, level=level)
    years = get_years_between_dates(*time_range)
    data_requested = set([k for k, v in DATA_ALIASES.items() if v in data_range])
    response = requests.get(URL)
    if response.status_code == 200:
        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all links (assuming directory listing is in <a> tags)
        links = soup.find_all('a')

        # Extract folder names
        folders = [link['href'].replace('/', '') for link in links if link['href'].endswith('/')]
        folders = [year for year in folders if re.match(r'^\d{4}(_\d{4})?$', year)]

        # Urls for reading
        read_urls = [urljoin(URL + '/', x) for x in years]
    else:
        warnings.warn("IMGW server not responding")

    water_files = []
    for url in tqdm(read_urls,total=len(read_urls)):
        response = requests.get(url)
        if response.status_code == 200:
            # Parse the HTML content
            soup = BeautifulSoup(response.text, 'html.parser')

            # Find all links (assuming the files are listed as clickable links in the HTML)
            links = soup.find_all('a')

            # Extract file names
            file_names = [link['href'] for link in links if '.' in link['href']]

            # Read files from the year

            for x in file_names:
                zipfile = requests.get(urljoin(url+'/',x))
                with ZipFile(io.BytesIO(zipfile.content)) as zip_ref:
                    for name in zip_ref.namelist():
                        if 'codz' in name:
                            water_data = pd.read_csv(zip_ref.open(name), encoding='windows-1250', names=WATER_COLUMNS)
                            water_selection = list(data_requested.intersection(set(WATER_SELECTED)))
                            water_selection_spacetime = water_selection + SPACE_TIME_COLUMNS
                            water_data = water_data.loc[:,water_selection_spacetime]
                            water_files.append(water_data)
        else:
            warnings.warn('IMGW server not responding')

    water_files = pd.concat(water_files)
    water_files = water_files.rename({'Calendar month': 'Month', 'Hydrological year': 'Year'}, axis=1)
    water_files['Timestamp'] = water_files.apply(create_timestamp_from_row, axis=1)
    water_files = water_files.merge(coordinates,left_on='Station code',right_on='Unnamed: 0')

    # Define the columns to be excluded
    columns_excluded = ['Timestamp', 'S2CELL']

    # Get numerical values and convert
    water_files_values = water_files.loc[:,water_selection]
    water_files_values = water_files_values.apply(pd.to_numeric, errors='coerce')
    water_files_spacetime = water_files.loc[:,columns_excluded]
    water_files = pd.concat([water_files_values,water_files_spacetime],axis=1)

    # Adjust time range
    water_files = water_files[(water_files.Timestamp >= time_range[0]) & (water_files.Timestamp <= time_range[1])]

    # Average overlapping
    original_size = water_files.shape[0]
    s_d_merged = water_files.groupby(['S2CELL', 'Timestamp']).mean()
    if original_size != s_d_merged.shape[0]:
        warnings.warn("Some data were aggregated")

    # Pivot the DataFrame
    water_pivot = water_files.pivot_table(index='Timestamp', columns='S2CELL')

    return water_pivot

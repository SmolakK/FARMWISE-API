import requests
import pandas as pd
import warnings
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from zipfile import ZipFile
import io
from API_readers.imgw.imgw_mappings.synop_mapping import s_d_COLUMNS, s_d_SELECTION, s_d_t_COLUMNS, s_d_t_SELECTION, DATA_ALIASES
from tqdm import tqdm
import s2sphere
from API_readers.imgw.imgw_utils import create_timestamp_from_row, expand_range, get_years_between_dates

URL = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_meteorologiczne/dobowe/synop"
SPACE_TIME_COLUMNS = ['Station code', 'Year', 'Month', 'Day', 'Code', 'lat', 'lon']


def _limit_coordinates(spatial_range, coordinates):
    """
    Limit the coordinates DataFrame to those falling within the specified spatial range.

    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param coordinates: DataFrame containing latitude and longitude coordinates.
    :return: DataFrame containing coordinates within the specified spatial range.
    """
    n, s, e, w = spatial_range
    coordinates = coordinates[(coordinates.lat <= n) & (coordinates.lat >= s) &
                              (coordinates.lon <= e) & (coordinates.lon >= w)]
    return coordinates


def _prepare_coordinates(spatial_range, level):
    """
    Prepare coordinates for data retrieval, limiting them to the specified spatial range and assigning S2Cell IDs.

    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param level: S2Cell level.
    :return: DataFrame containing coordinates within the specified spatial range and their corresponding S2Cell IDs.
    """
    coordinates = pd.read_csv('API_readers/imgw/constants/imgw_coordinates.csv', index_col=0)
    if coordinates.lon.isna().sum() > 0 or coordinates.lat.isna().sum():
        warnings.warn("Some stations in IMGW-API have no coordinates. The data for them will be lost.")
    coordinates = coordinates[~coordinates.isna().any(axis=1)]
    coordinates.lat = coordinates.lat.astype('float32')
    coordinates.lon = coordinates.lon.astype('float32')
    coordinates = _limit_coordinates(spatial_range=spatial_range, coordinates=coordinates)
    coordinates['S2CELL'] = coordinates.apply(lambda x:
                                              s2sphere.CellId.from_lat_lng(
                                                  s2sphere.LatLng.from_degrees(x.lat, x.lon)).parent(level).id(),
                                              axis=1)
    return coordinates


def read_data(spatial_range, time_range, data_range, level):
    """
    Read data from the IMGW-API for the specified spatial and time range, and data types.

    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param time_range: A tuple containing the start and end timestamps defining the time range.
    :param data_range: A list of data types requested.
                       Allowed data types: 'precipitation', 'sunlight', 'cloud cover', 'temperature',
                       'wind', 'pressure', 'humidity'.
    :param level: S2Cell level.
    :return: A DataFrame containing the requested data pivoted by Timestamp and S2CELL.
    """
    coordinates = _prepare_coordinates(spatial_range=spatial_range, level=level)
    years = get_years_between_dates(*time_range)
    data_requested = set([k for k,v in DATA_ALIASES.items() if v in data_range])
    response = requests.get(URL)
    if response.status_code == 200:
        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all links (assuming directory listing is in <a> tags)
        links = soup.find_all('a')

        # Extract folder names
        folders = [link['href'].replace('/','') for link in links if link['href'].endswith('/')]
        folders = [year for year in folders if re.match(r'^\d{4}(_\d{4})?$', year)]

        # Expand names for searching
        expanded_years = {}
        for item in folders:
            expanded_years.update(expand_range(item))

        read_urls = [urljoin(URL+'/', expanded_years[x]) for x in years]
    else:
        warnings.warn("IMGW server not responding")

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
            s_d_files = []
            s_d_t_files = []
            for x in file_names:
                zipfile = requests.get(urljoin(url+'/',x))
                with ZipFile(io.BytesIO(zipfile.content)) as zip_ref:
                    for name in zip_ref.namelist():
                        if '_t' in name:
                            s_d_t_file = pd.read_csv(zip_ref.open(name),encoding='windows-1250',names=s_d_t_COLUMNS)
                            data_selection = list(data_requested.intersection(set(s_d_t_SELECTION)))
                            data_selection += SPACE_TIME_COLUMNS
                            s_d_t_file = s_d_t_file.loc[:, s_d_t_file.columns.intersection(data_selection)]
                            s_d_t_files.append(s_d_t_file)
                        else:
                            s_d_file = pd.read_csv(zip_ref.open(name), encoding='windows-1250', names=s_d_COLUMNS)
                            data_selection = list(data_requested.intersection(set(s_d_SELECTION)))
                            data_selection += SPACE_TIME_COLUMNS
                            s_d_file = s_d_file.loc[:, s_d_file.columns.intersection(data_selection)]
                            s_d_files.append(s_d_file)
            s_d = pd.concat(s_d_files)
            s_d_t = pd.concat(s_d_t_files)
        else:
            warnings.warn("IMGW server not responding")

    # Define the columns to be excluded
    columns_excluded = ['Timestamp', 'S2CELL']

    # Apply create_timestamp_from_row function to create Timestamp column
    s_d['Timestamp'] = s_d.apply(create_timestamp_from_row, axis=1)
    s_d_t['Timestamp'] = s_d_t.apply(create_timestamp_from_row,axis=1)

    # Merge with COORDINATES DataFrame
    s_d_merged = s_d.merge(coordinates, left_on='Station code', right_on='Code')

    # Merge other dataframe together
    s_d_merged = s_d_t.merge(s_d_merged,left_on=['Timestamp','Station code'],right_on=['Timestamp','Station code'],suffixes=(None,'_right'))

    # Drop overlapping columns
    s_d_merged = s_d_merged.loc[:,[col for col in s_d_merged.columns if '_right' not in col]]

    # Select columns excluding the excluded ones
    s_d_merged_values = s_d_merged.drop(columns=columns_excluded)

    # Convert columns to numeric (excluding excluded columns)
    s_d_merged_values = s_d_merged_values.apply(pd.to_numeric, errors='coerce')

    # Concatenate excluded columns with converted numeric columns
    s_d_merged = pd.concat([s_d_merged[columns_excluded], s_d_merged_values], axis=1)

    # Remove columns with NaN values
    s_d_merged = s_d_merged.dropna(axis=1)

    # Remove space and time columns other than S2CELL and Timestamp
    s_d_merged = s_d_merged.drop(SPACE_TIME_COLUMNS,axis=1)

    # Adjust time range
    s_d_merged = s_d_merged[(s_d_merged.Timestamp >= time_range[0]) & (s_d_merged.Timestamp <= time_range[1])]

    # Average overlapping
    s_d_merged = s_d_merged.groupby(['S2CELL', 'Timestamp']).mean()

    # Pivot the DataFrame
    s_d_pivot = s_d_merged.pivot_table(index='Timestamp', columns='S2CELL')

    return s_d_pivot

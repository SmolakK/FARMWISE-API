import re
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from gios_mappings import gios_mapping
from datetime import datetime
import warnings
from utils.coordinates_to_cells import prepare_coordinates


def extract_point_ids(url):
    page = requests.get(url)
    soup = BeautifulSoup(page.text, "html.parser")
    links = soup.find_all('a')
    point_ids = [re.findall(r'p=(\d+)', link.get('href', '')) for link in links]
    point_ids = [pid for sublist in point_ids for pid in sublist]
    return ','.join(point_ids)


def scrape_point_data(point_id, parameter_values, parameter_order):
    url = f'https://www.gios.gov.pl/chemizm_gleb/index.php?mod=pomiary&p={point_id}'
    page = requests.get(url)
    soup = BeautifulSoup(page.text, "html.parser")

    table_headers = soup.find_all('th')
    columns = [th.text.strip() for th in table_headers if th.text.strip() != 'Rok']

    table_data = soup.find_all('td')[3:]
    rows = [td.text.strip() for td in table_data]

    smaller_columns = [columns[i:i + 8] for i in range(0, len(columns), 8)]
    smaller_rows = [rows[i:i + 8] for i in range(0, len(rows), 8)]

    headers_list = [';'.join(headers) for headers in smaller_columns]
    rows_list = [';'.join(row) for row in smaller_rows]

    headers_df = pd.DataFrame([headers_list[0].split(';')], columns=headers_list[0].split(';'))
    data = [row.split(';') for row in rows_list]

    data = [[value.replace(",", ".") if re.match(r"^\d+,\d+$", value) else value for value in row] for row in data]

    rows_df = pd.DataFrame(data, columns=headers_df.columns)
    rows_df.iloc[:, 0:2] = rows_df.iloc[:, 0:2].astype(str)

    # Drop columns "Uziarnienie" and "Jednostka"
    rows_df.drop(columns=['Uziarnienie', 'Jednostka'], errors='ignore', inplace=True)

    # Insert the parameter column at the second position (index 1)
    rows_df.insert(1, 'parameter', parameter_values)

    # Insert the Id column at the first position (index 0)
    rows_df.insert(0, 'point_id', point_id)
    rows_df['point_id'] = pd.to_numeric(rows_df['point_id'], errors='coerce')

    # Replace "n.o." with NaN
    rows_df.replace("n.o.", np.nan, inplace=True)

    # Melt the DataFrame to long format
    long_df = rows_df.melt(id_vars=['point_id', 'parameter'], var_name='year', value_name='value')

    # Create pivot table
    pivot_table = long_df.pivot_table(index=['point_id', 'year'], columns='parameter', values='value',
                                      aggfunc='first').reset_index()

    # Ensure the pivot table has the parameters in the specified order
    available_parameters = [param for param in parameter_order if param in pivot_table.columns]
    pivot_table = pivot_table[['point_id', 'year'] + available_parameters]

    return pivot_table


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
    print("DOWNLOADING: GIOS soil data")
    time_from, time_to = time_range
    time_from = datetime.strptime(time_from, '%Y-%m-%d').year
    time_to = datetime.strptime(time_to, '%Y-%m-%d').year
    coors = pd.read_csv(r'API_readers/gios/constants/gios_coordinates.csv')
    coordinates = prepare_coordinates(coordinates=coors, spatial_range=spatial_range, level=level)
    point_id_url = 'https://www.gios.gov.pl/chemizm_gleb/index.php?mod=pomiary'
    point_ids = extract_point_ids(point_id_url)

    all_dataframes = []

    data_requested = set([k for k,v in gios_mapping.DATA_ALIASES.items() if v in data_range])
    parameter_values = gios_mapping.PARAMETER_VALUES
    parameter_selection = gios_mapping.PARAMETER_SELECTION
    parameter_selection = list(set(parameter_selection).intersection(data_requested))

    # Keeping the same order for the parameters
    parameter_order = parameter_values.copy()
    point_ids = point_ids.split(',')[:10]

    for point_id in tqdm(point_ids,total=len(point_ids)):
        df = scrape_point_data(point_id, parameter_values, parameter_order)
        # Filter data layers
        columns_to_select = list(df.columns[:2]) + list(set(df.columns).intersection(set(parameter_selection)))
        df = df.loc[:,columns_to_select]
        # Filter time range
        df.year = df.year.astype(int)
        df = df[(df.year >= time_from) & (df.year <= time_to)]
        all_dataframes.append(df)

    # Combine all dataframes into one
    final_dataframe = pd.concat(all_dataframes, ignore_index=True)

    # Coordinates merge
    final_dataframe = final_dataframe.merge(coordinates, left_on='point_id', right_on='id')

    # Select necessary columns
    constant_columns_numeric = list(set(final_dataframe.columns).intersection(set(parameter_selection)))
    constant_columns = ['year','S2CELL'] + constant_columns_numeric
    final_dataframe = final_dataframe.loc[:, constant_columns]

    # To numeric
    final_dataframe_numeric = final_dataframe.loc[:, constant_columns_numeric]
    final_dataframe_numeric = final_dataframe_numeric.apply(pd.to_numeric, errors='coerce').fillna(0)
    final_dataframe = pd.concat((final_dataframe.drop(constant_columns_numeric,axis=1),final_dataframe_numeric),axis=1)

    # Average overlapping
    original_size = final_dataframe.shape[0]
    final_dataframe = final_dataframe.groupby(['S2CELL', 'year']).mean()
    if original_size != final_dataframe.shape[0]:
        warnings.warn("Some data were aggregated")

    # Pivot
    dataframe_pivot = final_dataframe.pivot_table(index='year',columns='S2CELL')
    return dataframe_pivot

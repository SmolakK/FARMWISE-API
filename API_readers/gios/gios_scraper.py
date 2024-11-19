import re
import pandas as pd
import numpy as np
import httpx
from bs4 import BeautifulSoup
from tqdm import tqdm
from API_readers.gios.gios_mappings import gios_mapping
from datetime import datetime
import warnings
from utils.coordinates_to_cells import prepare_coordinates
import asyncio


# TODO: time wrapping bug
async def extract_point_ids(url):
    """
    Extracts point IDs from the hyperlinks found on a webpage.

    This function sends a GET request to the specified URL, parses the HTML content of the page,
    and retrieves all hyperlinks. It extracts point IDs from the query parameters of the links
    that match the pattern 'p={point_id}'.

    :param url: A string representing the URL of the webpage to scrape.
    :return: A comma-separated string of point IDs extracted from the links on the page.
    """
    async with httpx.AsyncClient() as client:
        page = await client.get(url)
    soup = BeautifulSoup(page.text, "html.parser")
    links = soup.find_all('a')
    point_ids = [re.findall(r'p=(\d+)', link.get('href', '')) for link in links]
    point_ids = [pid for sublist in point_ids for pid in sublist]
    return ','.join(point_ids)


async def scrape_point_data(point_id, parameter_values, parameter_order):
    """
    Scrapes soil measurement data for a specified point ID from a GIOS webpage.

    This function retrieves data from the GIOS website, processes the HTML to extract relevant
    soil measurement data, and organizes it into a pandas DataFrame. It formats the data and
    ensures that parameters are arranged according to the specified order.

    :param point_id: An integer representing the unique identifier for the measurement point.
    :param parameter_values: A list of parameter names corresponding to the scraped data.
    :param parameter_order: A list specifying the desired order of parameters in the final DataFrame.
    :return: A pandas DataFrame containing the scraped and organized soil measurement data,
             with columns for point ID, year, and the specified parameters.
    """
    url = f'https://www.gios.gov.pl/chemizm_gleb/index.php?mod=pomiary&p={point_id}'
    async with httpx.AsyncClient() as client:
        page = await client.get(url)
    soup = BeautifulSoup(page.text, "html.parser")

    # Parsing HTML in a separate thread
    table_headers = await asyncio.to_thread(
        lambda: [th.text.strip() for th in soup.find_all('th') if th.text.strip() != 'Rok'])
    table_data = await asyncio.to_thread(lambda: [td.text.strip() for td in soup.find_all('td')[3:]])

    # Processing data into DataFrames asynchronously
    smaller_columns = [table_headers[i:i + 8] for i in range(0, len(table_headers), 8)]
    smaller_rows = [table_data[i:i + 8] for i in range(0, len(table_data), 8)]

    headers_list = [';'.join(headers) for headers in smaller_columns]
    rows_list = [';'.join(row) for row in smaller_rows]

    headers_df = pd.DataFrame([headers_list[0].split(';')], columns=headers_list[0].split(';'))
    data = [row.split(';') for row in rows_list]
    data = [[value.replace(",", ".") if re.match(r"^\d+,\d+$", value) else value for value in row] for row in data]

    rows_df = pd.DataFrame(data, columns=headers_df.columns)
    rows_df.iloc[:, 0:2] = rows_df.iloc[:, 0:2].astype(str)
    rows_df.drop(columns=['Uziarnienie', 'Jednostka'], errors='ignore', inplace=True)
    rows_df.insert(1, 'parameter', parameter_values)
    rows_df.insert(0, 'point_id', point_id)
    rows_df['point_id'] = pd.to_numeric(rows_df['point_id'], errors='coerce')
    rows_df.replace("n.o.", np.nan, inplace=True)

    long_df = rows_df.melt(id_vars=['point_id', 'parameter'], var_name='year', value_name='value')
    pivot_table = long_df.pivot_table(index=['point_id', 'year'], columns='parameter', values='value',
                                      aggfunc='first').reset_index()
    available_parameters = [param for param in parameter_order if param in pivot_table.columns]
    pivot_table = pivot_table[['point_id', 'year'] + available_parameters]

    return pivot_table


async def read_data(spatial_range, time_range, data_range, level):
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
    avail_years = [1995, 2000, 2005, 2010, 2015, 2020, 2025]
    avail_years = [(avail_years[x], avail_years[x + 1]) for x in range(len(avail_years) - 1)]

    time_from, time_to = time_range
    time_from = datetime.strptime(time_from, '%Y-%m-%d').year
    time_to = datetime.strptime(time_to, '%Y-%m-%d').year

    between_years = [(s, e) for s, e in avail_years if e >= time_from and s <= time_from]
    lowest_range = min([x[0] for x in between_years])
    highest_range = max([x[1] for x in between_years])

    coors = await asyncio.to_thread(pd.read_csv, r'API_readers/gios/constants/gios_coordinates.csv')

    coordinates = prepare_coordinates(coordinates=coors, spatial_range=spatial_range, level=level)
    if coordinates is None:
        return None

    point_id_url = 'https://www.gios.gov.pl/chemizm_gleb/index.php?mod=pomiary'
    point_ids = await extract_point_ids(point_id_url)

    all_dataframes = []
    data_requested = set([k for k, v in gios_mapping.DATA_ALIASES.items() if v in data_range])
    parameter_values = gios_mapping.PARAMETER_VALUES
    parameter_selection = list(set(gios_mapping.PARAMETER_SELECTION).intersection(data_requested))

    # Keeping the same order for the parameters
    parameter_order = parameter_values.copy()
    point_ids = point_ids.split(',')
    point_ids = list(map(int, point_ids))
    point_ids = list(set(point_ids).intersection(set(coordinates.id)))

    for point_id in tqdm(point_ids, total=len(point_ids)):
        df = await scrape_point_data(point_id, parameter_values, parameter_order)
        # Filter data layers
        columns_to_select = list(df.columns[:2]) + list(set(df.columns).intersection(set(parameter_selection)))
        df = df.loc[:, columns_to_select]
        # Filter time range
        df.year = df.year.astype(int)
        df = df[(df.year >= lowest_range) & (df.year < highest_range)]
        all_dataframes.append(df)

    # Combine all dataframes into one
    final_dataframe = await asyncio.to_thread(pd.concat, all_dataframes, ignore_index=True)
    final_dataframe = final_dataframe.merge(coordinates, left_on='point_id', right_on='id')

    # Select necessary columns
    constant_columns_numeric = list(set(final_dataframe.columns).intersection(set(parameter_selection)))
    constant_columns = ['year', 'S2CELL'] + constant_columns_numeric
    final_dataframe = final_dataframe.loc[:, constant_columns]

    # To numeric
    final_dataframe_numeric = final_dataframe.loc[:, constant_columns_numeric]
    final_dataframe_numeric = final_dataframe_numeric.apply(pd.to_numeric, errors='coerce').fillna(0)
    final_dataframe = pd.concat((final_dataframe.drop(constant_columns_numeric, axis=1), final_dataframe_numeric),
                                axis=1)

    # Average overlapping
    original_size = final_dataframe.shape[0]
    final_dataframe = final_dataframe.groupby(['S2CELL', 'year']).mean()
    if original_size != final_dataframe.shape[0]:
        warnings.warn("Some data were aggregated")
    final_dataframe = final_dataframe.groupby(level=0, axis=1).mean()  # some wierd stuff out here

    # Explode to days
    days = pd.date_range(time_range[0], time_range[1], freq='D')
    final_dataframe = pd.concat([final_dataframe.assign(Timestamp=date.date()) for date in days])

    final_dataframe = final_dataframe.droplevel(1).reset_index().set_index(["Timestamp", 'S2CELL'])

    dataframe_pivot = final_dataframe.pivot_table(index='Timestamp', columns='S2CELL')
    return dataframe_pivot

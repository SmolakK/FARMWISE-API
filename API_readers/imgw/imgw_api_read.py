import requests
import pandas as pd
import warnings
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from zipfile import ZipFile
import io
from mappings.synop_mapping import s_d_COLUMNS, s_d_SELECTION, s_d_t_COLUMNS
from tqdm import tqdm
import s2cell
import zarr

COORDINATES = pd.read_csv('constants/imgw_coordinates.csv',index_col=0)
COORDINATES = COORDINATES[~COORDINATES.isna().any(axis=1)]
COORDINATES.lat = COORDINATES.lat.astype('float32')
COORDINATES.lon = COORDINATES.lon.astype('float32')
COORDINATES['S2CELL'] = COORDINATES.apply(lambda x: s2cell.lat_lon_to_token(x.lat,x.lon,level=17),axis=1)

def expand_range(range_str):
    if '_' in range_str:
        start, end = map(int, range_str.split('_'))
        return {str(year): range_str for year in range(start, end + 1)}
    else:
        return {range_str: range_str}


def create_timestamp_from_row(row):
    """
    Create a Pandas Timestamp from day, month, and year columns in a DataFrame row.

    Parameters:
        row (pd.Series): A row from a DataFrame containing 'day', 'month', and 'year' columns.

    Returns:
        pd.Timestamp: Timestamp object representing the given date.
    """
    day = row['Day']
    month = row['Month']
    year = row['Year']
    return pd.Timestamp(year=year, month=month, day=day)

years = ['1993','2013']

url = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_meteorologiczne/dobowe/synop"
response = requests.get(url)
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

    read_urls = [urljoin(url+'/',expanded_years[x]) for x in years]
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
                        s_d_t_files.append(pd.read_csv(zip_ref.open(name),encoding='windows-1250',names=s_d_t_COLUMNS))
                    else:
                        s_d_files.append(pd.read_csv(zip_ref.open(name),encoding='windows-1250',names=s_d_COLUMNS))
        s_d = pd.concat(s_d_files)
        s_d_t = pd.concat(s_d_files)
    else:
        warnings.warn("IMGW server not responding")

# Define the columns to be excluded
columns_excluded = ['Timestamp', 'S2CELL']

# Apply create_timestamp_from_row function to create Timestamp column
s_d['Timestamp'] = s_d.apply(create_timestamp_from_row, axis=1)

# Merge with COORDINATES DataFrame
s_d_merged = s_d.merge(COORDINATES, left_on='Station code', right_on='Code')

# Check for data loss due to missing coordinates
if s_d.shape[0] != s_d_merged.shape[0]:
    raise ValueError("Data loss due to missing coordinates!")

# Select columns excluding the excluded ones
s_d_merged_values = s_d_merged.drop(columns=columns_excluded)

# Convert columns to numeric (excluding excluded columns)
s_d_merged_values = s_d_merged_values.apply(pd.to_numeric, errors='coerce')

# Concatenate excluded columns with converted numeric columns
s_d_merged = pd.concat([s_d_merged[columns_excluded], s_d_merged_values], axis=1)

# Remove columns with NaN values
s_d_merged = s_d_merged.dropna(axis=1)

# Pivot the DataFrame
s_d_pivot = s_d_merged.pivot_table(index='Timestamp', columns='S2CELL')

# Convert to Zarr array
s_d_zarr = zarr.array(s_d_pivot)

s_d_t['Timestamp'] = s_d_t.apply(create_timestamp_from_row,axis=1)
s_d_t_merged = s_d_t.merge(COORDINATES,left_on='Station code',right_on='Code')
if s_d_t.shape[0] != s_d_t_merged.shape[0]:
    raise "Data loss due to missing coordinates!"

s_d_merged

# TODO: selection procedure, clean lat, lon, dates etc., mapping to global names, clean this out

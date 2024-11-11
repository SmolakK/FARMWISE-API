import requests
import pandas as pd
import numpy as np
import s2sphere
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from io import BytesIO
from tqdm import tqdm
from pyproj import Transformer
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from gios_gw_mappings.gios_gw_mapping import selected_columns, DATA_ALIASES, PARAMETER_SELECTION

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize transformer for coordinate conversion
transformer = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)
URL = 'https://mjwp.gios.gov.pl/wyniki-badan/wyniki-badan-2023.html'


def find_subpage_links(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        return [urljoin(url, link.get('href')) for link in soup.find_all('a') if
                link.get('href') and 'wyniki-badan' in link.get('href')]
    except requests.RequestException as e:
        logging.error(f"Error fetching main page: {e}")
        return []


def find_xlsx_links(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        return [(urljoin(url, link.get('href')), link.get_text(strip=True).replace('/', '-')) for link in
                soup.find_all('a') if link.get('href') and link.get('href').endswith('.xlsx')]
    except requests.RequestException as e:
        logging.error(f"Error fetching subpage: {e}")
        return []


def process_xlsx(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return pd.read_excel(BytesIO(response.content))
    except requests.RequestException as e:
        logging.error(f"Error fetching xlsx file: {e}")
        return None


def convert_coords(row):
    try:
        lon, lat = transformer.transform(row['PUWG 1992 X'], row['PUWG 1992 Y'])
        return pd.Series([lat, lon])
    except Exception as e:
        logging.error(f"Error converting coordinates for row {row}: {e}")
        return pd.Series([None, None])


def convert_to_float(value):
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
        value = value.replace("<", "").strip()
        try:
            return float(value)
        except ValueError:
            return value  # Leave as is if conversion fails
    return value


def get_data(url):
    subpage_links = find_subpage_links(url)
    all_data = []

    with ThreadPoolExecutor() as executor:
        future_to_url = {executor.submit(find_xlsx_links, subpage): subpage for subpage in subpage_links}
        xlsx_links = []

        for future in as_completed(future_to_url):
            xlsx_links.extend(future.result())

        for xlsx_url, file_name in tqdm(xlsx_links, desc="Processing files"):
            df = process_xlsx(xlsx_url)
            if df is not None:
                # Filter and rename columns based on selected_columns dictionary
                cols_to_use = set(selected_columns.keys()).intersection(df.columns)
                df = df[list(cols_to_use)]
                df.rename(columns=selected_columns, inplace=True)

                if 'id' in df.columns:
                    df['id'] = pd.to_numeric(df['id'], errors='coerce').fillna(0).astype(int)

                # Convert PUWG 1992 coordinates to WGS84 lat/lon if applicable
                if 'PUWG 1992 X' in df.columns and 'PUWG 1992 Y' in df.columns:
                    coords = df.apply(convert_coords, axis=1)
                    df['lat'] = coords[0]
                    df['lon'] = coords[1]
                    df.drop(columns=["PUWG 1992 X", "PUWG 1992 Y"], inplace=True)

                # Apply conversion selectively to relevant columns, excluding "Range of Captured Aquifer Layer"
                columns_to_convert = df.select_dtypes(include=['object']).columns
                columns_to_convert = [col for col in columns_to_convert if
                                      col not in ["Type of Measurement Point", "Range of Captured Aquifer Layer"]]

                for col in columns_to_convert:
                    df[col] = df[col].apply(convert_to_float)

                if 'year' in df.columns:
                    df['year'] = pd.to_datetime(df['year'], format='%Y', errors='coerce').dt.year

                # Replace specific values for better consistency
                df.replace({
                    "n.o.": np.nan, "b.d.": np.nan, "brak danych": np.nan,
                    "st. wiercona": "well", "st. kopana": "well",
                    "piezometr": "piezometer", "źródło": "spring",
                    "łata wodowskazowa": "water level gauge",
                    "szyb kopalniany": "mineshaft", "otw badawczy": "test hole"
                }, inplace=True)

                all_data.append(df)

    final_df = pd.concat(all_data, ignore_index=True)
    final_df.dropna(how='all', inplace=True)
    final_df = final_df.sort_values(by="year").reset_index(drop=True)

    # Set 'id' column as the first column
    columns_order = ['id'] + [col for col in final_df.columns if col != 'id']
    final_df = final_df[columns_order]

    # Add S2 cell ID based on coordinates if latitude and longitude are available
    if "lat" in final_df.columns and "lon" in final_df.columns:
        final_df['S2CELL'] = final_df.apply(lambda x: s2sphere.CellId.from_lat_lng(
            s2sphere.LatLng.from_degrees(x['lat'], x['lon'])).parent(18).id() if pd.notnull(x['lat']) and pd.notnull(
            x['lon']) else None, axis=1)

    return final_df


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
    coordinates = pd.read_csv('constants/gios_gw_stations.csv')
    coordinates.lat = coordinates.lat.astype('float32')
    coordinates.lon = coordinates.lon.astype('float32')
    coordinates = _limit_coordinates(spatial_range=spatial_range, coordinates=coordinates)
    coordinates['S2CELL'] = coordinates.apply(lambda x:
                                              s2sphere.CellId.from_lat_lng(
                                                  s2sphere.LatLng.from_degrees(x.lat, x.lon)).parent(level).id(),
                                              axis=1)
    return coordinates


def read_data(spatial_range: object, time_range: object, data_range: object, level: object) -> object:
    # Extract years from time range
    time_from, time_to = time_range
    time_from = datetime.strptime(time_from, '%Y-%m-%d').year
    time_to = datetime.strptime(time_to, '%Y-%m-%d').year
    coordinates = _prepare_coordinates(spatial_range=spatial_range, level=level)

    # Get the final data from the `get_data` function
    final_df = get_data(URL)
    if final_df.empty:
        logging.warning("No data to process in `read_data`.")
        return pd.DataFrame()  # Return an empty DataFrame if no data

    # Filter `final_df` by time range
    final_df = final_df[(final_df['year'] >= time_from) & (final_df['year'] <= time_to)]

    # Map `data_range` to available parameters in `final_df`
    data_requested = set([k for k, v in DATA_ALIASES.items() if v in data_range])
    parameter_selection = list(set(PARAMETER_SELECTION).intersection(data_requested))

    # Filter columns in `final_df` based on `parameter_selection` and add `year`, `id`, and `S2CELL` if present
    columns_to_select = ['S2CELL', 'year'] + parameter_selection
    columns_to_select = [col for col in columns_to_select if col in final_df.columns]  # Ensure columns exist
    final_df = final_df[columns_to_select]

    # Return the filtered DataFrame for further processing
    return final_df


if __name__ == "__main__":
    final_data = get_data(URL)
    N, S, E, W = 59.0, 49.0, 24.2, 15.2
    LEVEL = 18
    TIME_FROM, TIME_TO = '1991-01-01', '2024-12-31'
    FACTORS = ["groundwater quality"]

    result = read_data(spatial_range=(N, S, E, W), time_range=(TIME_FROM, TIME_TO),
                       data_range=FACTORS, level=LEVEL)
    print(result)

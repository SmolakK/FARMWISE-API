import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from io import BytesIO
from tqdm import tqdm
from pyproj import Transformer
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

# Initialize transformer for coordinate conversion
transformer = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)
URL = 'https://mjwp.gios.gov.pl/wyniki-badan/wyniki-badan-2023.html'

# Define selected columns for extraction and renaming
selected_columns = {
    "PUWG 1992 X": "PUWG 1992 X",
    "PUWG 1992 Y": "PUWG 1992 Y",
    "Miejscowość": "name",
    "Numer punktu pomiarowego wg MONBADA": "id"
}


def find_subpage_links(url):
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    return [urljoin(url, link.get('href')) for link in soup.find_all('a') if
            link.get('href') and 'wyniki-badan' in link.get('href')]


def find_xlsx_links(url):
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    return [(urljoin(url, link.get('href')), link.get_text(strip=True).replace('/', '-')) for link in soup.find_all('a')
            if link.get('href') and link.get('href').endswith('.xlsx')]


def process_xlsx(url):
    response = requests.get(url)
    response.raise_for_status()
    return pd.read_excel(BytesIO(response.content))


def convert_coords(row):
    lon, lat = transformer.transform(row['PUWG 1992 X'], row['PUWG 1992 Y'])
    return pd.Series([lat, lon])


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
                df = df[[col for col in selected_columns.keys() if col in df.columns]]
                df.rename(columns=selected_columns, inplace=True)
                # Convert 'Point_id' column to integer if possible
                if 'id' in df.columns:
                    df['id'] = pd.to_numeric(df['id'], errors='coerce').fillna(0).astype(int)

                if "PUWG 1992 X" in df.columns and "PUWG 1992 Y" in df.columns:
                    lat_lon = df.apply(convert_coords, axis=1)
                    df['lat'] = lat_lon[0]
                    df['lon'] = lat_lon[1]
                    df.drop(columns=["PUWG 1992 X", "PUWG 1992 Y"], inplace=True)

                all_data.append(df[['id', 'name', 'lat', 'lon']])

    final_df = pd.concat(all_data, ignore_index=True).dropna(subset=['lat', 'lon']).drop_duplicates()
    return final_df


# Save data to CSV in the current working directory
if __name__ == "__main__":
    final_data = get_data(URL)

    # Specify the output path for clarity
    output_path = os.path.join(os.getcwd(), 'constants/gios_gw_stations.csv')

    try:
        # Save the DataFrame to a CSV file
        final_data.to_csv(output_path, index=False)
        print(f"Data successfully saved to '{output_path}' with distinct latitude and longitude values.")
    except Exception as e:
        # Catch any errors and print them
        print("An error occurred while saving the file:", e)
        
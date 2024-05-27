import requests
from bs4 import BeautifulSoup
import pandas as pd
from tqdm import tqdm
from utils.name_to_coordinates import get_coordinates


def generate_urls(base_url, start=2, end=32, step=2):
    # Generate a list of URLs based on a range of numbers
    return [f"{base_url}{i:02d}" for i in range(start, end + 1, step)]


def fetch_and_parse(url):
    # Fetch URL content and parse it with BeautifulSoup.
    response = requests.get(url)
    if response.status_code == 200:
        return BeautifulSoup(response.content, 'html.parser')
    return None  # Return None if response is not OK


def extract_data(soup):
    # Extract data from parsed HTML soup.

    if soup is None:
        return []
    spans = soup.find_all('span', class_='w1')
    data = [{'id': int(spans[i].get_text(strip=True)),
             'name': spans[i + 1].get_text(strip=True) + ', Poland'}
            for i in range(0, len(spans), 2)]
    return data


# Setup base URL
base_url = 'https://www.gios.gov.pl/chemizm_gleb/index.php?mod=pomiary&w='

# Generate URLs
urls = generate_urls(base_url)

# Fetch and process data
all_data = []
for url in tqdm(urls, desc="Fetching URLs"):
    soup = fetch_and_parse(url)
    all_data.extend(extract_data(soup))

# Convert list of dicts to DataFrame
df = pd.DataFrame(all_data)

# Add coordinates to DataFrame using tqdm for progress indication

tqdm.pandas(desc="Fetching Coordinates")
df['coordinates'] = df['name'].progress_apply(get_coordinates)

# Split coordinates into latitude and longitude

df[['lat', 'lon']] = pd.DataFrame(df['coordinates'].tolist(), index=df.index)

# Clean up the DataFrame by removing the 'coordinates' column
df.drop(columns=['coordinates'], inplace=True)

# Save to CSV

df.to_csv('gios_coordinates.csv', index=False)
print("Data has been processed and saved to 'gios_coordinates.csv'.")

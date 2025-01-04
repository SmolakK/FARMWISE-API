import pandas as pd
from tqdm import tqdm
from utils.name_to_coordinates import get_coordinates
from API_readers.gios.gios_utils import generate_urls, fetch_and_parse, extract_data

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

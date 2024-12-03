import requests
from bs4 import BeautifulSoup


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

import re
import os
import pandas as pd
import requests
from bs4 import BeautifulSoup

def ensure_directory_exists(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def extract_point_ids(url):
    page = requests.get(url)
    soup = BeautifulSoup(page.text, "html.parser")
    links = soup.find_all('a')
    point_ids = []
    for link in links:
        href = link.get('href')
        if href:
            matches = re.findall(r'p=(\d+)', href)
            point_ids.extend(matches)
    return ','.join(point_ids)

def scrape_point_data(point_id, directory):
    ensure_directory_exists(directory)
    url = f'https://www.gios.gov.pl/chemizm_gleb/index.php?mod=pomiary&p={point_id}'
    page = requests.get(url)
    soup = BeautifulSoup(page.text, "html.parser")

    columns = []
    rows = []

    table_headers = soup.find_all('th')
    for th in table_headers:
        columns.append(th.text.strip())
    columns = [col for col in columns if col != 'Rok']

    table_data = soup.find_all('td')[3:]
    for td in table_data:
        rows.append(td.text.strip())

    smaller_columns = [columns[i:i + 8] for i in range(0, len(columns), 8)]
    smaller_rows = [rows[i:i + 8] for i in range(0, len(rows), 8)]

    headers_list = [';'.join(headers) for headers in smaller_columns]
    rows_list = [';'.join(row) for row in smaller_rows]

    headers_df = pd.DataFrame([headers_list[0].split(';')], columns=headers_list[0].split(';'))
    data = [row.split(';') for row in rows_list]

    for row in data:
        for i in range(2, len(row)):
            if re.match(r"^\d+,\d+$", row[i]):
                row[i] = row[i].replace(",", ".")

    rows_df = pd.DataFrame(data, columns=headers_df.columns)
    rows_df.iloc[:, 0:2] = rows_df.iloc[:, 0:2].astype(str)

    rows_df.insert(0, 'point_id', point_id)

    filename = os.path.join(directory, f'point_{point_id}.csv')
    rows_df.to_csv(filename, index=False)

def main():
    point_id_url = 'https://www.gios.gov.pl/chemizm_gleb/index.php?mod=pomiary'
    point_ids = extract_point_ids(point_id_url)

    directory = "data"  # Save files in a subfolder named 'data'

    for point_id in point_ids.split(','):
        scrape_point_data(point_id, directory)

if __name__ == "__main__":
    main()
import re
import os
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup


# def ensure_directory_exists(directory):
#     if not os.path.exists(directory):
#         os.makedirs(directory)


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


def main():
    point_id_url = 'https://www.gios.gov.pl/chemizm_gleb/index.php?mod=pomiary'
    point_ids = extract_point_ids(point_id_url)

    all_dataframes = []

    # list of parameters in the parameter column
    parameter_values = [
        'BN-78/9180-11: 1.0-0.1 mm [%]', 'BN-78/9180-11: 0.1-0.02 mm [%]', 'BN-78/9180-11: < 0.02 mm [%]',
        'PTG 2008: 2.0-0.05 mm [%]', 'PTG 2008: 0.05-0.002 mm [%]', 'PTG 2008: < 0.002 mm [%]', 'pH_H2O [pH]',
        'pH_KCl [pH]', 'CaCo3 [%]', 'humus [%]', 'organic_carbon [%]', 'total_nitrogen [%]', 'c/n [-]',
        'Hh [cmol(+)*kg-1]', 'Hw [cmol(+)*kg-1]', 'Al [cmol(+)*kg-1]', 'Ca2+ [cmol(+)*kg-1]', 'Mg2+ [cmol(+)*kg-1]',
        'Na+ [cmol(+)*kg-1]', 'K+ [cmol(+)*kg-1]', 'S [cmol(+)*kg-1]', 'T [cmol(+)*kg-1]', 'V [%]',
        'available ammonium nitrogen [NNH4 mg*kg-1]', 'available potassium [mg K2O*100g-1]',
        'available magnesium [mg Mg*100g-1]',
        'available sulphur [mg S-SO4*100g-1]', 'available ammonium nitrogen [NNH4 mg*kg-1]',
        'available nitrate nitrogen [NNO3 mg*kg-1]',
        'P [%]', 'Ca [%]', 'Mg [%]', 'K [%]', 'Na [%]', 'S [%]', 'Al [%]', 'Fe [%]', 'Mn [mg*kg-1]', 'Cd [mg*kg-1]',
        'Cu [mg*kg-1]', 'Cr [mg*kg-1]', 'Ni [mg*kg-1]', 'Pb [mg*kg-1]', 'Zn [mg*kg-1]', 'Co [mg*kg-1]', 'V [mg*kg-1]',
        'Li [mg*kg-1]',
        'Be [mg*kg-1]', 'Ba [mg*kg-1]', 'Sr [mg*kg-1]', 'La [mg*kg-1]', 'Hg [mg*kg-1]', 'As [mg*kg-1]',
        'PAH_sum_13 [µg*kg-1]',
        'naphthalene [µg*kg-1]', 'phenanthrene [µg*kg-1]', 'anthracene [µg*kg-1]', 'fluoranthene [µg*kg-1]',
        'chrysene [µg*kg-1]', 'benzo(a)anthracene [µg*kg-1]', 'benzo(a)pyrene [µg*kg-1]',
        'benzo(a)fluoranthene [µg*kg-1]',
        'benzo(ghi)perylene [µg*kg-1]', 'fluorene [µg*kg-1]', 'pyrene [µg*kg-1]', 'benzo(b)fluoranthene [µg*kg-1]',
        'benzo(k)fluoranthene [µg*kg-1]', 'dibenzo(a.h)anthracene [µg*kg-1]', 'indeno(1.2.3-cd)pyrene [µg*kg-1]',
        'organochlorine_pesticides_DDT/DDE/DDD [mg*kg-1]', 'organochlorine_pesticides_aldrin [mg*kg-1]',
        'organochlorine_pesticides_dieldrin [mg*kg-1]', 'organochlorine_pesticides_endrin [mg*kg-1]',
        'organochlorine_pesticides_alfa-HCH [mg*kg-1]', 'organochlorine_pesticides_beta-HCH [mg*kg-1]',
        'organochlorine_pesticides_gamma-HCH [mg*kg-1]', 'pesticides_non_chlorinated_compounds_carbaryl [mg*kg-1]',
        'pesticides_non_chlorinated_compounds_carbofuran [mg*kg-1]',
        'pesticides_non_chlorinated_compounds_maneb [mg*kg-1]',
        'pesticides_non_chlorinated_compounds_atrazin [mg*kg-1]', 'radioactivity [Bq*kg-1]',
        'soil_electrical_conductivity [mS*m-1]',
        'soil_salinity [mg KCl*100g-1]'
    ]

    # Keeping the same order for the parameters
    parameter_order = parameter_values

    for point_id in point_ids.split(','):
        df = scrape_point_data(point_id, parameter_values, parameter_order)
        all_dataframes.append(df)

    # Combine all dataframes into one
    final_dataframe = pd.concat(all_dataframes, ignore_index=True)

    return final_dataframe


if __name__ == "__main__":
    final_dataframe = main()

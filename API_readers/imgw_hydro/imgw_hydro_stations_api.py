import sys
import requests
import pandas as pd
from io import StringIO
from tqdm import tqdm
from utils.name_to_coordinates import get_coordinates

url = r"https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_hydrologiczne/lista_stacji_hydro.csv"
wykaz_stacji = requests.get(url)
wykaz_stacji.encoding = 'windows-1250'
wykaz_stacji = wykaz_stacji.text
wykaz_stacji = StringIO(wykaz_stacji)
df = pd.read_csv(wykaz_stacji, header=None, names = ['Name','Code',"Value"], encoding='UTF-8')
df['Name'] = df['Name'] + ',Poland'
tqdm.pandas(desc="Processing")
df['coordinates'] = df['Name'].progress_apply(get_coordinates)
df[['lat','lon']] = df.coordinates.astype(str).str.split(',',expand=True)
df.lat = df.lat.str.replace('(','')
df.lon = df.lon.str.replace(')','')
df.to_csv(r'imgw_coordinates.csv')

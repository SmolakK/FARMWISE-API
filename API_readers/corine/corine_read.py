import httpx
import requests
import numpy as np
import pandas as pd
from PIL import Image
from io import BytesIO
from utils.interpolate_data import how_many
from utils.coordinates_to_cells import prepare_coordinates
from utils.interpolate_data import interpolate
from API_readers.corine.corine_mappings.corine_mapping import PARAMETERS_SELECTION
from datetime import datetime, date
import asyncio


async def read_data(spatial_range, time_range, data_range, level):
    """
    N = 51.2
    S = 49.0
    E = 17.1
    W = 15.0
    LEVEL = 8
    TIME_FROM = '2010-01-01'
    TIME_TO = '2023-12-31'
    FACTORS = ['land cover']

    df = read_data((N, S, E, W),(TIME_FROM,TIME_TO),FACTORS,LEVEL)

    :param spatial_range: A tuple containing the spatial range (N, S, E, W) defining the bounding box.
    :param time_range: A tuple containing the start and end timestamps defining the time range.
    :param data_range: A list of properties requested.
                       Allowed CORINE properties: 'land cover'
    :param level: S2Cell level.
    :return: A pandas DataFrame containing the processed data.
    """
    # Define the base URL for the CORINE Land Cover SERVICES
    avail_years = [1990,2000,2006,2012,2018,2024]
    avail_years = [(avail_years[x],avail_years[x+1]) for x in range(len(avail_years)-1)]
    start, end = time_range
    start = datetime.strptime(start, '%Y-%m-%d').date()
    end = datetime.strptime(end, '%Y-%m-%d').date()
    between_years = [(s,e) for s,e in avail_years if e >= start.year]

    stacked_df = []
    async with httpx.AsyncClient() as client:
        for year_start,year_end in between_years:
            base_url = "https://image.discomap.eea.europa.eu/arcgis/rest/services/Corine/CLC{}_WM/MapServer/export".format(year_start)

            # Define the query parameters
            north, south, east, west = spatial_range
            size_lat, size_lon = how_many(north, south, east, west, level)

            params = {
                'bbox': f"{west},{south},{east},{north}",  # Bounding box (xmin, ymin, xmax, ymax)
                'bboxSR': '4326',  # Spatial reference (EPSG:4326 for WGS84)
                'size': f"{size_lon},{size_lat}",  # Image size (width, height)
                'imageSR': '4326',  # Spatial reference for the output image
                'format': format,  # Output image format (e.g., png, jpeg)
                'f': 'image'  # Return the result as an image
            }

            # Make the GET request to the API
            response = await client.get(base_url, params=params)

            # Check if the response is successful
            if response.status_code == 200:
                print("Image successfully retrieved.")

                # Process image asynchronously
                image = await asyncio.to_thread(Image.open, BytesIO(response.content))
                image_array = await asyncio.to_thread(np.array, image)

                # Generate lat/lon for each pixel
                latitudes = np.linspace(south, north, size_lat)
                longitudes = np.linspace(west, east, size_lon)

                data_rows = []
                for i, lat in enumerate(latitudes):
                    for j, lon in enumerate(longitudes):
                        coors = {'lat': lat, 'lon': lon}
                        coors.update({k:v for k,v in zip(PARAMETERS_SELECTION,image_array[i,j])})
                        data_rows.append(coors)

                # Convert data to DataFrame asynchronously
                df = await asyncio.to_thread(pd.DataFrame.from_dict, data_rows)
                df = await asyncio.to_thread(prepare_coordinates, df, spatial_range, level)
                df = df.set_index('S2CELL')
                df = df.groupby(level=0).mean().reset_index()

                # Explode to days
                if start.year > year_start:
                    explode_start = start
                else:
                    explode_start = date(year_start,1,1)
                if year_end > end.year:
                    explode_end = end
                else:
                    explode_end = date(year_end, 12, 31)
                days = pd.date_range(explode_start, explode_end, freq='D')
                df = pd.concat([df.assign(Timestamp=dates) for dates in days])

                # Data interpolation
                if level >= 18:
                    df = interpolate(df, spatial_range, level)
                    df = df.reset_index().rename({'level_0': 'S2CELL', 'level_1': 'Timestamp'}, axis=1)
                else:
                    df = df.drop(['lat', 'lon'], axis=1)
                stacked_df.append(df)

    # Concatenate and pivot data asynchronously
    final_df = await asyncio.to_thread(pd.concat, stacked_df)
    final_df = await asyncio.to_thread(final_df.pivot_table, index='Timestamp', columns='S2CELL')

    return final_df

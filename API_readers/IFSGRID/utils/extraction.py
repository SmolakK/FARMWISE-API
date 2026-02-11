import geopandas as gpd
import numpy as np
import pandas as pd

def extract_values(shp_path:str, factor_feature:str, bbox:tuple) -> pd.DataFrame:
    
    with gpd.read_file(shp_path) as src:
        gdf = src.to_crs(epsg=4326)

    gdf_bbox = gdf[gdf.geometry.intersects(bbox)]
    gdf_bbox['geometry'] = gdf_bbox["geometry"].centroid

    feature_value = pd.DataFrame()
    feature_value['lon'] = gdf_bbox.geometry.x
    feature_value['lat'] = gdf_bbox.geometry.y
    feature_value['factor'] = gdf_bbox[factor_feature]

    return feature_value

import geopandas as gpd
import pandas as pd
from typing import Tuple
import os
import json

def factor_mapping_extractor(factor, aliasaes, data_path):

    with open(r"API_readers\IFSGRID\utils\definitions.json", "r") as f:
        file = json.load(f)

    code_file = {}
    for fac in file:
        for var in file[fac]["variables"]:
            code_file[var['code']] = var['file']    

    shpfile_paths = {}
    for key in aliasaes:
        if aliasaes[key] == factor[0]:
            filename = code_file[key]
            shpfile_paths[key] = os.path.join(data_path,filename,f'{filename}.shp')
    
    return shpfile_paths

def extract_values(
    shp_path: str,
    factor_feature: str,
    bbox: Tuple[float, float, float, float]
) -> pd.DataFrame:
    """
    Extract feature values and centroid coordinates from a shapefile
    for geometries intersecting a given bounding box.

    Parameters
    ----------
    shp_path : str
        Path to the input shapefile (or any format supported by GeoPandas).
    factor_feature : str
        Name of the attribute column to extract.
    bbox : tuple of float (minx, miny, maxx, maxy)
        Bounding box in EPSG:4326 coordinate reference system.

    Returns
    -------
    pd.DataFrame
        DataFrame containing lon, latand value from the selected 
            attribute column.
    """
    gdf = gpd.read_file(shp_path)

    if factor_feature not in gdf.columns:
        raise ValueError(f"Column '{factor_feature}' not found in dataset.")
    if gdf.crs is None:
        raise ValueError("Input data has no CRS defined.")
    if gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    gdf_bbox = gdf[gdf.geometry.intersects(bbox)].copy()

    if gdf_bbox.empty:
        return pd.DataFrame(columns=["lon", "lat", "factor"])

    gdf_bbox["geometry"] = gdf_bbox.geometry.centroid
    result = pd.DataFrame({
        "lon": gdf_bbox.geometry.x,
        "lat": gdf_bbox.geometry.y,
        factor_feature: gdf_bbox[factor_feature].values
    })
    from shapely.geometry import Point
    geometry = [Point(xy) for xy in zip(result["lon"], result["lat"])]
    gdf = gpd.GeoDataFrame(result, geometry=geometry, crs="EPSG:4326")
    gdf.to_file("result.shp")

    return result


def stack_values():
    pass
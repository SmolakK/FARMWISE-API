import os
import json
from shapely.geometry import Polygon
import geopandas as gpd
import pandas as pd
from API_readers.IFSGRID.mappings.IFSGRID_mappings import DATA_ALIASES

def factor_mapping_extractor(factor:str) -> dict:
    """
    Extract shapefile paths corresponding to a given factor.

    Parameters
    ----------
    factor : str
        Logical factor name defined in DATA_ALIASES mapping.

    Returns
    -------
    dict
        Dictionary mapping feature codes to absolute shapefile paths.
    """
    DATASET = os.path.join(
        'API_readers',
        'IFSGRID',
        'data',
        'IFSGRID',
        'data'
    )
    
    with open(
        os.path.join(
            'API_readers','IFSGRID','utils','definitions.json'
            ), 
            "r"
        ) as f:
        file = json.load(f)

    code_file = {}
    for fac in file:
        for var in file[fac]["variables"]:
            code_file[var['code']] = var['file']    

    shpfile_paths = {}
    for key in DATA_ALIASES:
        if DATA_ALIASES[key] == factor:
            filename = code_file[key]
            shpfile_paths[key] = os.path.join(
                DATASET,filename,f'{filename}.shp'
            )
    
    return shpfile_paths

def extract_values(
    shp_path: str,
    factor_feature: str,
    bbox: Polygon
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

    utm_crs = gdf_bbox.estimate_utm_crs()
    gdf_proj = gdf_bbox.to_crs(utm_crs)
    centroids = gdf_proj.geometry.centroid
    centroids = gpd.GeoSeries(centroids, crs=utm_crs).to_crs(epsg=4326)
    gdf_bbox["geometry"] = centroids.values
    result = pd.DataFrame({
        "lon": gdf_bbox.geometry.x,
        "lat": gdf_bbox.geometry.y,
        factor_feature: gdf_bbox[factor_feature].values
    })
    return result


def stack_values(data_range:list, bbox:Polygon) -> pd.DataFrame:
    """
    Stack multiple factor values into a single DataFrame
    based on shared spatial coordinates.

    Parameters
    ----------
    data_range : list of str
        List of logical factor names to extract.
    bbox : Polygon
        Bounding box in EPSG:4326 coordinate reference system.

    Returns
    -------
    pd.DataFrame
        DataFrame containing merged factor values aligned by
        latitude and longitude. Returns empty DataFrame if
        no data is found.
    """
    factor_data_frame = pd.DataFrame(columns=['lat','lon'])
    for factor in data_range:
        data_paths = factor_mapping_extractor(factor)
        for key, value in data_paths.items():
            try:
                data = extract_values(value, key, bbox)
                factor_data_frame = pd.merge(
                    factor_data_frame, 
                    data, 
                    on=["lat", "lon"], 
                    how="outer"
                )
            except Exception as e:
                print(value, e)

    if factor_data_frame.empty:
        return pd.DataFrame()
    else: 
        return factor_data_frame
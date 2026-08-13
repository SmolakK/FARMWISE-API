import json
from pathlib import Path


def return_country_bboxes():
    jpath = Path(__file__).with_name("country_codes")
    with jpath.open("r", encoding="utf-8") as jfile:
        country_json = json.load(jfile)

    COUNTRY_BBOXES = {}

    for country in country_json.values():
        region = country.get("region", "")
        if region != "Europe":
            continue  # Skip non-European countries

        name = country["name"]
        bbox = country["boundingBox"]
        north = bbox["ne"]["lat"]
        south = bbox["sw"]["lat"]
        east = bbox["ne"]["lon"]
        west = bbox["sw"]["lon"]
        COUNTRY_BBOXES[name] = (north, south, east, west)

    return COUNTRY_BBOXES

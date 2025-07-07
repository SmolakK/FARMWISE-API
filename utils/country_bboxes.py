import json


def return_country_bboxes():
    jpath = f'utils\country_codes'
    with open(jpath,'r') as jfile:
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

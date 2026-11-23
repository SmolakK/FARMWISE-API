import json
from pathlib import Path

# The Urals, the conventional eastern edge of Europe. The source box for the
# Russian Federation runs to 180 degrees east, so a request naming it (or a
# list of European countries including it) covered Siberia as well: about
# three times the width of Europe, downloaded and processed by every source.
EUROPE_EAST_LIMIT = 60.0


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
        east = min(bbox["ne"]["lon"], EUROPE_EAST_LIMIT)
        west = bbox["sw"]["lon"]
        COUNTRY_BBOXES[name] = (north, south, east, west)

    return COUNTRY_BBOXES

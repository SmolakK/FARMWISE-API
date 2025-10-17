import time

from geopy.exc import GeocoderUnavailable
from geopy.geocoders import Nominatim


def get_coordinates(city_name, retries=10, wait_time=20):
    """
    Fetches the geographical coordinates (latitude and longitude) for a given city name.

    This function attempts to geocode the city name using the Nominatim service.
    If the service is unavailable, it will retry up to a specified number of attempts,
    waiting a defined amount of time between retries.

    :param city_name: The name of the city for which to retrieve coordinates.
    :param retries: The number of times to retry fetching coordinates in case of a geocoding error (default is 10).
    :param wait_time: The time in seconds to wait between retry attempts (default is 20 seconds).
    :return: A tuple containing the latitude and longitude of the city. Returns (None, None) if unsuccessful.
    """
    geolocator = Nominatim(user_agent='geocoder')
    for attempt in range(retries):
        try:
            location = geolocator.geocode(city_name, timeout=20)
            if location:
                return location.latitude, location.longitude
            else:
                return None, None
        except GeocoderUnavailable as e:
            print(f"Geocoder unavailable for {city_name}, retrying... (Attempt {attempt + 1}/{retries})")
            time.sleep(wait_time)  # Wait before retrying
    print(f"Failed to fetch coordinates for {city_name} after {retries} attempts")
    return None, None

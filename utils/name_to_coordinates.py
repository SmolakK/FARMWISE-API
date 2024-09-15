import time
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderUnavailable

def get_coordinates(city_name, retries=10, wait_time=20):
    geolocator = Nominatim(user_agent='geocoder')
    for attempt in range(retries):
        try:
            location = geolocator.geocode(city_name, timeout=20)
            if location:
                return location.latitude, location.longitude
            else:
                return None
        except GeocoderUnavailable as e:
            print(f"Geocoder unavailable for {city_name}, retrying... (Attempt {attempt + 1}/{retries})")
            time.sleep(wait_time)  # Wait before retrying
    print(f"Failed to fetch coordinates for {city_name} after {retries} attempts")
    return None, None

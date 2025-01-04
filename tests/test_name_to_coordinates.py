import pytest
from unittest.mock import patch, MagicMock
from geopy.exc import GeocoderUnavailable
from utils.name_to_coordinates import get_coordinates


# Test successful geocoding
@patch('utils.name_to_coordinates.Nominatim')
def test_get_coordinates_success(mock_nominatim):
    # Mock Nominatim and its geocode method
    mock_geolocator = MagicMock()
    mock_nominatim.return_value = mock_geolocator
    mock_geolocator.geocode.return_value = MagicMock(latitude=40.7128, longitude=-74.0060)

    city_name = "New York"
    lat, lon = get_coordinates(city_name)

    assert lat == 40.7128, "Latitude should match the mocked value"
    assert lon == -74.0060, "Longitude should match the mocked value"
    mock_geolocator.geocode.assert_called_once_with(city_name, timeout=20)


# Test geocoding failure with retries
@patch('utils.name_to_coordinates.Nominatim')
def test_get_coordinates_failure_with_retries(mock_nominatim):
    # Mock Nominatim and simulate GeocoderUnavailable exception
    mock_geolocator = MagicMock()
    mock_nominatim.return_value = mock_geolocator
    mock_geolocator.geocode.side_effect = GeocoderUnavailable

    city_name = "Unavailable City"
    lat, lon = get_coordinates(city_name, retries=3, wait_time=0)  # Reduced retries and wait_time for faster test

    assert lat is None, "Latitude should be None if geocoding fails"
    assert lon is None, "Longitude should be None if geocoding fails"
    assert mock_geolocator.geocode.call_count == 3, "Should retry the specified number of times"


# Test geocoding with no results
@patch('utils.name_to_coordinates.Nominatim')
def test_get_coordinates_no_results(mock_nominatim):
    # Mock Nominatim and simulate no result
    mock_geolocator = MagicMock()
    mock_nominatim.return_value = mock_geolocator
    mock_geolocator.geocode.return_value = None

    city_name = "Unknown City"
    lat, lon = get_coordinates(city_name)

    assert lat is None, "Latitude should be None if no result is found"
    assert lon is None, "Longitude should be None if no result is found"
    mock_geolocator.geocode.assert_called_once_with(city_name, timeout=20)

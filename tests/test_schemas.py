import pytest
from pydantic import ValidationError
from schemas import ReadDataRequest
from schemas import UserCreate, Token

valid_bounding_box = (35.0, 34.0, -117.0, -118.0)
valid_time_from = "2024-01-01"
valid_time_to = "2024-01-31"
valid_factors = ["temperature", "precipitation"]  # Update this based on `valid_factors` in your application


def test_valid_read_data_request():
    data = {
        "bounding_box": valid_bounding_box,
        "level": 10,
        "time_from": valid_time_from,
        "time_to": valid_time_to,
        "factors": valid_factors,
        "separate_api": True,
        "interpolation": False,
    }
    request = ReadDataRequest(**data)
    assert request.bounding_box == valid_bounding_box
    assert request.level == 10
    assert request.time_from == valid_time_from
    assert request.time_to == valid_time_to
    assert request.factors == valid_factors


def test_invalid_date_format():
    with pytest.raises(ValidationError, match="Date must be in YYYY-MM-DD format"):
        ReadDataRequest(
            bounding_box=valid_bounding_box,
            level=10,
            time_from="01-01-2024",  # Invalid date format
            time_to=valid_time_to,
            factors=valid_factors,
        )


def test_invalid_bounding_box():
    with pytest.raises(ValidationError):
        ReadDataRequest(
            bounding_box=(35.0, -118.0),  # Incorrect length
            level=10,
            time_from=valid_time_from,
            time_to=valid_time_to,
            factors=valid_factors,
        )

    with pytest.raises(ValidationError):
        ReadDataRequest(
            bounding_box=(34.0, 35.0, -117.0, -118.0),  # Invalid order
            level=10,
            time_from=valid_time_from,
            time_to=valid_time_to,
            factors=valid_factors,
        )


def test_invalid_factors():
    with pytest.raises(ValidationError, match="Factors must be within"):
        ReadDataRequest(
            bounding_box=valid_bounding_box,
            level=10,
            time_from=valid_time_from,
            time_to=valid_time_to,
            factors=["invalid_factor"],  # Not in `valid_factors`
        )


def test_valid_user_create():
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "strongpassword",
    }
    user = UserCreate(**user_data)
    assert user.username == "testuser"
    assert user.email == "test@example.com"
    assert user.full_name == "Test User"
    assert user.password == "strongpassword"


def test_token_schema():
    token_data = {"access_token": "abcd1234", "token_type": "bearer"}
    token = Token(**token_data)
    assert token.access_token == "abcd1234"
    assert token.token_type == "bearer"

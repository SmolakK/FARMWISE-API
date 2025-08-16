from pydantic import BaseModel, Field, field_validator, EmailStr
from typing import List, Tuple, Optional
from datetime import datetime
from mappings.data_source_mapping import API_PATH_RANGES

# Dynamically extract all unique factors from API_PATH_RANGES
valid_factors = set(
    factor for api_params in API_PATH_RANGES.values() for factor in api_params[2]
)


class ReadDataRequest(BaseModel):
    bounding_box: Optional[Tuple[float, float, float, float]] = Field(
        None,
        example=(34.0, -118.0, 35.0, -117.0),
        description="Tuple of (North, South, East, West) coordinates in decimal degrees."
    )
    country: Optional[List[str]] = Field(
        None,
        description="List of country names. Used as an alternative to bounding box."
    )
    level: int = Field(
        ...,
        gt=0,
        lt=20,
        description="Level must be between 1 and 19."
    )
    time_from: str = Field(
        ...,
        example="2024-01-01",
        description="Start date in YYYY-MM-DD format."
    )
    time_to: str = Field(
        ...,
        example="2024-01-31",
        description="End date in YYYY-MM-DD format."
    )
    factors: List[str] = Field(
        ...,
        example=["temperature", "precipitation"],
        description="List of factors to retrieve data for."
    )
    separate_api: Optional[bool] = Field(
        False,
        description="If True, store APIs in separate columns instead of averaging."
    )
    interpolation: Optional[bool] = Field(
        False,
        description="If True, apply interpolation to the resulting data."
    )

    @field_validator("time_from", "time_to")
    def validate_date(cls, value):
        try:
            datetime.strptime(value, '%Y-%m-%d')
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
        return value

    @field_validator("bounding_box")
    def validate_bounding_box(cls, value):
        if value is None:
            return value  # Allow None if user selects country
        if not (len(value) == 4 and all(isinstance(num, (int, float)) for num in value)):
            raise ValueError("Bounding box must be a tuple of four float or int values.")
        if not (value[0] > value[1] and value[2] > value[3]):
            raise ValueError("Bounding box coordinates must follow the order: (North, South, East, West).")
        return value

    @field_validator("factors")
    def check_factors(cls, value):
        if any(factor not in valid_factors for factor in value):
            raise ValueError(f"Factors must be within {valid_factors}")
        return value


# Define the response model
class ReadDataResponse(BaseModel):
    download_link: str


class UserBase(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None


class UserCreate(UserBase):
    password: str


class User(UserBase):
    id: int

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None

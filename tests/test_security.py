import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session
from security import authenticate_user, create_access_token
from jose import jwt
import os
from security import get_current_user
from fastapi import HTTPException


def test_authenticate_user_valid():
    db = MagicMock(spec=Session)
    mock_user = MagicMock()
    mock_user.hashed_password = "mocked_hashed_password"
    db.query.return_value.filter.return_value.first.return_value = mock_user

    # Mock the verify_password function
    with patch("security.verify_password") as mock_verify_password:
        mock_verify_password.return_value = True  # Simulate successful password verification

        result = authenticate_user(db, "validuser", "plaintextpassword")

        # Assertions
        assert result == mock_user, "User authentication failed for valid credentials"
        mock_verify_password.assert_called_with("plaintextpassword", "mocked_hashed_password")


def test_authenticate_user_invalid_password():
    db = MagicMock(spec=Session)
    mock_user = MagicMock()
    mock_user.hashed_password = "mocked_hashed_password"  # Mocked valid hashed password
    db.query.return_value.filter.return_value.first.return_value = mock_user

    # Mock the verify_password function
    with patch("security.verify_password") as mock_verify_password:
        mock_verify_password.return_value = False  # Simulate unsuccessful password verification

        result = authenticate_user(db, "validuser", "wrongpassword")

        # Assertions
        assert not result, "Authentication succeeded with an incorrect password"
        mock_verify_password.assert_called_once_with("wrongpassword", "mocked_hashed_password")


def test_authenticate_user_nonexistent_user():
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.first.return_value = None

    result = authenticate_user(db, "nonexistentuser", "password")
    assert not result, "Authentication succeeded for a nonexistent user"

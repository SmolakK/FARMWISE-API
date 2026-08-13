from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

import pytest
import jwt
from fastapi import HTTPException
from sqlalchemy.orm import Session
from farmwise_api.server import security
from farmwise_api.server.security import authenticate_user


TEST_SECRET = "test-secret-at-least-32-bytes-long"


def test_authenticate_user_valid():
    db = MagicMock(spec=Session)
    mock_user = MagicMock()
    mock_user.hashed_password = "mocked_hashed_password"
    db.query.return_value.filter.return_value.first.return_value = mock_user

    # Mock the verify_password function
    with patch("farmwise_api.server.security.verify_password") as mock_verify_password:
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
    with patch("farmwise_api.server.security.verify_password") as mock_verify_password:
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


def test_create_access_token_contains_subject_and_expiry(monkeypatch):
    monkeypatch.setattr(security, "SECRET_KEY", TEST_SECRET)
    monkeypatch.setattr(security, "ALGORITHM", "HS256")

    token = security.create_access_token(
        {"sub": "alice"}, expires_delta=timedelta(minutes=5)
    )
    payload = jwt.decode(token, TEST_SECRET, algorithms=["HS256"])

    assert payload["sub"] == "alice"
    assert "exp" in payload


@pytest.mark.asyncio
async def test_get_current_user_returns_database_user(monkeypatch):
    monkeypatch.setattr(security, "SECRET_KEY", TEST_SECRET)
    monkeypatch.setattr(security, "ALGORITHM", "HS256")
    token = security.create_access_token({"sub": "alice"})
    user = SimpleNamespace(username="alice", disabled=False)
    lookup = MagicMock(return_value=user)
    monkeypatch.setattr(security, "get_user_by_username", lookup)

    result = await security.get_current_user(db=MagicMock(), token=token)

    assert result is user
    lookup.assert_called_once_with(ANY, username="alice")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "token",
    [
        "not-a-token",
        jwt.encode({"role": "reader"}, TEST_SECRET, algorithm="HS256"),
    ],
)
async def test_get_current_user_rejects_invalid_token(monkeypatch, token):
    monkeypatch.setattr(security, "SECRET_KEY", TEST_SECRET)
    monkeypatch.setattr(security, "ALGORITHM", "HS256")

    with pytest.raises(HTTPException) as exc_info:
        await security.get_current_user(db=MagicMock(), token=token)

    assert exc_info.value.status_code == 401
    assert exc_info.value.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_get_current_user_rejects_deleted_user(monkeypatch):
    monkeypatch.setattr(security, "SECRET_KEY", TEST_SECRET)
    monkeypatch.setattr(security, "ALGORITHM", "HS256")
    token = security.create_access_token({"sub": "deleted"})
    monkeypatch.setattr(security, "get_user_by_username", MagicMock(return_value=None))

    with pytest.raises(HTTPException) as exc_info:
        await security.get_current_user(db=MagicMock(), token=token)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_active_user_accepts_enabled_user():
    user = SimpleNamespace(disabled=False)

    assert await security.get_current_active_user(user) is user


@pytest.mark.asyncio
async def test_get_current_active_user_rejects_disabled_user():
    with pytest.raises(HTTPException) as exc_info:
        await security.get_current_active_user(SimpleNamespace(disabled=True))

    assert exc_info.value.status_code == 400

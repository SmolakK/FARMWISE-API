from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from farmwise_api.server.routers import auth


@pytest.mark.asyncio
async def test_login_for_access_token_returns_bearer_token(monkeypatch):
    user = SimpleNamespace(username="alice")
    monkeypatch.setattr(auth, "authenticate_user", MagicMock(return_value=user))
    create_token = MagicMock(return_value="encoded-token")
    monkeypatch.setattr(auth, "create_access_token", create_token)
    form = SimpleNamespace(username="alice", password="secret")

    result = await auth.login_for_access_token(form_data=form, db=MagicMock())

    assert result == {"access_token": "encoded-token", "token_type": "bearer"}
    assert create_token.call_args.kwargs["data"] == {"sub": "alice"}


@pytest.mark.asyncio
async def test_login_for_access_token_rejects_invalid_credentials(monkeypatch):
    monkeypatch.setattr(auth, "authenticate_user", MagicMock(return_value=False))
    form = SimpleNamespace(username="alice", password="wrong")

    with pytest.raises(HTTPException) as exc_info:
        await auth.login_for_access_token(form_data=form, db=MagicMock())

    assert exc_info.value.status_code == 401
    assert exc_info.value.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_read_users_me_returns_current_user():
    user = SimpleNamespace(username="alice")

    assert await auth.read_users_me(current_user=user) is user

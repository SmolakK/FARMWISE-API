from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from farmwise_api.server.routers import auth


def _request():
    """A minimal request object; the limiter reads the client address."""
    return SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={},
                           scope={"type": "http"}, app=SimpleNamespace(state=SimpleNamespace()))


@pytest.mark.asyncio
async def test_login_for_access_token_returns_bearer_token(monkeypatch):
    user = SimpleNamespace(username="alice")
    monkeypatch.setattr(auth, "authenticate_user", MagicMock(return_value=user))
    create_token = MagicMock(return_value="encoded-token")
    monkeypatch.setattr(auth, "create_access_token", create_token)
    form = SimpleNamespace(username="alice", password="secret")

    result = await auth.login_for_access_token.__wrapped__(
        request=_request(), form_data=form, db=MagicMock()
    )

    assert result == {"access_token": "encoded-token", "token_type": "bearer"}
    assert create_token.call_args.kwargs["data"] == {"sub": "alice"}


@pytest.mark.asyncio
async def test_login_for_access_token_rejects_invalid_credentials(monkeypatch):
    monkeypatch.setattr(auth, "authenticate_user", MagicMock(return_value=False))
    form = SimpleNamespace(username="alice", password="wrong")

    with pytest.raises(HTTPException) as exc_info:
        await auth.login_for_access_token.__wrapped__(
            request=_request(), form_data=form, db=MagicMock()
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_read_users_me_returns_current_user():
    user = SimpleNamespace(username="alice")

    assert await auth.read_users_me(current_user=user) is user


def test_login_endpoint_is_rate_limited():
    """Password guessing was unthrottled on an internet-facing deployment.

    slowapi wraps a limited endpoint, so the wrapper - and the limit recorded
    on the application - are what prove the decorator is still in place.
    """
    from farmwise_api.server.security import limiter

    assert hasattr(auth.login_for_access_token, "__wrapped__"), (
        "the /token endpoint is no longer wrapped by the rate limiter"
    )
    registered = {
        name: [str(limit.limit) for limit in limits]
        for name, limits in getattr(limiter, "_route_limits", {}).items()
    }
    assert any("token" in name for name in registered), (
        f"no rate limit registered for /token; registered: {registered}"
    )


def test_documentation_endpoints_can_be_disabled(monkeypatch):
    """/docs, /redoc and /openapi.json are unauthenticated: a deployment must
    be able to switch them off without patching the code."""
    import importlib

    monkeypatch.setenv("FARMWISE_PUBLISH_API_DOCS", "0")
    main = importlib.reload(importlib.import_module("farmwise_api.server.main"))
    try:
        assert main.PUBLISH_API_DOCS is False
        assert main.app.docs_url is None
        assert main.app.redoc_url is None
        assert main.app.openapi_url is None
    finally:
        monkeypatch.setenv("FARMWISE_PUBLISH_API_DOCS", "1")
        importlib.reload(main)


def test_documentation_endpoints_are_published_by_default(monkeypatch):
    import importlib

    monkeypatch.delenv("FARMWISE_PUBLISH_API_DOCS", raising=False)
    main = importlib.reload(importlib.import_module("farmwise_api.server.main"))

    assert main.PUBLISH_API_DOCS is True
    assert main.app.docs_url == "/docs"

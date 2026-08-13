"""Command-line and lazy ASGI entry points for FARMWISE."""

from __future__ import annotations

from typing import Any


__all__ = ["app", "run"]

_SERVER_INSTALL_MESSAGE = (
    "FARMWISE server dependencies are not installed. Install them with "
    '`python -m pip install "farmwise-api[server]"`.'
)


def _load_server_app() -> Any:
    """Load the ASGI application only when server functionality is requested."""
    try:
        from farmwise_api.server.main import app as server_app
    except ModuleNotFoundError as error:
        raise RuntimeError(_SERVER_INSTALL_MESSAGE) from error
    return server_app


def __getattr__(name: str) -> Any:
    """Expose the ASGI application lazily for Uvicorn."""
    if name == "app":
        return _load_server_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def run() -> None:
    """Start the FARMWISE ASGI application."""
    try:
        server_app = _load_server_app()
    except RuntimeError as error:
        raise SystemExit(str(error)) from error

    import uvicorn

    uvicorn.run(
        server_app,
        host="0.0.0.0",
        port=8000,
        proxy_headers=True,
    )


if __name__ == "__main__":
    run()

"""Optional server entry point for FARMWISE.

Importing this module must also work for the local-library installation, which
does not install the dependencies from the ``server`` extra.
"""

from __future__ import annotations

from typing import Any


__all__ = ["app", "run"]

_SERVER_INSTALL_MESSAGE = (
    "FARMWISE server dependencies are not installed. Install them with "
    "`python -m pip install \"farmwise-api[server]\"`."
)


def _load_server_app() -> Any:
    """Load the ASGI application only when server functionality is requested."""
    try:
        from server.main import app as server_app
    except ModuleNotFoundError as error:
        raise RuntimeError(_SERVER_INSTALL_MESSAGE) from error
    return server_app


def __getattr__(name: str) -> Any:
    """Provide ``main.app`` lazily for Uvicorn and ASGI imports."""
    if name == "app":
        return _load_server_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def run() -> None:
    """Start the production-facing ASGI application."""
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

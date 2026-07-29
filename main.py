"""Public server entry point for FARMWISE."""

from server.main import app

__all__ = ["app"]


def run() -> None:
    """Start the production-facing ASGI application."""
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        proxy_headers=True,
    )


if __name__ == "__main__":
    run()

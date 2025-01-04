import pytest
from fastapi.testclient import TestClient
from main import app, lifespan
from routers.data_call import api_router
from routers.auth import auth_router
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
import os
from security import setup_security


@pytest.fixture
def client():
    """
    Fixture for creating a test client.
    """
    return TestClient(app)


def test_app_startup_and_shutdown(client):
    """
    Test app startup and shutdown logic.
    """
    with patch("main.start_scheduler") as mock_start_scheduler, \
         patch("main.shutdown_scheduler") as mock_shutdown_scheduler, \
         patch("tempfile.mkdtemp") as mock_mkdtemp, \
         patch("shutil.rmtree") as mock_rmtree:

        # Mock temporary directory creation
        mock_mkdtemp.return_value = "/mock/temp/dir"

        # Simulate lifespan
        with TestClient(app) as client:
            # Verify the start_scheduler was called
            mock_start_scheduler.assert_called_once()

            # Capture the actual argument
            actual_dir = mock_start_scheduler.call_args[0][0]

            # Ensure it is a valid directory
            assert os.path.isdir(actual_dir), f"Expected a valid directory but got {actual_dir}"

        # Assert scheduler stopped and temp dir removed
        mock_shutdown_scheduler.assert_called_once()
        mock_rmtree.assert_called_once_with(actual_dir, ignore_errors=True)


def test_routers_included(client):
    """
    Test that the API routers are included in the app.
    """
    routes = [route.path for route in app.routes]
    assert any("/read-data" in route for route in routes), "Data API router not included"
    assert any("/docs" in route for route in routes), "Auth API router not included"
    assert any("/token" in route for route in routes), "Token API router not included"
    assert any("/users/me" in route for route in routes), "Users Me API router not included"


def test_app_routes(client):
    """
    Test that the application routes are accessible.
    """
    response = client.get("/openapi.json")
    assert response.status_code == 200, "OpenAPI documentation not accessible"

    # Test a route from api_router
    # Replace '/data/example' with a valid endpoint from your API router
    response = client.get("/read-data")
    assert response.status_code == 405, "Data API route not reachable"

    # Test a route from auth_router
    # Replace '/auth/example' with a valid endpoint from your Auth router
    response = client.post("/token", data={"username": "user", "password": "pass"})
    assert response.status_code == 401, "Auth API route not reachable"

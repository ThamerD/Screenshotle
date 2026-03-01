"""
Unit tests for app.main: app creation and built-in routes.
"""

import pytest
from fastapi.testclient import TestClient


def test_create_app_returns_fastapi_app():
    from app.main import create_app
    app = create_app()
    assert app is not None
    assert app.title == "Screenshotle" or "Screenshotle" in app.title


def test_app_has_health_route(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_app_state_has_config(client: TestClient):
    from app.main import app
    assert hasattr(app.state, "config")

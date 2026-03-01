"""
Pytest configuration and shared fixtures.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Return a test client for the FastAPI app."""
    app = create_app()
    return TestClient(app)

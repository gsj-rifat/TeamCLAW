import sys
from unittest.mock import MagicMock, AsyncMock, patch

# CRITICAL: Mock asyncpg module before importing anything that uses it
# This allows tests to run even if asyncpg (C-extension) isn't installed
sys.modules["asyncpg"] = MagicMock()

import pytest
import asyncio
from fastapi.testclient import TestClient
from main import app
from src.infrastructure.container import container
from src.infrastructure.config import settings

# --- Mocks ---
# We mock the entire DB init process to avoid needing a real DB for smoke testing.
mock_init_db = AsyncMock()

# Patch sqlalchemy create_async_engine to prevent actual engine creation attempts
patch_engine = patch("src.adapters.postgres_adapter.create_async_engine", return_value=AsyncMock())
patch_engine.start()

@pytest.fixture
def client():
    # Patch the container's init_resources to prevent real DB connection attempts
    container.init_resources = mock_init_db
    
    # Patch the separate init_db call in main.py lifespan
    # We need to patch where it's imported in main.py
    with patch("main.init_db", new=AsyncMock()) as mock_schema_init:
        with TestClient(app) as test_client:
            yield test_client

def test_health_check(client):
    """Verify /health endpoint works and returns correct structure."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "config" in data
    assert "groq" in data["config"]
    assert "slack" in data["config"]
    assert "jira" in data["config"]

def test_docs_page(client):
    """Verify Swagger UI is served."""
    response = client.get("/docs")
    assert response.status_code == 200

def test_slack_events_endpoint_exists(client):
    """Verify the Slack events endpoint is mounted."""
    # We expect 405 Method Not Allowed for GET, or 403/422 if we POST without signature.
    # Just checking it's there.
    response = client.get("/slack/events")
    assert response.status_code == 405  # It's a POST only endpoint

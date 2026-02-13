import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test the health check endpoint."""
    response = await client.get("/health")

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "nova-agent"


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """Test the root endpoint."""
    response = await client.get("/")

    assert response.status_code == 200

    data = response.json()
    assert data["service"] == "Nova Agent"
    assert "version" in data
    assert "endpoints" in data
    assert "health" in data["endpoints"]

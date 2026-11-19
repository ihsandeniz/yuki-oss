import pytest


@pytest.mark.asyncio
async def test_health_returns_200(client):
    r = await client.get("/health")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_health_has_character_name(client):
    data = (await client.get("/health")).json()
    assert data.get("character") == "Yuki"

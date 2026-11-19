import pytest


@pytest.mark.asyncio
async def test_memory_stats_endpoint(client):
    """/api/memory/stats — 200 ve 'enabled' alanı döner"""
    r = await client.get("/api/memory/stats")
    assert r.status_code == 200
    data = r.json()
    assert "enabled" in data


@pytest.mark.asyncio
async def test_memory_list_endpoint(client, mocker):
    """/api/memory — DB mock ile 200 ve liste döner.

    Hafızanın açık olması ve pgvector servisi test İÇİNDE sabitlenir: `MEMORY_ENABLED`
    `.env`'deki `DATABASE_URL`/`MEMORY_BACKEND`'den gelir; `.env`'siz makinede (CI) kapalıdır
    ve uç 503 döner. Önceden bu test yalnız geliştiricinin `.env`'i sayesinde geçiyordu.
    """
    from app import config
    from app.api import memory as memory_api
    from app.services import memory as memory_svc
    mocker.patch.object(memory_api, "MEMORY_ENABLED", True)
    mocker.patch.object(config, "MEMORY_BACKEND", "pgvector")
    mocker.patch.object(memory_svc, "_service", None)
    mocker.patch("app.services.memory.get_pool", return_value=None)
    r = await client.get("/api/memory")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)

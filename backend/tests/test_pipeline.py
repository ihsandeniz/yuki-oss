import io
import pytest


@pytest.mark.asyncio
async def test_voice_rejects_wrong_mime(client):
    """Yanlış MIME type → 415 Unsupported Media Type"""
    r = await client.post(
        "/api/voice",
        files={"file": ("test.txt", io.BytesIO(b"hello world"), "text/plain")},
    )
    assert r.status_code == 415


@pytest.mark.asyncio
async def test_voice_rejects_large_file(client):
    """26 MB ses dosyası → 413 Request Entity Too Large"""
    big = io.BytesIO(b"x" * (26 * 1024 * 1024))
    r = await client.post(
        "/api/voice",
        files={"file": ("big.wav", big, "audio/wav")},
    )
    assert r.status_code == 413


@pytest.mark.asyncio
async def test_voice_endpoint_exists(client):
    """/api/voice endpoint var (405/415/422 → endpoint mevcut, 404 değil)"""
    r = await client.post("/api/voice")
    assert r.status_code != 404

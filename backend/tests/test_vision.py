"""Faz 4 — Vision servis ve endpoint testleri."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.llm import ChatResponse, EmotionTag
from app.services.vision import capture_and_analyze, _capture_screenshot


# ------------------------------------------------------------------ #
# _capture_screenshot testleri
# ------------------------------------------------------------------ #


def test_capture_screenshot_returns_base64(mocker):
    """mss mock'lanmış — base64 string döndürmeli."""
    fake_rgba = b"\xff\x00\x00\xff" * (100 * 100)  # 100x100 kırmızı piksel (BGRA)

    mock_raw = MagicMock()
    mock_raw.size = (100, 100)
    mock_raw.bgra = fake_rgba

    mock_sct = MagicMock()
    mock_sct.__enter__ = MagicMock(return_value=mock_sct)
    mock_sct.__exit__ = MagicMock(return_value=False)
    mock_sct.monitors = [{"left": 0, "top": 0, "width": 100, "height": 100}]
    mock_sct.grab.return_value = mock_raw

    mocker.patch("mss.mss", return_value=mock_sct)

    result = _capture_screenshot()

    assert isinstance(result, str)
    assert len(result) > 0
    # Base64 karakter seti kontrolü
    import base64
    decoded = base64.b64decode(result)
    assert len(decoded) > 0


# ------------------------------------------------------------------ #
# capture_and_analyze testleri
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_capture_and_analyze_returns_chat_response(mocker):
    """Screenshot + Vision LLM mock'lanmış — ChatResponse döndürmeli."""
    mocker.patch(
        "app.services.vision._capture_screenshot",
        return_value="FAKE_BASE64_IMAGE",
    )

    mock_choice = MagicMock()
    mock_choice.message.content = (
        'Ekranda bir terminal penceresi var.\n'
        '[EMOTION:{"emotion":"neutral","intensity":0.5}]\n'
        '[BEHAVIOR:{"action":"idle"}]'
    )
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    mocker.patch("app.services.vision._get_client", return_value=mock_client)

    result = await capture_and_analyze("Ekranda ne var?")

    assert isinstance(result, ChatResponse)
    assert "terminal" in result.text.lower()
    assert result.emotion.emotion == "neutral"
    assert result.emotion.intensity == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_capture_and_analyze_emotion_happy(mocker):
    """Farklı duygu etiketini doğru parse etmeli."""
    mocker.patch("app.services.vision._capture_screenshot", return_value="IMG")

    mock_choice = MagicMock()
    mock_choice.message.content = (
        'Güzel bir masaüstü arka planı var.\n'
        '[EMOTION:{"emotion":"happy","intensity":0.8}]\n'
        '[BEHAVIOR:{"action":"nod"}]'
    )
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    mocker.patch("app.services.vision._get_client", return_value=mock_client)

    result = await capture_and_analyze("Ekranım güzel mi?")

    assert result.emotion.emotion == "happy"
    assert result.emotion.intensity == pytest.approx(0.8)


# ------------------------------------------------------------------ #
# /api/vision endpoint testleri
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_vision_endpoint_success(client, mocker):
    """POST /api/vision 200 dönmeli."""
    mocker.patch(
        "app.api.vision.capture_and_analyze",
        return_value=ChatResponse(
            text="Ekranda kod editörü açık.",
            emotion=EmotionTag(emotion="neutral", intensity=0.5),
        ),
    )

    response = await client.post(
        "/api/vision",
        json={"prompt": "Ne görüyorsun?"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert data["emotion"] == "neutral"
    assert data["intensity"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_vision_endpoint_default_prompt(client, mocker):
    """Prompt gönderilmeden endpoint çalışmalı (default değer kullanılır)."""
    mocker.patch(
        "app.api.vision.capture_and_analyze",
        return_value=ChatResponse(
            text="Masaüstü boş.",
            emotion=EmotionTag(emotion="neutral", intensity=0.4),
        ),
    )

    response = await client.post("/api/vision", json={})

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_vision_endpoint_prompt_too_long(client):
    """501 karakterlik prompt 422 dönmeli."""
    response = await client.post(
        "/api/vision",
        json={"prompt": "a" * 501},
    )
    assert response.status_code == 422

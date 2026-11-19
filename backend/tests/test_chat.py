import pytest


@pytest.mark.asyncio
async def test_chat_max_length_validation(client):
    """4001 karakter mesaj → 422 Unprocessable Entity"""
    r = await client.post("/api/chat", json={"message": "a" * 4001})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_chat_empty_message_validation(client):
    """Boş mesaj → 422"""
    r = await client.post("/api/chat", json={"message": ""})
    assert r.status_code == 422


def test_emotion_parsing():
    """_parse_tags: [EMOTION:...] etiketi doğru parse edilmeli"""
    from app.services.llm import _parse_tags
    clean, tag, _ = _parse_tags('Test yanıt. [EMOTION:{"emotion":"happy","intensity":0.8}]')
    assert tag.emotion == "happy"
    assert tag.intensity == 0.8
    assert "[EMOTION:" not in clean
    assert clean == "Test yanıt."


def test_emotion_parsing_missing_tag():
    """Etiket yoksa neutral döner"""
    from app.services.llm import _parse_tags
    clean, tag, _ = _parse_tags("Normal yanıt.")
    assert tag.emotion == "neutral"
    assert tag.intensity == 0.5
    assert clean == "Normal yanıt."


@pytest.mark.asyncio
async def test_chat_with_mock(client, mocker):
    """OpenRouter mock ile /api/chat testi"""
    mock_message = mocker.MagicMock()
    mock_message.content = 'Merhaba! [EMOTION:{"emotion":"happy","intensity":0.7}]'
    mock_choice = mocker.MagicMock()
    mock_choice.message = mock_message
    mock_resp = mocker.MagicMock()
    mock_resp.choices = [mock_choice]

    mock_client = mocker.MagicMock()
    mock_client.chat.completions.create = mocker.AsyncMock(return_value=mock_resp)
    mocker.patch("app.services.llm._get_client", return_value=mock_client)

    r = await client.post("/api/chat", json={"message": "Merhaba"})
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data
    assert "emotion" in data

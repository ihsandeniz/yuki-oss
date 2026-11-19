"""Hafif hafızada (semantik hafıza kapalı) Yuki'nin cevabı geçmişe yazılır — her model yolunda.

Kusur: yerel model (Ollama, USE_LOCAL_LLM) yolunda yalnız semantik hafıza dalı kaydediyordu;
hafif hafızada kullanıcının mesajı yazılıyor, Yuki'nin cevabı yazılmıyordu. Sayfa yenilenince
geçmişte yalnız kullanıcının mesajları kalıyor, model sonraki turda kendi cevaplarını görmüyordu.

Aynı ölçü bulut (OpenRouter) yolunda da koşar: orada cevap zaten yazılıyordu, bu test
bunun bozulmadığını da tutar.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import llm


def _chunk(content):
    ch = MagicMock()
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = None
    ch.choices = [MagicMock(delta=delta, finish_reason=None)]
    return ch


def _stream(parcalar):
    async def _aiter(_self=None):
        for p in parcalar:
            yield _chunk(p)
    s = MagicMock()
    s.__aiter__ = _aiter
    s.close = AsyncMock()
    return s


def _istemci(parcalar):
    client = MagicMock()
    client.base_url = "http://127.0.0.1:11434/v1"
    client.chat.completions.create = AsyncMock(side_effect=lambda *a, **k: _stream(parcalar))
    return client


@pytest.fixture
def gecmis(monkeypatch):
    """Diske yazmadan geçmişi yakalar: save_history'nin son çağrısı."""
    kayit: dict[str, list[dict]] = {}
    monkeypatch.setattr(llm, "_histories", {}, raising=False)
    monkeypatch.setattr("app.services.lite_memory.load_history", lambda key: [])
    monkeypatch.setattr("app.services.lite_memory.save_history",
                        lambda key, h: kayit.__setitem__(key, [dict(m) for m in h]))
    monkeypatch.setattr("app.services.lite_memory.note_user_message", lambda key: False)
    monkeypatch.setattr(llm, "MEMORY_ENABLED", False)
    return kayit


def _roller(kayit):
    assert kayit, "geçmiş hiç kaydedilmedi"
    (h,) = kayit.values()
    return [(m["role"], m["content"]) for m in h]


@pytest.mark.asyncio
async def test_yerel_model_cevabi_gecmise_yazilir(gecmis):
    client = _istemci(["Merhaba, ", "nasılsın?"])
    with patch("app.services.llm._get_client", return_value=client), \
         patch("app.services.llm.USE_LOCAL_LLM", True):
        metin = "".join([c async for c in llm.chat_stream("selam")])

    assert metin == "Merhaba, nasılsın?"
    assert _roller(gecmis) == [("user", "selam"), ("assistant", "Merhaba, nasılsın?")]


@pytest.mark.asyncio
async def test_yerel_model_iki_tur_sonra_model_kendi_cevabini_gorur(gecmis):
    """İkinci turda modele giden mesajlarda ilk turun cevabı bulunur."""
    client = _istemci(["Birinci cevap."])
    with patch("app.services.llm._get_client", return_value=client), \
         patch("app.services.llm.USE_LOCAL_LLM", True):
        _ = [c async for c in llm.chat_stream("bir")]
        _ = [c async for c in llm.chat_stream("iki")]

    giden = client.chat.completions.create.call_args_list[-1].kwargs["messages"]
    roller = [(m["role"], m["content"]) for m in giden if m["role"] != "system"]
    assert ("assistant", "Birinci cevap.") in roller
    assert roller[-1] == ("user", "iki")


@pytest.mark.asyncio
async def test_bulut_yolu_cevabi_gecmise_yazar(gecmis):
    """Bulut (OpenRouter, LLMRunner) yolu: cevap zaten yazılıyordu — bozulmasın."""
    client = _istemci(["Bulut ", "cevabı."])
    client.base_url = "https://openrouter.ai/api/v1"
    router = MagicMock()
    router.get_client = AsyncMock(return_value=(client, "test/model"))
    router.record_success = MagicMock()
    router.record_failure = MagicMock()
    with patch("app.services.llm_router.get_router", return_value=router), \
         patch("app.services.llm._get_client", return_value=client), \
         patch("app.services.llm.USE_LOCAL_LLM", False):
        metin = "".join([c async for c in llm.chat_stream("selam")])

    assert "Bulut" in metin
    assert _roller(gecmis) == [("user", "selam"), ("assistant", "Bulut cevabı.")]

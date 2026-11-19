"""Agentic döngü testleri — zincirleme ve paralel araç çağrısı.

⚠️ 2026-07-29'da yeniden yazıldı. Eski hâli **artık var olmayan bir mimariyi**
test ediyordu ve bu yüzden sessizce kırıktı:
  1. Araç çağrısı adımı non-streaming sanılıyordu; `runner.run()` her adımı
     `stream=True` ile açıp `delta.tool_calls` parçalarını biriktiriyor.
  2. Mock yalnız `app.services.llm._get_client`'a takılıyordu; runner client'ı
     **`llm_router.get_router().get_client()`** üzerinden alıyor → mock devreye
     girmiyor, gerçek API'ye çıkılıyordu (401 → "anahtar geçersiz" mesajı).
  3. `AsyncMock(name="list_directory")` Mock'un KENDİ adını verir, `.name`
     alanını DEĞİL → araç adı hiç doğru gelmiyordu.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm import chat_stream


def _chunk(content=None, tool_calls=None):
    """OpenAI streaming chunk'ı taklit et (runner'ın okuduğu alanlar kadar)."""
    ch = MagicMock()
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = tool_calls
    ch.choices = [MagicMock(delta=delta, finish_reason=None)]
    return ch


def _tool_delta(index, call_id, name, arguments):
    """delta.tool_calls[i] — runner index/id/function.name/arguments okur."""
    tc = MagicMock()
    tc.index = index
    tc.id = call_id
    fn = MagicMock()
    fn.name = name              # MagicMock(name=...) ÇALIŞMAZ, atama şart
    fn.arguments = arguments
    tc.function = fn
    return tc


def _stream(chunks):
    """`await create(...)` sonucu: async iterable + close()."""
    async def _aiter(_self=None):
        for c in chunks:
            yield c
    s = MagicMock()
    s.__aiter__ = _aiter
    s.close = AsyncMock()
    return s


def _fake_router(chunk_lists):
    """llm_router yerine sahte client: her çağrıda sıradaki chunk listesini akıtır.

    Liste tükenirse SONUNCUSUNU tekrar üretir — runner araç turundan sonra
    `_stream_final()` ile fazladan bir çağrı yapabiliyor; sabit uzunluklu
    side_effect orada `StopAsyncIteration`'a dönüşüyordu.
    """
    kalan = [list(c) for c in chunk_lists]

    def _create(*_a, **_kw):
        chunks = kalan.pop(0) if len(kalan) > 1 else kalan[0]
        return _stream(chunks)

    client = MagicMock()
    client.base_url = "https://openrouter.ai/api/v1"
    client.chat.completions.create = AsyncMock(side_effect=_create)
    router = MagicMock()
    router.get_client = AsyncMock(return_value=(client, "test/model"))
    router.record_success = MagicMock()
    router.record_failure = MagicMock()
    return router, client


@pytest.mark.asyncio
async def test_agentic_runner_sequential_mocked():
    """Tek araç çağrısı → sonuç → final yanıt zinciri."""
    router, client = _fake_router([
        [_chunk(tool_calls=[
            _tool_delta(0, "call_1", "list_directory", json.dumps({"path": "."}))
        ])],
        [_chunk(content="Dizini listeledim, "), _chunk(content="MASTER_PLAN.md burada.")],
    ])

    with patch("app.services.llm_router.get_router", return_value=router), \
         patch("app.services.llm._get_client", return_value=client), \
         patch("app.services.runner.call_tool",
               new=AsyncMock(return_value="MASTER_PLAN.md\nREADME.md")) as mock_call, \
         patch("app.services.llm.USE_LOCAL_LLM", False), \
         patch("app.services.llm.MEMORY_ENABLED", False):
        full_text = "".join([c async for c in chat_stream("Dosyaları listele.")])

    assert "MASTER_PLAN.md" in full_text
    assert client.chat.completions.create.call_count >= 2   # araç turu + final
    assert mock_call.call_count == 1
    assert mock_call.call_args.args[0] == "list_directory"


@pytest.mark.asyncio
async def test_agentic_runner_parallel_mocked():
    """Aynı adımda iki araç çağrısı birlikte çalıştırılır."""
    router, client = _fake_router([
        [_chunk(tool_calls=[
            _tool_delta(0, "call_1", "get_system_info", "{}"),
            _tool_delta(1, "call_2", "take_screenshot", "{}"),
        ])],
        [_chunk(content="Sistem bilgilerini aldım ve "), _chunk(content="ekran görüntüsü hazır.")],
    ])

    with patch("app.services.llm_router.get_router", return_value=router), \
         patch("app.services.llm._get_client", return_value=client), \
         patch("app.services.runner.call_tool",
               new=AsyncMock(side_effect=["OS: Linux...", "SCREENSHOT_DATA:abc"])) as mock_call, \
         patch("app.services.llm.USE_LOCAL_LLM", False), \
         patch("app.services.llm.MEMORY_ENABLED", False):
        full_text = "".join([c async for c in chat_stream("Bilgi topla.")])

    assert "ekran" in full_text.lower()
    assert client.chat.completions.create.call_count >= 2
    assert mock_call.call_count == 2
    assert {c.args[0] for c in mock_call.call_args_list} == {"get_system_info", "take_screenshot"}


@pytest.mark.asyncio
async def test_araci_olmayan_yanit_dogrudan_akar():
    """Araç çağrısı yoksa tek adımda token'lar doğrudan yayılır (TTFT)."""
    router, client = _fake_router([
        [_chunk(content="Merhaba "), _chunk(content="İpek.")],
    ])

    with patch("app.services.llm_router.get_router", return_value=router), \
         patch("app.services.llm._get_client", return_value=client), \
         patch("app.services.llm.USE_LOCAL_LLM", False), \
         patch("app.services.llm.MEMORY_ENABLED", False):
        full_text = "".join([c async for c in chat_stream("selam")])

    assert "Merhaba" in full_text and "İpek" in full_text
    assert client.chat.completions.create.call_count == 1

"""TTS fallback zinciri testleri: Fish → ElevenLabs → Edge TTS → Google TTS.

Açık kaynak sürümde yerel ses motoru yok (karar: 2026-10-17 yuki-urun-acik-kaynak
§ Ek karar); zincir Edge ve bulut/uzak katmanlardan oluşur.
"""

import pytest
from unittest.mock import AsyncMock, patch


def _kapat(monkeypatch, fish=False, el=False):
    from app.services import tts
    monkeypatch.setattr(tts, "USE_FISH_TTS", fish)
    monkeypatch.setattr(tts, "USE_ELEVENLABS_TTS", el)
    monkeypatch.setattr(tts, "ELEVENLABS_API_KEY", "sk-test" if el else "")
    monkeypatch.setattr(tts, "_elevenlabs_kapali_sebep", None)


def test_yerel_motor_izi_yok():
    from app.services import tts
    for ad in ("USE_LOCAL_TTS", "_synthesize_" + "xt" + "ts", "_stream_" + "xt" + "ts"):
        assert not hasattr(tts, ad), ad


# ── synthesize() ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_synthesize_katman_yoksa_dogrudan_edge(monkeypatch):
    _kapat(monkeypatch)
    with patch("app.services.tts._synthesize_edge", new_callable=AsyncMock, return_value=b"edge") as e:
        from app.services.tts import synthesize
        assert await synthesize("merhaba") == b"edge"
    e.assert_called_once_with("merhaba")


@pytest.mark.asyncio
async def test_synthesize_fish_sonra_elevenlabs_sonra_edge(monkeypatch):
    _kapat(monkeypatch, fish=True, el=True)
    with patch("app.services.tts._synthesize_fish", new_callable=AsyncMock, side_effect=Exception("fish")) as f, \
         patch("app.services.tts._synthesize_elevenlabs", new_callable=AsyncMock, side_effect=Exception("el")) as el, \
         patch("app.services.tts._synthesize_edge", new_callable=AsyncMock, return_value=b"edge") as e:
        from app.services.tts import synthesize
        assert await synthesize("merhaba") == b"edge"
    f.assert_called_once(); el.assert_called_once(); e.assert_called_once()


@pytest.mark.asyncio
async def test_synthesize_elevenlabs_basariliysa_edge_cagrilmaz(monkeypatch):
    _kapat(monkeypatch, el=True)
    with patch("app.services.tts._synthesize_elevenlabs", new_callable=AsyncMock, return_value=b"el"), \
         patch("app.services.tts._synthesize_edge", new_callable=AsyncMock) as e:
        from app.services.tts import synthesize
        assert await synthesize("merhaba") == b"el"
    e.assert_not_called()


# ── synthesize_streaming() ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_streaming_katman_yoksa_edge(monkeypatch):
    _kapat(monkeypatch)

    async def _edge(*a, **k):
        yield b"e1"
        yield b"e2"

    with patch("app.services.tts._stream_edge", _edge):
        from app.services.tts import synthesize_streaming
        assert [c async for c in synthesize_streaming("merhaba")] == [b"e1", b"e2"]


@pytest.mark.asyncio
async def test_streaming_elevenlabs_hatasinda_edge(monkeypatch):
    _kapat(monkeypatch, el=True)

    async def _el(*a, **k):
        raise Exception("el")
        yield  # pragma: no cover

    async def _edge(*a, **k):
        yield b"edge"

    with patch("app.services.tts._stream_elevenlabs", _el), patch("app.services.tts._stream_edge", _edge):
        from app.services.tts import synthesize_streaming
        assert [c async for c in synthesize_streaming("merhaba")] == [b"edge"]


# ── Edge 403 (2026-10-10, edge-tts #490) → Google çeviri TTS son çare ──
# Anahtarsız müşterinin tek katmanı Edge; 403'te Yuki tamamen susuyordu.
class _Edge403:
    def __init__(self, *a, **k):
        pass

    async def stream(self):
        raise RuntimeError("403, message='Invalid response status'")
        yield  # pragma: no cover


class _EdgeBos:
    def __init__(self, *a, **k):
        pass

    async def stream(self):
        yield {"type": "WordBoundary"}


@pytest.mark.asyncio
async def test_duz_edge_403te_googlea_duser(monkeypatch):
    monkeypatch.setattr("app.services.tts.edge_tts.Communicate", _Edge403)
    with patch("app.services.tts._synthesize_google", new_callable=AsyncMock, return_value=b"g") as mg:
        from app.services.tts import synthesize, synthesize_streaming
        assert await synthesize("merhaba") == b"g"
        assert [c async for c in synthesize_streaming("merhaba")] == [b"g"]
    assert mg.call_count == 2


@pytest.mark.asyncio
async def test_edge_bos_ses_donerse_googlea_duser(monkeypatch):
    monkeypatch.setattr("app.services.tts.edge_tts.Communicate", _EdgeBos)
    with patch("app.services.tts._synthesize_google", new_callable=AsyncMock, return_value=b"g") as mg:
        from app.services.tts import _synthesize_edge, _stream_edge
        assert await _synthesize_edge("merhaba") == b"g"
        assert [c async for c in _stream_edge("merhaba")] == [b"g"]
    assert mg.call_count == 2


@pytest.mark.asyncio
async def test_edge_akis_ortasinda_koparsa_googlea_dusmez(monkeypatch):
    """Kısmi ses gittiyse ikinci ses eklenmez (çift ses olmasın)."""
    class _EdgeKopuk:
        def __init__(self, *a, **k):
            pass

        async def stream(self):
            yield {"type": "audio", "data": b"yarim"}
            raise RuntimeError("koptu")

    monkeypatch.setattr("app.services.tts.edge_tts.Communicate", _EdgeKopuk)
    with patch("app.services.tts._synthesize_google", new_callable=AsyncMock) as mg:
        from app.services.tts import _stream_edge
        assert [c async for c in _stream_edge("merhaba")] == [b"yarim"]
    mg.assert_not_called()


@pytest.mark.asyncio
async def test_google_dili_secili_sesten_alir_ve_parcalar(monkeypatch):
    istekler = []

    class _Yanit:
        status_code, content = 200, b"mp3"

    class _Istemci:
        async def get(self, url, params=None, **k):
            istekler.append(params)
            return _Yanit()

    monkeypatch.setattr("app.services.tts._get_shared_client", lambda: _Istemci())
    from app.services.tts import _synthesize_google
    out = await _synthesize_google(("kelime " * 60).strip(), "en-US-AvaNeural")
    assert out == b"mp3" * len(istekler) and len(istekler) == 3
    assert {p["tl"] for p in istekler} == {"en"}


@pytest.mark.asyncio
async def test_google_hata_kodu_istisna_firlatir(monkeypatch):
    class _Yanit:
        status_code, content = 429, b""

    class _Istemci:
        async def get(self, *a, **k):
            return _Yanit()

    monkeypatch.setattr("app.services.tts._get_shared_client", lambda: _Istemci())
    from app.services.tts import _synthesize_google
    with pytest.raises(RuntimeError, match="429"):
        await _synthesize_google("merhaba", "tr-TR-EmelNeural")


def test_google_parcalama_sinir_ve_kelime():
    from app.services.tts import _google_parcala, _GOOGLE_PARCA
    metin = ("kelime " * 100).strip()
    p = _google_parcala(metin)
    assert all(len(x) <= _GOOGLE_PARCA for x in p) and " ".join(p) == metin
    assert _google_parcala("a" * 400) == ["a" * 180, "a" * 180, "a" * 40]
    assert _google_parcala("") == []


@pytest.mark.asyncio
async def test_ws_tts_hatasi_baglantiyi_dusurmez(monkeypatch):
    """Ses üretilemezse _send_tts_streaming istisna yaymaz (eskiden WS'i ilk cümlede kapatıyordu)."""
    async def _patlayan(text):
        raise ValueError("403")
        yield  # pragma: no cover

    monkeypatch.setattr("app.api.websocket.synthesize_streaming", _patlayan)
    ws = AsyncMock()
    from app.api.websocket import _send_tts_streaming
    await _send_tts_streaming(ws, "merhaba")
    ws.send_json.assert_not_called()


def test_tts_durumu_google_yedegini_gosterir():
    from app.mesajlar import tr, en
    assert "ses.google-notu" in tr.METINLER and "ses.google-notu" in en.METINLER

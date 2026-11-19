"""Dolgu sesi — cevap gecikince bir kez kısa "hmm" (varsayılan KAPALI; `config.DOLGU_SESI` — `.env` `DOLGU_SESI=1` ya da HQ › Ses anahtarı).

Kurallar (`services/dolgu_sesi.py`):
- dolgu cevabı BEKLETMEZ: ses hazır değilse o tur hiç gönderilmez, sentez arka planda yapılır
- ilk gerçek ses (`audio`/`audio_chunk`, `dolgu` işaretsiz) gecikmeden önce giderse dolgu yok
- tur başına en çok bir dolgu; tur bitince zamanlayıcı ölür, `ws.send_json` geri yerine konur
- sentez hatası turu bozmaz
- ses hattında TEK tur çağrı noktası (`dolgu_sesi.tur`) + bağlantı açılışında tek ısınma (`dolgu_sesi.isit`)
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app import config as _config
from app.services import dolgu_sesi as D


class SahteWS:
    def __init__(self):
        self.giden: list[dict] = []

    async def send_json(self, m):
        self.giden.append(m)


@pytest.fixture(autouse=True)
def temiz(monkeypatch):
    D._onbellek.clear()
    D._isitma = None
    monkeypatch.setenv("DOLGU_GECIKME_MS", "300")
    monkeypatch.delenv("DOLGU_METNI", raising=False)
    yield
    D._onbellek.clear()
    D._isitma = None


def _sentez(sayac, hata=False):
    async def _s(metin):
        sayac.append(metin)
        if hata:
            raise RuntimeError("tts yok")
        yield b"HM"
        yield b"MM"
    return _s


def _dolgular(ws):
    return [m for m in ws.giden if m.get("dolgu")]


async def test_kapaliyken_hicbir_sey_olmaz(monkeypatch):
    monkeypatch.setattr(_config, "DOLGU_SESI", False)
    sayac = []
    ws = SahteWS()
    async with D.tur(ws, sentezle=_sentez(sayac)):
        await asyncio.sleep(0.45)
    assert ws.giden == [] and sayac == []


async def test_cevap_gecikirse_bir_kez_dolgu(monkeypatch):
    monkeypatch.setattr(_config, "DOLGU_SESI", True)
    D._onbellek["Hmm."] = b"HMMM"
    ws = SahteWS()
    async with D.tur(ws, sentezle=_sentez([])):
        await asyncio.sleep(0.8)
        await ws.send_json({"type": "audio", "data": "x", "text": "Cevap."})
    d = _dolgular(ws)
    assert len(d) == 1, ws.giden
    assert d[0]["type"] == "audio" and d[0]["text"] == ""
    import base64
    assert base64.b64decode(d[0]["data"]) == b"HMMM"
    assert ws.giden[0] is d[0], "dolgu gerçek sesten önce gitmeli"


async def test_ses_zamaninda_gelirse_dolgu_yok(monkeypatch):
    monkeypatch.setattr(_config, "DOLGU_SESI", True)
    D._onbellek["Hmm."] = b"HMMM"
    ws = SahteWS()
    async with D.tur(ws, sentezle=_sentez([])):
        await ws.send_json({"type": "audio_chunk", "data": "x"})
        await asyncio.sleep(0.5)
    assert _dolgular(ws) == []


async def test_metin_akisi_dolguyu_durdurmaz(monkeypatch):
    """Yalnız SES dolguyu iptal eder; `text` parçası gelmesi kullanıcının bir şey duyduğu demek değil."""
    monkeypatch.setattr(_config, "DOLGU_SESI", True)
    D._onbellek["Hmm."] = b"HMMM"
    ws = SahteWS()
    async with D.tur(ws, sentezle=_sentez([])):
        await ws.send_json({"type": "text", "chunk": "Ce"})
        await asyncio.sleep(0.5)
    assert len(_dolgular(ws)) == 1


async def test_onbellek_bossa_bu_tur_dolgu_yok_arka_planda_isinir(monkeypatch):
    monkeypatch.setattr(_config, "DOLGU_SESI", True)
    sayac = []
    ws = SahteWS()
    async with D.tur(ws, sentezle=_sentez(sayac)):
        await asyncio.sleep(0.5)
    assert _dolgular(ws) == [], "sentez tur içinde beklenmemeli"
    await asyncio.sleep(0.05)
    assert sayac == ["Hmm."] and D._onbellek["Hmm."] == b"HMMM"
    ws2 = SahteWS()
    async with D.tur(ws2, sentezle=_sentez(sayac)):
        await asyncio.sleep(0.5)
    assert len(_dolgular(ws2)) == 1
    assert sayac == ["Hmm."], "ısınmış önbellek ikinci kez sentezlenmez"


async def test_isitma_ust_uste_tek_gorev(monkeypatch):
    monkeypatch.setattr(_config, "DOLGU_SESI", True)
    sayac = []

    async def _yavas(metin):
        sayac.append(metin)
        await asyncio.sleep(0.2)
        yield b"X"
    for _ in range(3):
        async with D.tur(SahteWS(), sentezle=_yavas):
            pass
    await asyncio.sleep(0.3)
    assert sayac == ["Hmm."]


async def test_sentez_hatasi_turu_bozmaz(monkeypatch):
    monkeypatch.setattr(_config, "DOLGU_SESI", True)
    ws = SahteWS()
    async with D.tur(ws, sentezle=_sentez([], hata=True)):
        await asyncio.sleep(0.4)
    await asyncio.sleep(0.05)
    assert _dolgular(ws) == [] and "Hmm." not in D._onbellek
    assert D._isitma.done() and D._isitma.exception() is None, "hata arka plan görevinden sızmamalı"


async def test_tur_bitince_zamanlayici_olur_send_geri_gelir(monkeypatch):
    monkeypatch.setattr(_config, "DOLGU_SESI", True)
    D._onbellek["Hmm."] = b"HMMM"
    ws = SahteWS()
    asil = ws.send_json
    async with D.tur(ws, sentezle=_sentez([])):
        assert ws.send_json != asil
    assert ws.send_json == asil
    await asyncio.sleep(0.5)
    assert _dolgular(ws) == []


async def test_istisnada_da_send_geri_gelir(monkeypatch):
    monkeypatch.setattr(_config, "DOLGU_SESI", True)
    D._onbellek["Hmm."] = b"HMMM"
    ws = SahteWS()
    asil = ws.send_json
    with pytest.raises(ZeroDivisionError):
        async with D.tur(ws, sentezle=_sentez([])):
            1 / 0
    assert ws.send_json == asil


def test_gecikme_sinirlari(monkeypatch):
    monkeypatch.setenv("DOLGU_GECIKME_MS", "10")
    assert D.gecikme_sn() == 0.3
    monkeypatch.setenv("DOLGU_GECIKME_MS", "99999")
    assert D.gecikme_sn() == 5.0
    monkeypatch.setenv("DOLGU_GECIKME_MS", "abc")
    assert D.gecikme_sn() == 1.2
    monkeypatch.setenv("DOLGU_METNI", "  ")
    assert D.metin() == "Hmm."


# ── ses hattına bağlantı ───────────────────────────────────────────────────

WS_PY = Path(__file__).resolve().parents[1] / "app" / "api" / "websocket.py"


def test_ses_hattinda_tek_cagri_noktasi():
    kaynak = WS_PY.read_text(encoding="utf-8")
    assert kaynak.count("dolgu_sesi.tur(") == 1, "dolgu ses hattına tek noktadan bağlanmalı"
    assert kaynak.count("dolgu_sesi.isit(") == 1, "ısınma bağlantı açılışında bir kez"
    assert kaynak.count("dolgu_sesi.") == 2
    acilis = kaynak.index("await ws.accept()")
    assert acilis < kaynak.index("dolgu_sesi.isit(") < kaynak.index("while True"), "ısınma accept'ten hemen sonra"


@pytest.fixture
def istemci(monkeypatch):
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    import app.config as config
    from app.api import websocket as W
    from app.services import ag_ayari
    monkeypatch.setattr(config, "AUTH_TOKEN", "")
    monkeypatch.setattr(ag_ayari, "ws_izinli", lambda *a, **k: True)

    async def _chat_stream(metin, cancel_token=None):
        await asyncio.sleep(0.7)       # model geç cevap veriyor
        yield "Tamam."

    async def _tts(ws, metin, *a, **k):
        await ws.send_json({"type": "audio", "data": "", "text": metin})
    monkeypatch.setattr(W, "chat_stream", _chat_stream)
    monkeypatch.setattr(W, "_send_tts_streaming", _tts)
    app = FastAPI()
    app.include_router(W.router)
    with TestClient(app) as c:
        yield c


def _sira(ws, tavan=40):
    tipler = []
    for _ in range(tavan):
        m = ws.receive_json()
        tipler.append(("dolgu" if m.get("dolgu") else m.get("type")))
        if m.get("type") == "done":
            return tipler
    raise AssertionError(tipler)


def test_gercek_hatta_dolgu_cevaptan_once(istemci, monkeypatch):
    monkeypatch.setattr(_config, "DOLGU_SESI", True)
    D._onbellek["Hmm."] = b"HMMM"
    with istemci.websocket_connect("/ws/realtime") as ws:
        ws.send_text(json.dumps({"type": "text", "message": "merhaba"}))
        tipler = _sira(ws)
    assert "dolgu" in tipler and tipler.index("dolgu") < tipler.index("audio"), tipler
    assert tipler.count("dolgu") == 1


def test_gercek_hatta_kapaliyken_dolgu_yok(istemci, monkeypatch):
    monkeypatch.setattr(_config, "DOLGU_SESI", False)
    D._onbellek["Hmm."] = b"HMMM"
    with istemci.websocket_connect("/ws/realtime") as ws:
        ws.send_text(json.dumps({"type": "text", "message": "merhaba"}))
        tipler = _sira(ws)
    assert "dolgu" not in tipler

"""Sesli sözden sonraki 1,5 sn düzenleme penceresi başka mesajı YUTMAZ.

Pencere eskiden tek bir `ws.receive()` bekliyordu ve gelen her şeyi "düzenleme" sanıyordu:
- pencereye düşen ikinci söz (ses karesi) hiç işlenmiyordu — üst üste söz kayboluyordu,
- pencerede basılan DURDUR (`cancel`) yutuluyor, tur yine başlıyordu,
- `ping` cevapsız kalıyordu.
Kişisel Yuki'deki düzeltmenin (pencere yalnız kendi onayını alır, gerisi sıraya) yuki-oss'un
satır içi tur yapısına göre yeniden yazımı. Gerçek STT/LLM yok: sahte.
"""
import json

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api import websocket as W


@pytest.fixture
def istemci(monkeypatch):
    import app.config as config
    from app.services import ag_ayari
    monkeypatch.setattr(config, "AUTH_TOKEN", "")
    monkeypatch.setattr(ag_ayari, "ws_izinli", lambda *a, **k: True)
    sozler = {b"SES1": "birinci soru", b"SES2": "ikinci soru"}
    monkeypatch.setattr(W, "ensure_wav", lambda b: b)
    monkeypatch.setattr(W, "detect_speech", lambda b: True)
    monkeypatch.setattr(W, "check_wake_word", lambda t: True)
    monkeypatch.setattr(W, "analyze_voice_emotion", lambda b: {"emotion": "neutral", "energy": 0})

    async def _transcribe(b):
        return sozler[b]
    monkeypatch.setattr(W, "transcribe", _transcribe)
    turlar = []

    async def _chat_stream(metin, cancel_token=None):
        turlar.append(metin)
        yield "Tamam."
    monkeypatch.setattr(W, "chat_stream", _chat_stream)

    async def _tts(ws, metin, *a, **k):
        await ws.send_json({"type": "audio", "text": metin})
    monkeypatch.setattr(W, "_send_tts_streaming", _tts)
    app = FastAPI()
    app.include_router(W.router)
    with TestClient(app) as c:
        c.turlar = turlar
        yield c


def _al(ws, sure=5.0):
    """Süreli alma: kırmızıda (mesaj yutulunca) test asılı kalmasın, düşsün."""
    import anyio

    async def _r():
        with anyio.fail_after(sure):
            return await ws._send_rx.receive()
    m = ws.portal.call(_r)
    return json.loads(m["text"]) if m.get("text") else {}


def _bekle(ws, tip, tavan=60):
    for _ in range(tavan):
        m = _al(ws)
        if m.get("type") == tip:
            return m
    raise AssertionError(f"{tip} gelmedi")


def test_pencereye_dusen_ikinci_soz_kaybolmaz(istemci):
    with istemci.websocket_connect("/ws/realtime") as ws:
        ws.send_bytes(b"SES1")
        _bekle(ws, "transcription")
        ws.send_bytes(b"SES2")                     # pencere açıkken ikinci söz
        _bekle(ws, "audio")
        _bekle(ws, "transcription")
        ws.send_text(json.dumps({"type": "confirm_transcription", "text": ""}))
        _bekle(ws, "audio")
    assert istemci.turlar == ["birinci soru", "ikinci soru"]


def test_pencerede_durdur_turu_baslatmaz(istemci):
    with istemci.websocket_connect("/ws/realtime") as ws:
        ws.send_bytes(b"SES1")
        _bekle(ws, "transcription")
        ws.send_text(json.dumps({"type": "cancel"}))
        _bekle(ws, "cancelled")
    assert istemci.turlar == []


def test_pencerede_ping_cevapsiz_kalmaz_ve_tur_surer(istemci):
    with istemci.websocket_connect("/ws/realtime") as ws:
        ws.send_bytes(b"SES1")
        _bekle(ws, "transcription")
        ws.send_text(json.dumps({"type": "ping"}))
        ws.send_text(json.dumps({"type": "confirm_transcription", "text": "düzeltilmiş soru"}))
        _bekle(ws, "pong")
        _bekle(ws, "audio")
    assert istemci.turlar == ["düzeltilmiş soru"]


def test_duzeltme_uygulanir(istemci):
    with istemci.websocket_connect("/ws/realtime") as ws:
        ws.send_bytes(b"SES1")
        _bekle(ws, "transcription")
        ws.send_text(json.dumps({"type": "confirm_transcription", "text": "düzeltilmiş"}))
        _bekle(ws, "audio")
    assert istemci.turlar == ["düzeltilmiş"]


def test_pencereye_dusen_yazili_mesaj_kaybolmaz(istemci):
    with istemci.websocket_connect("/ws/realtime") as ws:
        ws.send_bytes(b"SES1")
        _bekle(ws, "transcription")
        ws.send_text(json.dumps({"type": "text", "message": "yazılı soru"}))
        _bekle(ws, "audio")
        _bekle(ws, "audio")
    assert istemci.turlar == ["birinci soru", "yazılı soru"]

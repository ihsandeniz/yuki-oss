"""Gemini canlı ses (`native_audio.py`) — kurulu google-genai SDK'sının GERÇEK `AsyncSession`'ı ile.

Neden var: eski kod SDK 2.x'te üç yerden kırıktı ve hiçbir test bu yolu koşmadığı için CI yeşil kaldı:
  · `types.RealtimeInput(media_chunks=…)`  → AttributeError (sınıf SDK'da yok)
  · `async for response in self._session`  → TypeError (AsyncSession async-iterable değil)
  · `getattr(response, "turn_complete")`   → hep False (alan `server_content` altında), tur hiç bitmiyordu
Ayrıca model adı `gemini-2.0-flash-live-001` 2025-12-09'da kapandı (yerine `gemini-3.8-live`).

Ağ yok, anahtar yok: SDK'nın websocket bağlantısı (`google.genai.live.ws_connect`) sahte bir sunucuyla
değiştirilir. SDK'nın kendi kurulum mesajı, gönderme ve okuma kodu olduğu gibi çalışır; ölçülen şey
SDK'ya giden ve SDK'dan gelen gerçek JSON'dur.
"""
from __future__ import annotations

import base64
import io
import json
import re
import wave
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import pytest

genai_live = pytest.importorskip("google.genai.live")

from app.services import native_audio  # noqa: E402
from app.services.native_audio import GeminiLiveSession, _wav_to_pcm16_16k  # noqa: E402

KOK = Path(__file__).resolve().parents[2]


# ── sahte Gemini Live sunucusu ─────────────────────────────────────────────

def _deve(o):
    """Anahtarları camelCase'e çevirir: SDK bazı alt nesneleri snake_case yollar (`realtime_input`,
    `voice_config`); sunucu iki yazımı da kabul eder. Test yazım biçimini değil içeriği ölçer."""
    if isinstance(o, dict):
        return {re.sub(r"_(\w)", lambda m: m.group(1).upper(), k): _deve(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_deve(x) for x in o]
    return o


def _b64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class SahteWS:
    """websockets bağlantısı taklidi: SDK'nın yolladığını kaydeder, sıradaki sunucu mesajını verir."""

    def __init__(self, sunucu_mesajlari):
        self.giden: list[dict] = []
        self._kuyruk = [json.dumps(m).encode() for m in sunucu_mesajlari]

    async def send(self, veri):
        self.giden.append(_deve(json.loads(veri)))

    async def recv(self, decode=None):
        if not self._kuyruk:
            raise AssertionError("sahte sunucu boşaldı — istemci turun bittiğini anlamadı")
        return self._kuyruk.pop(0)

    async def close(self):
        pass


@pytest.fixture
def sunucu(monkeypatch):
    """`ws_connect`'i sahtesiyle değiştirir; mesaj listesini sonradan doldurmak için nesneyi döner."""
    durum = {"ws": None, "uri": None, "mesajlar": []}

    @asynccontextmanager
    async def sahte_baglan(uri, *a, **k):
        durum["uri"] = uri
        durum["baglanti"] = repr(k)
        durum["ws"] = SahteWS([{"setupComplete": {}}] + durum["mesajlar"])
        yield durum["ws"]

    monkeypatch.setattr(genai_live, "ws_connect", sahte_baglan)
    return durum


def _ses_olayi(*parcalar: bytes) -> dict:
    return {"serverContent": {"modelTurn": {"parts": [
        {"inlineData": {"mimeType": "audio/pcm;rate=24000", "data": base64.b64encode(p).decode()}}
        for p in parcalar
    ]}}}


DOKUM = {"serverContent": {"outputTranscription": {"text": "Merhaba!"}}}
BITTI = {"serverContent": {"turnComplete": True}}


def _wav(sr=48000, kanal=2, sure=0.1) -> bytes:
    n = int(sr * sure)
    t = np.arange(n) / sr
    tek = (0.5 * np.sin(2 * np.pi * 440 * t) * 32767).astype("<i2")
    veri = np.repeat(tek[:, None], kanal, axis=1).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(kanal)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(veri)
    return buf.getvalue()


def _oturum(model="gemini-3.8-live", voice="Aoede"):
    return GeminiLiveSession(api_key="test-anahtari", model=model, system_prompt="Sen Yuki'sin.", voice=voice)


# ── kurulum mesajı ─────────────────────────────────────────────────────────

async def test_kurulum_mesaji_model_ses_ve_dokum(sunucu):
    async with _oturum(voice="Kore"):
        pass
    kurulum = sunucu["ws"].giden[0]["setup"]
    assert kurulum["model"] == "models/gemini-3.8-live"
    gen = kurulum["generationConfig"]
    assert gen["responseModalities"] == ["AUDIO"]
    assert gen["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Kore"
    assert "outputAudioTranscription" in kurulum, "3.x yalnız ses döndürür; döküm ayarı yoksa yazı hiç gelmez"
    assert kurulum["systemInstruction"]["parts"][0]["text"] == "Sen Yuki'sin."
    assert "BidiGenerateContent" in sunucu["uri"]
    assert "test-anahtari" in sunucu["baglanti"], "anahtar bağlantı başlığına gitmeli"


# ── ses gönderme ───────────────────────────────────────────────────────────

async def test_ses_gonderme_blob_ve_akis_sonu(sunucu):
    async with _oturum() as s:
        await s.send_audio(_wav(sr=48000, kanal=2, sure=0.1))
    giden = sunucu["ws"].giden[1:]
    assert len(giden) == 2, giden
    ses = giden[0]["realtimeInput"]["audio"]
    assert ses["mimeType"] == "audio/pcm;rate=16000"
    pcm = _b64(ses["data"])
    assert len(pcm) == 1600 * 2, "48 kHz stereo 0,1 sn → 16 kHz mono 1600 örnek PCM16"
    assert np.abs(np.frombuffer(pcm, "<i2")).max() > 10000, "ses sıfırlanmamış olmalı"
    assert giden[1] == {"realtimeInput": {"audioStreamEnd": True}}


def test_wav_olmayan_kayit_ensure_wav_ile_cevrilir(monkeypatch):
    """İstemci MediaRecorder çıktısını (webm/opus) yollar; WAV'a çevirmeden okunamaz."""
    from app.services import stt
    gelen = []

    def sahte_ensure_wav(b):
        gelen.append(b)
        return _wav(sr=16000, kanal=1, sure=0.05)

    monkeypatch.setattr(stt, "ensure_wav", sahte_ensure_wav)
    pcm = _wav_to_pcm16_16k(b"\x1aE\xdf\xa3webm-taklidi")
    assert gelen == [b"\x1aE\xdf\xa3webm-taklidi"]
    assert len(pcm) == 800 * 2


def test_cevrilemeyen_kayit_acik_hata(monkeypatch):
    from app.services import stt
    monkeypatch.setattr(stt, "ensure_wav", lambda b: b)
    with pytest.raises(ValueError):
        _wav_to_pcm16_16k(b"OggS-cevrilemedi")


# ── yanıt okuma ────────────────────────────────────────────────────────────

async def test_yanit_cok_parcali_ses_dokum_ve_tur_sonu(sunucu):
    sunucu["mesajlar"] = [_ses_olayi(b"\x01\x02", b"\x03\x04"), DOKUM, _ses_olayi(b"\x05\x06"), BITTI,
                          _ses_olayi(b"\x07\x08"), BITTI]
    async with _oturum() as s:
        await s.send_text("selam")
        birinci = [c async for c in s.receive()]
        ikinci = [c async for c in s.receive()]

    assert [c.audio for c in birinci if c.audio] == [b"\x01\x02\x03\x04", b"\x05\x06"]
    assert [c.text for c in birinci if c.text] == ["Merhaba!"]
    assert birinci[-1].turn_complete and sum(c.turn_complete for c in birinci) == 1
    # Tur sonunda durdu: ikinci turun mesajları ilk receive()'de tüketilmedi.
    assert [c.audio for c in ikinci if c.audio] == [b"\x07\x08"] and ikinci[-1].turn_complete
    assert sunucu["ws"].giden[1] == {"clientContent": {
        "turns": [{"role": "user", "parts": [{"text": "selam"}]}], "turnComplete": True}}


async def test_baslatilmamis_oturum():
    s = _oturum()
    with pytest.raises(RuntimeError):
        await s.send_audio(b"")
    with pytest.raises(RuntimeError):
        [c async for c in s.receive()]


# ── /ws/native ucu baştan sona (sahte Gemini sunucusuyla) ──────────────────

def test_ws_native_ucu_ses_gonder_yanit_al(sunucu, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app import config as cfg
    from app.api import websocket_native as wn
    from app.services import ag_ayari

    monkeypatch.setattr(cfg, "AUTH_TOKEN", "")
    monkeypatch.setattr(ag_ayari, "ws_izinli", lambda ws: True)
    monkeypatch.setattr(wn, "GEMINI_NATIVE_AUDIO", True)
    monkeypatch.setattr(wn, "GEMINI_API_KEY", "test-anahtari")
    monkeypatch.setattr(wn, "build_system_prompt", lambda: "sistem")
    monkeypatch.setattr(wn, "GEMINI_LIVE_VOICE", "Puck")
    sunucu["mesajlar"] = [_ses_olayi(b"\x10\x20"), DOKUM, BITTI]

    uyg = FastAPI()
    uyg.include_router(wn.router)
    with TestClient(uyg).websocket_connect("/ws/native") as ws:
        ws.send_bytes(_wav(sr=16000, kanal=1, sure=0.05))
        alinan = [ws.receive_json() for _ in range(3)]

    assert alinan[0] == {"type": "audio_chunk", "data": base64.b64encode(b"\x10\x20").decode(),
                         "mime": "audio/pcm;rate=24000"}
    assert alinan[1] == {"type": "text", "chunk": "Merhaba!"}
    assert alinan[2] == {"type": "done"}
    kurulum = sunucu["ws"].giden[0]["setup"]
    assert kurulum["model"] == f"models/{wn.GEMINI_LIVE_MODEL}"
    assert kurulum["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Puck"


# ── model adı ──────────────────────────────────────────────────────────────

def test_varsayilan_model_ve_ses():
    kaynak = (KOK / "backend/app/config.py").read_text(encoding="utf-8")
    assert re.search(r'GEMINI_LIVE_MODEL: str = os\.getenv\("GEMINI_LIVE_MODEL", ""\)\.strip\(\) or "gemini-3\.8-live"', kaynak)
    assert re.search(r'GEMINI_LIVE_VOICE: str = os\.getenv\("GEMINI_LIVE_VOICE", ""\)\.strip\(\) or "Aoede"', kaynak)


def test_kapanan_live_modeli_geri_gelmesin():
    olu = re.compile(r"gemini-(?:2\.0-flash-live|live-2\.5-flash-preview)")
    yerler = [KOK / ".env.example", KOK / "frontend/js/core.js",
              *sorted((KOK / "backend/app").rglob("*.py"))]
    bulunan = [str(p.relative_to(KOK)) for p in yerler
               if olu.search(re.sub(r"#[^\n]*", "", p.read_text(encoding="utf-8")))]
    assert not bulunan, bulunan

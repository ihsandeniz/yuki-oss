"""TTS API — Ses sentezi durum, test ve referans ses yükleme.

GET  /api/tts/status    → aktif TTS zinciri + sağlayıcı durumu
POST /api/tts/test      → kısa test sesi üret (base64 WAV)
POST /api/tts/reference → Fish TTS için referans ses dosyası yükle
"""

from __future__ import annotations

import base64
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.config import (
    ELEVENLABS_API_KEY,
    FISH_REFERENCE_AUDIO,
    FISH_TTS_URL,
    USE_ELEVENLABS_TTS,
    USE_FISH_TTS,
)
from app.limiter import limiter
from app.mesajlar import M
from app.services.tts import synthesize

router = APIRouter(prefix="/api/tts", tags=["tts"])

# Referans ses dosyaları için kalıcı dizin
from app.config import DATA_DIR
_UPLOADS_DIR = DATA_DIR / "uploads" / "voice_refs"   # yazılabilir dizin (read-only AppImage mount fix)


def _elevenlabs_available() -> bool:
    return bool(ELEVENLABS_API_KEY and ELEVENLABS_API_KEY.startswith("sk_"))


def _fish_reference_exists() -> bool:
    return bool(FISH_REFERENCE_AUDIO) and Path(FISH_REFERENCE_AUDIO).exists()


@router.get("/status")
@limiter.limit("20/minute")
async def tts_status(request: Request):

    """Aktif TTS zinciri ve her sağlayıcının durumu."""
    chain = []
    if USE_FISH_TTS:
        chain.append({"id": "fish", "label": "Fish Speech S2", "active": True, "note": "Birincil — lokal SOTA"})
    if USE_ELEVENLABS_TTS:
        avail = _elevenlabs_available()
        chain.append({"id": "elevenlabs", "label": "ElevenLabs", "active": avail,
                       "note": "" if avail else "API key eksik (.env ELEVENLABS_API_KEY)"})
    chain.append({"id": "edge", "label": "Edge TTS", "active": True, "note": M("ses.edge-notu")})
    chain.append({"id": "google", "label": "Google TTS", "active": True, "note": M("ses.google-notu")})

    ref_exists = _fish_reference_exists()
    return {
        "chain": chain,
        "fish_enabled": USE_FISH_TTS,
        "fish_url": FISH_TTS_URL if USE_FISH_TTS else None,
        "fish_reference": FISH_REFERENCE_AUDIO if ref_exists else None,
        "fish_reference_exists": ref_exists,
        "elevenlabs_enabled": USE_ELEVENLABS_TTS,
        "elevenlabs_available": _elevenlabs_available(),
        "edge_always_on": True,
    }


class TestRequest(BaseModel):
    # Boş = dilin varsayılan test cümlesi (ses.test-metni) — sınıf düzeyinde M()
    # çağrılmaz: modül yüklenirken donar, dil değişince eski dilde kalırdı.
    text: str = ""


@router.post("/test")
@limiter.limit("10/minute")
async def tts_test(request: Request, req: TestRequest):
    """Mevcut TTS zinciriyle kısa test sesi üret."""
    metin = req.text or M("ses.test-metni")
    if len(metin) > 300:
        raise HTTPException(status_code=400, detail=M("ses.test-metni-uzun"))
    try:
        audio_bytes = await synthesize(metin)
        return {
            "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
            "format": "wav",
        }
    except Exception as e:
        # 🔎 2026-08-02: kaynak adı MESAJA yazılıyor. Sebep: geliştiricinin Windows turunda
        # ekranda `401 Missing Authentication header` çıktı ve **iki tur boyunca kimin
        # söylediği bulunamadı** — 5 dış servis tek tek elendi. Yukarı akış metnini
        # kullanıcıya sızdıran uç, KİMİN konuştuğunu da söylemek zorunda; yoksa ekran
        # görüntüsü teşhis için yetersiz kalıyor.
        raise HTTPException(status_code=500, detail=M("ses.tts-hatasi", sebep=e))


@router.post("/reference")
@limiter.limit("20/minute")
async def upload_reference(request: Request, file: UploadFile = File(...)):

    """Fish TTS için referans ses yükle (WAV/MP3, max 10 MB).

    Dosya `uploads/voice_refs/` dizinine kaydedilir.
    Ortam değişkeni FISH_REFERENCE_AUDIO'yu güncellemez (restart gerektirir);
    frontend bu yolu kaydedip sonraki oturumda .env'e koyulabilir.
    """
    allowed = {"audio/wav", "audio/mp3", "audio/mpeg", "audio/x-wav", "audio/wave"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=415, detail=M("ses.ref-bicim"))

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail=M("ses.ref-buyuk"))

    _UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "ref.wav").suffix or ".wav"
    dest = _UPLOADS_DIR / f"reference{ext}"
    dest.write_bytes(data)

    return {
        "status": "ok",
        "path": str(dest),
        "size_kb": round(len(data) / 1024, 1),
        "note": M("ses.fish-referans-notu"),
    }

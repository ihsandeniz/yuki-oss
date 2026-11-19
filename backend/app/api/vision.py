"""Faz 4 — Vision endpoint: POST /api/vision
Faz K — Ambient endpoints: GET /api/ambient/status, POST /api/ambient/mode
Faz K+ — Live frame stream: GET /api/ambient/frame
"""

import asyncio
import base64
import logging
import time as _time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.limiter import limiter
from app.mesajlar import M
from app.services.llm import ChatResponse
from app.services.state_machine import YukiState, get_state_machine
from app.services.emotion_engine import get_emotion_engine
from app.services.vision import capture_and_analyze

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["vision"])

# Frame cache — grim çok sık çağrılmasın
_frame_cache: dict = {"b64": None, "ts": 0.0}
_frame_lock = asyncio.Lock()  # Race condition protection
_FRAME_TTL = 1.5  # saniye — telefon 2s'de bir istek atarsa yeter


class VisionRequest(BaseModel):
    prompt: str = Field(default="Ekranda ne var? Kısaca açıkla.", min_length=1, max_length=500)  # i18n-istisna: Vision LLM'e giden varsayılan istem


class VisionReply(BaseModel):
    reply: str
    emotion: str
    intensity: float
    state: str


@router.post("/vision", response_model=VisionReply)
@limiter.limit("10/minute")
async def vision(request: Request, req: VisionRequest):
    """Ekran görüntüsü al, Vision LLM ile analiz et, yanıt döndür."""
    sm = get_state_machine()
    ee = get_emotion_engine()

    await sm.transition(YukiState.THINKING)

    try:
        resp: ChatResponse = await capture_and_analyze(req.prompt)
    except Exception as exc:
        log.error("[vision] Hata: %s", repr(exc))
        await sm.force(YukiState.IDLE)
        raise

    await ee.update(resp.emotion.emotion, resp.emotion.intensity)
    await sm.transition(YukiState.TALKING)
    await sm.force(YukiState.IDLE)

    return VisionReply(
        reply=resp.text,
        emotion=resp.emotion.emotion,
        intensity=resp.emotion.intensity,
        state=sm.state.value,
    )


# ── Faz K — Ambient endpoints ─────────────────────────────────────── #

class AmbientModeRequest(BaseModel):
    mode: Literal["passive", "active", "focused", "off"]


@router.get("/ambient/status")
@limiter.limit("10/minute")
async def ambient_status(request: Request):

    """Ambient Watcher durumunu döndürür."""
    from app.config import AMBIENT_ENABLED
    if not AMBIENT_ENABLED:
        return {"enabled": False, "running": False, "mode": None, "interval": None}
    try:
        from app.services.ambient import _watcher
        if _watcher is None:
            return {"enabled": AMBIENT_ENABLED, "running": False, "mode": None, "interval": None, "last_analysis": None}
        return _watcher.status()
    except Exception as e:
        log.warning("Ambient status hatası: %s", e)
        return {"enabled": AMBIENT_ENABLED, "running": False, "error": str(e), "last_analysis": None}


@router.get("/ambient/frame")
@limiter.limit("120/minute")
async def ambient_frame(request: Request):
    """Anlık ekran görüntüsünü JPEG olarak döndürür — canlı yayın için."""
    from app.services.tools import take_screenshot

    async with _frame_lock:
        now = _time.time()
        # Cache geçerliyse aynı frame'i döndür (grim'i gereksiz çağırma)
        if _frame_cache["b64"] is None or now - _frame_cache["ts"] > _FRAME_TTL:
            try:
                result = await asyncio.to_thread(take_screenshot)
                if result.startswith("SCREENSHOT_DATA:"):
                    _frame_cache["b64"] = result.split(":", 1)[1]
                    _frame_cache["ts"] = now
            except Exception as e:
                log.warning("Frame hatası: %s", e)

        b64 = _frame_cache["b64"]
        if not b64:
            raise HTTPException(status_code=503, detail=M("gorme.ekran-alinamadi"))

    return Response(
        content=base64.b64decode(b64),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.post("/ambient/scan")
@limiter.limit("10/minute")
async def ambient_scan(request: Request):
    """Anında tek bir ekran taraması yapar (interval beklenmez)."""
    from app.config import AMBIENT_ENABLED
    if not AMBIENT_ENABLED:
        raise HTTPException(status_code=403, detail="AMBIENT_ENABLED=false")
    from app.services.ambient import _watcher
    if _watcher is None:
        raise HTTPException(status_code=503, detail=M("gorme.izleyici-yok"))
    result = await _watcher.scan_now()
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.post("/ambient/mode")
@limiter.limit("20/minute")
async def set_ambient_mode(request: Request, req: AmbientModeRequest):
    """Ambient Watcher modunu çalışma zamanında değiştirir."""
    from app.config import AMBIENT_ENABLED
    if not AMBIENT_ENABLED:
        raise HTTPException(status_code=403, detail=M("gorme.kapali"))
    try:
        from app.services.ambient import _watcher
        if _watcher is None:
            raise HTTPException(status_code=503, detail=M("gorme.izleyici-henuz-yok"))
        await _watcher.set_mode(req.mode)
        return {"ok": True, "mode": req.mode}
    except HTTPException:
        raise
    except Exception as e:
        log.error("Ambient mod değiştirme hatası: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

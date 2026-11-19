"""Kapsamlı health check — alt sistem durumları, uptime, DB latency.

/health endpoint'i tarafından kullanılır.
"""

from __future__ import annotations

import logging
import time

from app.config import (
    MEMORY_ENABLED,
    MEMORY_BACKEND,
    ELEVENLABS_API_KEY,
    BROWSER_ENABLED,
)

logger = logging.getLogger(__name__)

# Ürün sürümü — TEK KAYNAK. Yayın turunda burası ve `electron/package.json` bump edilir.
# (Hata günlüğü de buradan okur; ikinci bir kopya bırakmak bugün kapatılan hata
# sınıfının ta kendisiydi — sabit değerin iki yerde yaşaması.)
APP_VERSION = "1.0.0"


async def get_health_report(app_start_time: float) -> dict:
    """Tüm alt sistemlerin durumunu toplar.

    Returns:
        {
            "status": "ok" | "degraded" | "error",
            "uptime_seconds": float,
            "version": str,
            "subsystems": { ... },
        }
    """
    subsystems: dict[str, dict] = {}
    degraded = False

    # Uptime
    uptime = time.monotonic() - app_start_time

    # ── Database ──
    # Ürün varsayılanı gömülü sqlite-vec: PostgreSQL hiç KULLANILMAZ. Eskiden
    # bu dalda da pool aranıyor, bulunamayınca "degraded" damgası basılıyordu →
    # sapasağlam çalışan pakette kullanıcı /health'te "degraded" görüyordu.
    if MEMORY_BACKEND == "sqlite":
        subsystems["database"] = {"status": "not_used", "detail": "gömülü sqlite-vec"}  # i18n-istisna: teşhis ucu alt sistem notu, geliştirici okur
    elif MEMORY_ENABLED:
        try:
            from app.db.connection import get_pool
            pool = await get_pool()
            if pool:
                t0 = time.monotonic()
                async with pool.acquire() as conn:
                    await conn.execute("SELECT 1")
                latency = (time.monotonic() - t0) * 1000
                subsystems["database"] = {"status": "ok", "latency_ms": round(latency, 1)}
            else:
                subsystems["database"] = {"status": "error", "detail": "pool yok"}
                degraded = True
        except Exception as e:
            subsystems["database"] = {"status": "error", "detail": str(e)}
            degraded = True
    else:
        subsystems["database"] = {"status": "disabled"}

    # ── STT Model ──
    try:
        from app.services.stt import _model
        subsystems["stt_model"] = {"status": "loaded" if _model is not None else "not_loaded"}
    except Exception:
        subsystems["stt_model"] = {"status": "unknown"}

    # ── TTS ──
    subsystems["tts"] = {
        "provider": "elevenlabs" if ELEVENLABS_API_KEY else "edge-tts",
    }

    # ── Memory ──
    if MEMORY_ENABLED and MEMORY_BACKEND == "sqlite":
        try:
            from app.services.memory import get_memory_service
            count = await get_memory_service().count()
            subsystems["memory"] = {"enabled": True, "count": count, "backend": "sqlite-vec"}
        except Exception:
            subsystems["memory"] = {"enabled": True, "count": None, "backend": "sqlite-vec"}
    elif MEMORY_ENABLED:
        try:
            from app.db.connection import get_pool
            pool = await get_pool()
            if pool:
                async with pool.acquire() as conn:
                    count = await conn.fetchval("SELECT COUNT(*) FROM memories")
                subsystems["memory"] = {"enabled": True, "count": count}
            else:
                subsystems["memory"] = {"enabled": True, "count": None}
        except Exception:
            subsystems["memory"] = {"enabled": True, "count": None}
    else:
        subsystems["memory"] = {"enabled": False}

    # ── Browser ──
    subsystems["browser"] = {"enabled": BROWSER_ENABLED}

    status = "degraded" if degraded else "ok"

    return {
        "status": status,
        "uptime_seconds": round(uptime, 1),
        "version": APP_VERSION,
        "character": "Yuki",
        "subsystems": subsystems,
    }

"""Bio API — /api/bio endpoint'i.

Samsung Galaxy Watch 7 (veya herhangi bir wearable) verisi alır/döner.
Veri yoksa simülasyon modu devrededir.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request

from app.limiter import limiter

router = APIRouter()

# ── Son bio snapshot ──────────────────────────────────────────── #
_bio_data: dict[str, Any] = {}
_last_update: float = 0.0


@router.post("/api/bio")
@limiter.limit("30/minute")
async def post_bio(request: Request):
    """Wearable / HCGateway / companion app'ten veri al."""
    global _bio_data, _last_update
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid json"}
    _bio_data = data
    _last_update = time.monotonic()
    return {"ok": True}


@router.get("/api/bio")
@limiter.limit("100/minute")
async def get_bio(request: Request):
    """Son bio snapshot'ı döndür. Veri yoksa simülasyon flag'i ekle."""
    age = time.monotonic() - _last_update if _last_update else None
    stale = age is None or age > 900  # 15 dakikadan eski = stale
    return {
        "ok": True,
        "stale": stale,
        "last_update": datetime.fromtimestamp(
            time.time() - (time.monotonic() - _last_update)
        ).isoformat() if _last_update else None,
        "data": _bio_data if not stale else {},
    }

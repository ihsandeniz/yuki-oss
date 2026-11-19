"""Karakter (persona) seçici API — persona kaydındaki karakterler arası runtime geçiş (Faz 4).

2026-11-14: kayıtta yalnız Yuki var; `available` tek elemanlı döner.

Aktif karakter; LLM persona promptunu (kimlik + kişilik) ve TTS ses tonunu
(Faz 5) değiştirir. Değişim anında uygulanır; sesli/yazılı komut
(switch_character tool) ile de tetiklenir. Frontend tema da WS ile senkronlanır.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.mesajlar import M
from app.limiter import limiter

from app.services.personas import (
    get_persona,
    get_persona_meta,
    list_personas,
    set_persona,
)

router = APIRouter(prefix="/api/character", tags=["character"])


class CharacterBody(BaseModel):
    name: str  # personas.PERSONAS anahtarı (şu an yalnız "yuki")


@router.get("")
@limiter.limit("100/minute")
async def get_current_character(request: Request):
    """Aktif karakteri ve seçilebilir karakterleri (kilit durumuyla) döndürür."""
    from app.services import yetki
    available = [
        {**p, "locked": not yetki.character_allowed(p["name"])}
        for p in list_personas()
    ]
    return {"character": get_persona(), "available": available}


@router.post("")
@limiter.limit("30/minute")
async def change_character(request: Request, body: CharacterBody):
    """Karakteri çalışırken değiştirir ve frontend'i bilgilendirir."""
    from app.services import yetki
    if not yetki.character_allowed((body.name or "").lower().strip()):
        return {
            "ok": False, "locked": True,
            "error": M("karakter.kilitli", karakter=body.name),
        }
    if not set_persona(body.name):
        return {
            "ok": False,
            "error": M("karakter.gecersiz", karakter=body.name,
                       liste=", ".join(p["name"] for p in list_personas())),
        }
    key = get_persona()
    meta = get_persona_meta(key)
    # Frontend temasının senkron kalması için WS yayınla (sesli komutla da değişebilir).
    try:
        from app.api.websocket import _manager
        await _manager.broadcast({"type": "switch_character", "character": key})
    except Exception:
        pass
    return {"ok": True, "character": key, "label": meta["label"], "title": meta["title"]}

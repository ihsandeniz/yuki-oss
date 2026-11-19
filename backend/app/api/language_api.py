"""Dil API — İKİ EKSEN: konuşma dili (tr/ja/en) + arayüz dili (tr/en).

Konuşma dili: TTS sesi (Edge), STT (Whisper dili), LLM yanıt dili (prompt).
Sesli komut (`set_language` aracı) yalnız bu ekseni değiştirir.
Arayüz dili: ekran metni (frontend sözlüğü, backend `M()`, Electron kabuğu).

🔑 Seçenek listeleri kaynaktan türetilir (`config.LANGUAGES`, `config.ARAYUZ_DILLERI`),
sabit değil. İki eksen kararı (2026-10-04) 09-18'in tek eksen kararını geçersiz kılar.

Yanıt ve WS `language_changed` olayı aynı durumu taşır: `{language, arayuz}`
(`config.dil_durumu()`). `language` alanının anlamı (konuşma) değişmedi — eski
istemciler (widget) bozulmaz.
"""

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.mesajlar import M
from app.limiter import limiter

from app.config import (
    ARAYUZ_DILLERI, LANGUAGES, dil_durumu, set_arayuz_dili, set_language,
)

router = APIRouter(prefix="/api/language", tags=["language"])


class LanguageBody(BaseModel):
    # Konuşma dili: "tr" | "ja" | "en" (veya "türkçe"/"japonca"/"İngilizce" takma adları)
    language: Optional[str] = None
    # Arayüz dili: "tr" | "en"
    arayuz: Optional[str] = None


def _available() -> list[dict]:
    return [
        {"code": code, "name": cfg["name"], "flag": cfg.get("flag", "")}
        for code, cfg in LANGUAGES.items()
    ]


def _arayuz_available() -> list[dict]:
    return [
        {"code": code, "name": LANGUAGES[code]["name"], "flag": LANGUAGES[code].get("flag", "")}
        for code in ARAYUZ_DILLERI
    ]


@router.get("")
@limiter.limit("100/minute")
async def get_current_language(request: Request):
    """İki eksenin aktif değeri + seçilebilir listeleri."""
    return {
        **dil_durumu(),
        "available": _available(),
        "arayuz_available": _arayuz_available(),
    }


@router.post("")
@limiter.limit("30/minute")
async def change_language(request: Request, body: LanguageBody):
    """Bir ekseni çalışırken değiştirir ve frontend'i bilgilendirir.

    Tek istekte TEK eksen: `arayuz` verildiyse arayüz, yoksa `language` (konuşma).
    """
    if body.arayuz is not None:
        if not set_arayuz_dili(body.arayuz):
            return {
                "ok": False,
                "error": M("ayar.gecersiz-dil", deger=body.arayuz, secenekler=list(ARAYUZ_DILLERI)),
            }
        mesaj = None   # arayüz değişimini ekran kendisi gösterir; Yuki konuşmaz
    elif body.language is not None:
        if not set_language(body.language):
            return {
                "ok": False,
                "error": M("ayar.gecersiz-dil", deger=body.language, secenekler=list(LANGUAGES)),
            }
        # Onay cümlesi dil KAYDINDAN gelir (2026-09-18, FAZ 1) — Yuki'nin yeni
        # konuşma dilinde söylediği cümle.
        cfg = LANGUAGES[dil_durumu()["language"]]
        mesaj = cfg.get("switch_msg", cfg["name"])
    else:
        return {"ok": False, "error": M("ayar.gecersiz-dil", deger="", secenekler=list(LANGUAGES))}

    durum = dil_durumu()
    # Frontend senkron kalsın (sesli komutla da değişebilir); iki eksen birlikte gider.
    try:
        from app.services.event_bus import bus
        await bus.publish("language_changed", durum)
    except Exception:
        pass
    return {"ok": True, **durum, "mesaj": mesaj}

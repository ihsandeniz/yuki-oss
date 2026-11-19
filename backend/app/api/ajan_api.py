"""AJAN sekmesi — REST yüzeyi. YALNIZ İZLEYİCİ.

Bilgisayarda çalışan yapay zekâ ajanlarını tek ekranda izleme: Yuki'nin uzman
ekibi · Claude Code · Codex · rutinler. Ajan oturumlarına metin/komut gönderme
açık kaynak sürümde YOK (karar: 2026-10-17 yuki-urun-acik-kaynak § Ek karar).
Sistem destesi bu modülde DEĞİL — arayüz kendi ucunu okur (`/api/monitor`).

Ekip çalışmasının CANLI hâli REST'te yok: orchestrator olayları event bus'a
yayınlar, /ws/realtime onları zaten taşır (tek kaynak). Buradaki `/ekip` yalnız
kadroyu ve kapıları verir — ekran açılınca kartlar boş kalmasın.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request

from app.limiter import limiter
from app.services import ajan_oturumlari

router = APIRouter(prefix="/api/ajan", tags=["ajan"])


@router.get("/oturumlar")
@limiter.limit("60/minute")
async def oturumlar(request: Request) -> dict:  # noqa: ARG001 — limiter Request ister
    """Claude Code + Codex oturumları (salt okunur)."""
    claude, codex = await asyncio.gather(
        asyncio.to_thread(ajan_oturumlari.claude_oturumlari),
        asyncio.to_thread(ajan_oturumlari.codex_oturumlari),
    )
    return {"claude": claude, "codex": codex}


@router.get("/ekip")
async def ekip() -> dict:
    """Yuki'nin uzman kadrosu + ekip kapıları. Canlı durum WS olaylarından gelir."""
    from app.services import orchestrator
    from app.services import yetki
    from app.services.personas import list_personas

    return {
        "uzmanlar": [p for p in list_personas() if p["name"] != "yuki"],
        "koordinator": next((p for p in list_personas() if p["name"] == "yuki"), None),
        "uzman_acik": yetki.feature_allowed("companion_team"),
        "meclis_acik": yetki.feature_allowed("companion_council"),
        "ayar": {
            "en_cok_gorev": orchestrator._ayar("COUNCIL_MAX_TASKS", orchestrator.COUNCIL_MAX_TASKS),
            "ayni_anda": orchestrator._ayar("COUNCIL_CONCURRENCY", orchestrator.COUNCIL_CONCURRENCY),
        },
    }


@router.get("/rutinler")
async def rutinler() -> dict:
    """Kayıtlı rutinler + bir sonraki çalışma zamanı (salt okunur)."""
    from app.services import routines
    from app.services import yetki

    acik = yetki.feature_allowed("routines")
    if not acik:
        return {"acik": False, "rutinler": []}
    try:
        from app.services.scheduler import get_scheduler
        zamanlayici = get_scheduler()
    except Exception:
        zamanlayici = None
    liste = []
    for r in routines._load():
        sonraki = None
        if zamanlayici is not None and r.get("id"):
            try:
                is_ = zamanlayici.get_job(f"routine_{r['id']}")
                if is_ is not None and is_.next_run_time is not None:
                    sonraki = is_.next_run_time.isoformat()
            except Exception:
                sonraki = None
        liste.append({
            "id": str(r.get("id", "")),
            "ad": str(r.get("name") or r.get("id") or ""),
            "zaman": str(r.get("schedule", "")),
            "tur": str(r.get("action_type", "")),
            "eylem": str(r.get("action", ""))[:300],
            "etkin": bool(r.get("enabled", True)),
            "sonraki": sonraki,
        })
    return {"acik": True, "rutinler": liste}

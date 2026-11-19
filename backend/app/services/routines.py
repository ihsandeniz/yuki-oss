"""Rutinler (Faz 25) — tekrarlı cron/interval + aksiyon, RESTART-GÜVENLİ.

scheduler.py (APScheduler + MemoryJobStore) runtime motoru; `data/routines.json`
DURABLE store. Startup'ta JSON'dan yeniden yüklenip zamanlanır → reload bozuk /
full-restart olsa da rutinler sağ çıkar.

Aksiyon tipleri:
  - team    → action = council hedefi (run_team) — bayrak kullanım
  - skill   → action = skill adı (skill__<ad>, parametresiz/varsayılanlı)
  - message → action = düz metin (Yuki proaktif söyler)

Zamanlama: 'HH:MM' (günlük) · 'every 30m|2h|1d' / 'her 30dk'.
"""
from __future__ import annotations

import os
import json
import logging
import re
import uuid
from pathlib import Path

from app.services import guvenli_json

logger = logging.getLogger(__name__)

# 🐞 2026-07-31: burası `backend/data/routines.json`e sabitti → satılan pakette
# `backend/` AppImage squashfs'i = SALT OKUNUR. Rutinler **Ultra'nın vitrinde
# satılan özelliği** ama kullanıcı rutin oluşturamıyordu (gerçek mount'ta ölçüldü:
# `[Errno 30] Read-only file system`). config_manager'la aynı hata sınıfı.
# YUKI_DATA_DIR varsa (Electron userData) oraya; yoksa eski davranış korunur.
_DATA_ROOT = Path(os.getenv("YUKI_DATA_DIR") or Path(__file__).resolve().parents[2])
_PATH = _DATA_ROOT / "data" / "routines.json"
_ACTION_TYPES = ("team", "skill", "message")


def _load() -> list[dict]:
    return guvenli_json.oku(_PATH, [], list)


def _save(routines: list[dict]) -> None:
    guvenli_json.yaz(_PATH, routines)


def _parse_schedule(s: str):
    """'HH:MM' → günlük cron; 'every N m|h|d' / 'her N dk|sa|gün' → interval. (trigger, kwargs) | None."""
    s = (s or "").strip().lower()
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return ("cron", {"hour": h, "minute": mi})
        return None
    m = re.match(r"^(?:every|her)\s*(\d+)\s*(m|dk|dakika|min|minute|h|sa|saat|hour|d|g|gün|day)s?$", s)
    if m:
        n, u = int(m.group(1)), m.group(2)
        if n < 1:
            # 🔴 "her 0 dk": APScheduler 0 aralığı sessizce 1 SANİYEYE çevirir → rutin her
            # saniye koşar (team/skill eylemiyse her saniye bir LLM çağrısı = kullanıcının parası).
            return None
        if u in ("m", "dk", "dakika", "min", "minute"):
            return ("interval", {"minutes": n})
        if u in ("h", "sa", "saat", "hour"):
            return ("interval", {"hours": n})
        if u in ("d", "g", "gün", "day"):
            return ("interval", {"days": n})
    return None


async def _run_action(routine: dict) -> None:
    """Rutin tetiklenince aksiyonu çalıştır ve sonucu kullanıcıya ilet."""
    at = routine.get("action_type")
    action = routine.get("action", "")
    name = routine.get("name") or routine.get("id", "?")
    try:
        if at == "team":
            from app.services.orchestrator import run_team
            result = await run_team(str(action))
        elif at == "skill":
            from app.services.tools import call_tool
            sk = str(action).strip()
            sk = sk[len("skill__"):] if sk.startswith("skill__") else sk
            result = await call_tool(f"skill__{sk}", {})
        elif at == "message":
            result = str(action)
        else:
            result = f"(bilinmeyen aksiyon tipi: {at})"
    except Exception as e:  # noqa: BLE001
        result = f"(rutin '{name}' hata: {e})"
    try:
        from app.services.scheduler import _push_proactive
        await _push_proactive(f"[Rutin: {name}] {result}"[:1500], "rutin")
    except Exception as e:  # noqa: BLE001
        logger.warning("rutin '%s' sonucu iletilemedi: %s", name, e)


def _schedule_one(routine: dict) -> bool:
    parsed = _parse_schedule(routine.get("schedule", ""))
    if not parsed:
        logger.warning("rutin '%s': geçersiz schedule '%s'", routine.get("id"), routine.get("schedule"))
        return False
    trigger, kwargs = parsed
    from app.services.scheduler import get_scheduler
    sched = get_scheduler()
    sched.add_job(
        _run_action, trigger=trigger, args=[routine],
        id=f"routine_{routine['id']}", replace_existing=True, **kwargs,
    )
    return True


def register_all() -> None:
    """Startup'ta JSON'daki tüm etkin rutinleri zamanla (restart-güvenlik)."""
    from app.config import SCHEDULER_ENABLED
    if not SCHEDULER_ENABLED:
        return
    routines = _load()
    ok = 0
    for r in routines:
        if r.get("enabled", True):
            try:
                if _schedule_one(r):
                    ok += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("rutin '%s' zamanlanamadı: %s", r.get("id"), e)
    if routines:
        logger.info("rutinler: %d/%d zamanlandı", ok, len(routines))


# ── Araç yüzeyi ──────────────────────────────────────────────────────────────
def create_routine(name: str, schedule: str, action_type: str, action: str) -> str:
    if action_type not in _ACTION_TYPES:
        return f"Hata: action_type {'/'.join(_ACTION_TYPES)} olmalı."
    if _parse_schedule(schedule) is None:
        return "Hata: schedule 'HH:MM' ya da 'every 30m|2h|1d' biçiminde olmalı."
    routines = _load()
    rid = uuid.uuid4().hex[:8]
    r = {"id": rid, "name": name or rid, "schedule": schedule,
         "action_type": action_type, "action": action, "enabled": True}
    routines.append(r)
    _save(routines)
    scheduled = False
    try:
        scheduled = _schedule_one(r)
    except Exception as e:  # noqa: BLE001
        logger.warning("create_routine zamanlama hatası: %s", e)
    tail = "" if scheduled else " (kaydedildi; sonraki restart'ta zamanlanır)"
    return f"Rutin kuruldu ✓ [{rid}] '{r['name']}' — {schedule} → {action_type}{tail}"


def list_routines() -> str:
    routines = _load()
    if not routines:
        return "Kayıtlı rutin yok."
    lines = []
    for r in routines:
        off = "" if r.get("enabled", True) else " (kapalı)"
        lines.append(f"• [{r['id']}] {r.get('name')} — {r.get('schedule')} → "
                     f"{r.get('action_type')}: {str(r.get('action'))[:60]}{off}")
    return "\n".join(lines)


def delete_routine(routine_id: str) -> str:
    routines = _load()
    n = len(routines)
    routines = [r for r in routines if r.get("id") != routine_id]
    if len(routines) == n:
        return f"Rutin bulunamadı: {routine_id}"
    _save(routines)
    try:
        from app.services.scheduler import get_scheduler
        get_scheduler().remove_job(f"routine_{routine_id}")
    except Exception:  # noqa: BLE001
        pass
    return f"Rutin silindi: {routine_id}"

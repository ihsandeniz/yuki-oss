"""skill_events.py — Beceri/olay kazanım kartı yayını (frontend SkillCard).

Frontend `window.SkillCard.show({type,name,...})` kartını WS üzerinden tetikler.
4 olay tipi:
  A skill  — `skill` hafıza scope'una kayıt        (memory.add)
  B unlock — bir aracın İLK başarılı kullanımı       (dispatcher.call_tool)
  C task   — çok-araçlı görev/analiz başarısı         (runner.run)
  D taught — kullanıcı `/öğren` ile öğretince          (websocket chat)

Tüm yayınlar spam'a karşı tip-başına cooldown'lı. _manager lazy import (dairesel
import'tan kaçınmak için) — yayın asla çağıranı bozmaz (try/except yutar).
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

log = logging.getLogger(__name__)

# ── kalıcılık: ömür-boyu "ilk kullanım" takibi ──
_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
_USED_PATH = os.path.join(_DATA_DIR, "used_tools.json")
_used: Optional[set[str]] = None

# ── tip-başına cooldown (sn) — spam koruması ──
_COOLDOWN = {"skill": 8.0, "unlock": 0.0, "task": 60.0, "taught": 0.0, "ipucu": 0.0}  # ipucu kendi susturmasını tutar (arac_ipucu.SUSMA_SN)
_last_emit: dict[str, float] = {}

# ── araç → Türkçe "yetenek" adı (B unlock kartı) ──
# i18n: kart metni arayüz dilinde FRONTEND'de kurulur — buradan
# `name_key="beceri.arac.<araç>"` gider, sözlük `frontend/js/diller/*.js`'te.
# Bu tablo yalnız anahtarı OLAN araçları seçer ve eski/anahtarsız istemci için
# düz-metin yedeğini taşır. Yeni araç eklersen sözlüğe de ekle (test denetler).
_FRIENDLY = {
    "take_screenshot": "EKRAN GÖZÜ", "send_screenshot_to_chat": "EKRAN PAYLAŞIMI",
    "web_search": "ARAYICI", "browse_web": "GEZGİN",
    "read_file": "OKUYUCU", "write_file": "YAZICI", "append_file": "EKLEYİCİ",
    "list_directory": "HARİTACI",
    "get_system_info": "SİSTEM GÖZÜ", "monitor_system": "NÖBETÇİ",
    "send_notification": "HABERCİ", "get_clipboard": "PANO OKUR", "set_clipboard": "PANO YAZAR",
    "memory_search": "ANIMSAYIŞ", "control_media": "EZGİ",
    "open_application": "ÇAĞIRICI", "control_volume": "SES USTASI", "switch_tab": "REHBER",
    "switch_character": "SURET", "youtube_music": "NAĞME",
}


def _load_used() -> set[str]:
    global _used
    if _used is not None:
        return _used
    try:
        with open(_USED_PATH, "r", encoding="utf-8") as f:
            _used = set(json.load(f))
    except Exception:
        _used = set()
    return _used


def _save_used() -> None:
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_USED_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted(_used or []), f, ensure_ascii=False)
    except Exception as e:
        log.debug("used_tools kaydedilemedi: %s", e)


async def emit(kind: str, name: str, *, sub: Optional[str] = None,
               banner: Optional[str] = None, tag: Optional[str] = None,
               name_key: Optional[str] = None, tag_key: Optional[str] = None,
               tag_vars: Optional[dict] = None) -> None:
    """Beceri/olay kartını tüm WS istemcilerine yayınla (cooldown'lı, asla raise etmez)."""
    try:
        cd = _COOLDOWN.get(kind, 8.0)
        now = time.monotonic()
        if cd > 0 and (now - _last_emit.get(kind, 0.0)) < cd:
            return
        _last_emit[kind] = now
        payload = {"type": kind, "name": (name or "—")[:48]}
        if sub:    payload["sub"] = sub
        if banner: payload["banner"] = banner
        if tag:    payload["tag"] = tag[:60]
        # Anahtar gelirse frontend metni kendi dilinde kurar; `name`/`tag` yedektir.
        if name_key: payload["name_key"] = name_key
        if tag_key:  payload["tag_key"] = tag_key
        if tag_vars: payload["tag_vars"] = tag_vars
        from app.api.websocket import _manager  # lazy → dairesel import yok
        await _manager.broadcast({"type": "skill_event", "payload": payload})
    except Exception as e:
        log.debug("skill_event yayınlanamadı: %s", e)


def _is_error_result(res) -> bool:
    if not isinstance(res, str):
        return False
    head = res.lstrip()[:24].lower()
    return head.startswith(("hata", "error", "❌", "⚠️", "exception", "traceback", "filenotfound"))


async def note_tool_use(tool_name: str, result) -> None:
    """B — bir aracın İLK başarılı kullanımında 'kilit açıldı' kartı."""
    try:
        if _is_error_result(result):
            return
        used = _load_used()
        if tool_name in used:
            return
        used.add(tool_name)
        _save_used()
        friendly = _FRIENDLY.get(tool_name, tool_name.replace("_", " ").upper())
        await emit("unlock", friendly, tag=f"ilk kullanım · {tool_name}",
                   name_key=(f"beceri.arac.{tool_name}" if tool_name in _FRIENDLY else None),
                   tag_key="beceri.unlock.tag-arac", tag_vars={"arac": tool_name})
    except Exception as e:
        log.debug("note_tool_use hata: %s", e)


async def note_skill_memory(content: str, kind: str = "skill") -> None:
    """A/D — skill hafıza kaydı (kind='skill') ya da kullanıcı öğretisi (kind='taught')."""
    name = (content or "").strip().split("\n")[0]
    if len(name) > 40:
        name = name[:38] + "…"
    # Hafıza içeriği kullanıcının kendi metnidir — çevrilmez; yalnız boşsa kalıp ad.
    await emit(kind, name or "YENİ BECERİ",
               name_key=(None if name else "beceri.yeni-beceri"))


async def note_task(n_tools: int) -> None:
    """C — çok-araçlı görev/analiz başarısı (eşik dispatcher tarafında)."""
    await emit("task", "BÜYÜK BİLGE", tag=f"{n_tools} araç · analiz tamam",
               name_key="beceri.buyuk-bilge",
               tag_key="beceri.task.tag-sayi", tag_vars={"n": n_tools})

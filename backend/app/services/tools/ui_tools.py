"""Yuki arayüz (frontend) kontrol araçları — sekme değiştirme.

Yuki kendi uygulamasının sekmeleri arasında geçiş yapabilir. WebSocket
üzerinden frontend'e {"type": "switch_tab", "tab": <kanonik>} mesajı push
edilir; frontend `window.switchTab(tab)` ile o sekmeyi açar.
"""
from __future__ import annotations

import logging
from app.mesajlar import M

logger = logging.getLogger(__name__)

# Kanonik sekme adı → kullanıcıya gösterilecek etiket (index.html nav ile BİREBİR).
#
# 🔴 2026-08-03 — SAHA RAPORU. Bu tablo kişisel sürümden kopyalanmış hâliyle
# duruyordu: map · finance · drive · faces · ağ tarama. **Bu sekmelerin hiçbiri satılan
# üründe yok** (frontend/index.html'de yalnız chat · planner · hq var). Sonuç:
#   • `list_tabs` kullanıcıya var olmayan 5 sekmeyi sayıyordu,
#   • `switch_tab("harita")` "Harita sekmesine geçildi." diye BAŞARI raporluyor,
#     frontend ise bilinmeyen sekmede sessizce sohbete düşüyordu.
# Araç, olmayan bir şeyi yaptım demektense yapamadığını söylemeli.
# Ders: kişiselden kopyalanan tablolar üründe **kırpılmalı**, kırpılmazsa yalan söyler.
_TABS: dict[str, str] = {
    "chat": "Sohbet",
    "planner": "PLAN (görev/zaman çizgisi)",
    "hq": "Ayarlar",
}

# Doğal dil takma adları → kanonik sekme
_ALIASES: dict[str, str] = {
    "sohbet": "chat", "konuşma": "chat", "ana": "chat", "anasayfa": "chat",
    "plan": "planner", "planlayıcı": "planner", "planlama": "planner",
    "takvim": "planner", "ajanda": "planner", "görevler": "planner",
    "ayar": "hq", "ayarlar": "hq", "settings": "hq", "seçenekler": "hq",
}

# Sekme → gerektirdiği lisans özelliği (yoksa kademe kapısı yok demektir).
# PLAN ekranı Pro özelliğidir; Free'de router düzeyinde 403 döner (api/todo.py).
_TAB_FEATURE: dict[str, str] = {"planner": "planner"}


def _resolve(tab: str) -> str | None:
    key = (tab or "").strip().lower()
    if key in _TABS:
        return key
    return _ALIASES.get(key)


def _sekme_listesi() -> str:
    return ", ".join(f"{v} ({k})" for k, v in _TABS.items())


def _kademe_izin_veriyor(canonical: str) -> bool:
    """Sekme bu lisansta açık mı. Entitlement okunamazsa engelleme (parite)."""
    feature = _TAB_FEATURE.get(canonical)
    if not feature:
        return True
    try:
        from app.services import yetki
        return bool(yetki.feature_allowed(feature))
    except Exception:  # pragma: no cover — lisans katmanı yoksa eski davranış
        return True


async def switch_tab(tab: str) -> str:
    """Frontend'de belirtilen sekmeye geçer."""
    canonical = _resolve(tab)
    if canonical is None:
        return M("sekme.gecersiz", sekme=tab, liste=_sekme_listesi())
    if not _kademe_izin_veriyor(canonical):
        # Sessizce başarısız olma — kullanıcı neden açılmadığını bilmeli.
        return M("sekme.kapali", ad=_TABS[canonical])
    # Lazy import — dairesel import'u kır (websocket → llm → tools → ui_tools)
    from app.api.websocket import _manager
    await _manager.broadcast({"type": "switch_tab", "tab": canonical})
    logger.info("switch_tab → %s", canonical)
    return M("sekme.gecildi", ad=_TABS[canonical])


async def list_tabs() -> str:
    """Mevcut uygulama sekmelerini listeler — kademede KAPALI olanı 'kapalı' diye işaretler."""
    parcalar = []
    for k, v in _TABS.items():
        parcalar.append(f"{v} ({k})" if _kademe_izin_veriyor(k)
                        else f"{v} ({k}) — " + M("sekme.kapali-eki"))
    return M("sekme.mevcut", liste=", ".join(parcalar))


# ── Karakter / persona geçişi (Faz 4) ────────────────────────────────
# Doğal dil takma adları → kanonik persona anahtarı. Kanonik adlar (PERSONAS
# anahtarları) ayrıca yazılmaz — `_karakter_anahtari` onları canlı tanır, yeni
# persona eklenince takma adı (varsa) buraya eklenir.
_CHAR_ALIASES: dict[str, str] = {}


def _karakter_anahtari(character: str) -> str | None:
    from app.services.personas import PERSONAS
    ad = (character or "").strip().lower()
    if ad in PERSONAS:
        return ad
    hedef = _CHAR_ALIASES.get(ad)
    return hedef if hedef in PERSONAS else None


async def switch_character(character: str) -> str:
    """Aktif karaktere (persona) geçer — kimlik, kişilik ve ses tonu değişir."""
    from app.services.personas import set_persona, get_persona_meta, list_personas

    key = _karakter_anahtari(character)
    if key is None:
        valid = ", ".join(f"{p['label']} ({p['name']})" for p in list_personas())
        return M("karakter.gecersiz", karakter=character, liste=valid)
    from app.services import yetki
    if not yetki.character_allowed(key):
        return M("karakter.kilitli", karakter=key)
    if not set_persona(key):
        return M("karakter.gecilemedi", karakter=character)
    meta = get_persona_meta(key)
    # Frontend teması + ses güncellensin diye WS push.
    from app.api.websocket import _manager
    await _manager.broadcast({"type": "switch_character", "character": key})
    logger.info("switch_character → %s", key)
    return f"{meta['label']} ({meta['title']}) karakterine geçildi."


async def list_characters() -> str:
    """Seçilebilir karakterleri listeler."""
    from app.services.personas import list_personas, get_persona

    from app.services import yetki

    active = get_persona()
    parts = []
    for p in list_personas():
        tag = " [aktif]" if p["name"] == active else ""
        if not yetki.character_allowed(p["name"]):
            tag = " [🔒 kapalı]"
        parts.append(f"{p['label']} ({p['name']}) — {p['title']}{tag}")
    return "Mevcut karakterler: " + " · ".join(parts)

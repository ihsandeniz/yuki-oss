"""Yetki — açık kaynak sürümde kademe kilidi yok.

Her araç, her özellik ve her karakter herkese açıktır. Durum değiştiren araçlar
onay kapısından geçer (approval_gate). Eski ürünün `licensing/` paketinin
(Lite/Pro/Ultra + imzalı lisans) yerine geçer.

Tek istisna: bayraklı özellikler — Fitnes (`FITNES`, varsayılan kapalı, HQ › Sistem anahtarı;
g4 2026-11-12) ve kamera görüşü (`GORUS`). Kapalıyken araçları LLM'e sunulmaz/çalışmaz, REST
uçları 404 (`ozellik_kapisi`). Bayrak istek anında okunur. Komuta Paneli 11-13'te tamamen
kaldırıldı (bekçi: tests/test_komuta_paneli_yok.py).
Bekçi: tests/test_ozellik_bayrak.py
"""
from __future__ import annotations

from fastapi import HTTPException

from app import config as _config

from app.services.personas import PERSONAS as _PERSONAS  # noqa: E402

# Karakter listesi personas.PERSONAS'tan gelir (2026-11-14: yalnız Yuki). `ozet()`
# canlı okur; bu ad geriye uyumluluk için import anındaki görüntüdür.
CHARACTERS_ALL = list(_PERSONAS)

# Ön yüzün düğme/sekme göstermek için sorduğu özellik adları — hepsi açık.
FEATURES = (
    "planner", "drive_backup", "push_notifications", "device_manager", "map_panel",
    "semantic_memory", "multi_character", "routines", "companion_team",
    "companion_council",
)


# Bayraklı özellik → config bayrağı. `GET /api/yetki` features'ta bu adlarla görünür.
BAYRAKLI = {"fitnes": "FITNES", "gorus": "GORUS"}

# Bayraklı özelliğin LLM araçları (services/tools/fitness_tools.py · gorus_tools.py).
ARACLAR = {
    "gorus": frozenset({"kameraya_bak"}),
    "fitnes": frozenset({
        "get_fitness_summary", "log_meal", "delete_meal", "list_meals", "log_workout_exercise",
        "list_workout", "get_fitness_config", "update_fitness_config", "save_fitness_template",
        "list_fitness_templates", "delete_fitness_template",
    }),
}


def bayrak_acik(ozellik: str) -> bool:
    """Bayraklı özellik açık mı — yalnız config'te tam `True` açar (fail-closed)."""
    return getattr(_config, BAYRAKLI[ozellik], False) is True


def tool_allowed(name: str) -> bool:
    for ozellik, adlar in ARACLAR.items():
        if name in adlar:
            return bayrak_acik(ozellik)
    return True


def character_allowed(key: str) -> bool:  # noqa: ARG001 — tüm karakterler açık
    return True


def feature_allowed(feature: str) -> bool:
    if feature in BAYRAKLI:
        return bayrak_acik(feature)
    return True


def ozellik_kapisi(ozellik: str):
    """Router bağımlılığı: bayrak kapalıysa 404 — kayıtsız uçla aynı yanıt (Atölye deseni)."""
    def _kapi() -> None:
        if not bayrak_acik(ozellik):
            raise HTTPException(status_code=404, detail="Not Found")
    _kapi.__name__ = f"{ozellik}_kapisi"
    return _kapi


def ozet() -> dict:
    """Ön yüzün okuduğu yetki özeti (`GET /api/yetki`)."""
    from app.services.tools.dispatcher import TOOLS
    return {
        "tools": sorted(t["function"]["name"] for t in TOOLS),
        "features": {**{f: feature_allowed(f) for f in FEATURES},
                     **{o: bayrak_acik(o) for o in BAYRAKLI}},
        "characters": list(_PERSONAS),
        "all_characters": list(_PERSONAS),
    }

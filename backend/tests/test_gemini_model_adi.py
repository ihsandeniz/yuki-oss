"""Gemini model kimlikleri: kaldırılan 2.x adları geri gelmesin.

Google 2026-12-01'de `gemini-2.5-flash` isteklerini `gemini-3.5-flash-lite`'a yönlendiriyor,
`gemini-2.0-flash` ise kapatıldı (kaynak: https://ai.google.dev/gemini-api/docs/models).
OpenRouter kimliği `google/gemini-3.5-flash-lite` (aynı fiyat, `GET /api/v1/models`).
"""
import re
from pathlib import Path

from app import config
from app.services import llm_providers

KOK = Path(__file__).resolve().parents[2]
YENI_OR = "google/gemini-3.5-flash-lite"
YENI_GOOGLE = "gemini-3.5-flash-lite"
ESKI = re.compile(r"gemini-2\.(?:0|5)-flash(?![-\w])")   # gemini-2.0-flash-live-001 gibi ayrı modeller hariç


def test_gorsel_model_varsayilani():
    kaynak = (KOK / "backend/app/config.py").read_text(encoding="utf-8")
    m = re.search(r'VISION_MODEL: str = os\.getenv\("VISION_MODEL", "([^"]+)"\)', kaynak)
    assert m and m.group(1) == YENI_OR


def test_openrouter_on_ayari():
    kimlikler = [p["id"] for p in config.MODEL_PRESETS["openrouter"]]
    assert YENI_OR in kimlikler
    assert not any(ESKI.search(k) for k in kimlikler)


def test_google_dogrudan_saglayici():
    g = llm_providers.kayit("google")
    assert g.varsayilan_model == YENI_GOOGLE
    assert g.one_cikan[0] == YENI_GOOGLE
    assert not any(ESKI.search(k) for k in g.one_cikan)


def test_on_yuz_ve_ornek_env():
    core = (KOK / "frontend/js/core.js").read_text(encoding="utf-8")
    assert f"id: '{YENI_OR}'" in core
    assert not ESKI.search(core)
    assert not ESKI.search((KOK / ".env.example").read_text(encoding="utf-8"))


def test_etiket_lite_surumunu_soyler():
    """Etiket "Gemini 3.5 Flash" olursa kullanıcı ayrı bir model olan google/gemini-3.5-flash'ı seçtiğini sanar."""
    etiket = next(p["label"] for p in config.MODEL_PRESETS["openrouter"] if p["id"] == YENI_OR)
    assert etiket.endswith("Flash-lite"), etiket
    core = (KOK / "frontend/js/core.js").read_text(encoding="utf-8")
    m = re.search(r"id: '" + re.escape(YENI_OR) + r"',\s*label: '([^']+)'", core)
    assert m and m.group(1).endswith("Flash-lite"), m and m.group(1)

"""Müşteriye ham teknik metin gösterilmez — 429 / 500 / paket hijyeni.

Ölçülen kusur (2026-08-04): lisans ve anahtar panelleri yalnız mutlu yolu ve
`ok:false` yolunu insanca anlatıyordu.

- **500** → FastAPI düz metin `Internal Server Error` döner (JSON değil) →
  frontend `r.json()` patlar → `catch` `String(e)` basar → müşteri
  *"SyntaxError: Unexpected token 'I'…"* görür.
- **429** → slowapi `{"error": "Rate limit exceeded: 10 per 1 minute"}` döner →
  frontend `d.ok` yok diye bunu **geçersiz lisans** sanar. Yalnız çirkin değil
  **yanlış teşhis**: müşteri sağlam anahtarını çöpe atar (ElevenLabs 401 dersi).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.hata_yaniti import KOD_BEKLENMEYEN, KOD_HIZ_SINIRI, _saniye_ayikla
from app.main import app

KOK = Path(__file__).resolve().parents[2]


@pytest.fixture
def istemci():
    # Limiter durumu SÜREÇ GENELİNDE ortak — sıfırlanmazsa ilk 429 testi
    # sonrakilerin hepsini 429'a düşürür ve testler birbirini yalanlar.
    from app.limiter import limiter

    limiter.reset()
    # raise_server_exceptions=False → gerçek müşteri gibi HTTP yanıtı görürüz,
    # test içinde istisna fırlamaz.
    yield TestClient(app, raise_server_exceptions=False)
    limiter.reset()


# Lisans ucu (eski ölçüm yüzeyi) açık kaynakta kalktı; aynı genel işleyiciler
# 10/dakika sınırlı `/api/chat/clear-messages` üzerinden ölçülür. Asıl iş sahtelenir.
UC = "/api/chat/clear-messages"


@pytest.fixture
def sessiz_temizlik(monkeypatch):
    from app.api import chat as chat_api

    async def _bos(**_k):
        return None
    monkeypatch.setattr(chat_api, "clear_history", _bos)


# ── 429 — "çok sık denedin", ASLA "geçersiz anahtar" ────────────────
def test_hiz_siniri_turkce_ve_makine_kodlu(istemci, sessiz_temizlik):
    for _ in range(12):
        r = istemci.post(UC)
    assert r.status_code == 429
    d = r.json()
    assert d["ok"] is False
    assert d["kod"] == KOD_HIZ_SINIRI
    assert "Rate limit exceeded" not in d["error"], "ham slowapi metni sızıyor"
    assert "bekleyip tekrar dene" in d["error"]


def test_hiz_siniri_anahtari_suclamaz(istemci, sessiz_temizlik):
    """Yanlış teşhis koruması: müşteri sağlam anahtarını çöpe atmasın."""
    for _ in range(12):
        r = istemci.post(UC)
    metin = r.json()["error"].lower()
    assert "geçersiz" not in metin
    assert "sorun değil" in metin.replace("i̇", "i")


def test_hiz_siniri_retry_after_verir(istemci, sessiz_temizlik):
    for _ in range(12):
        r = istemci.post(UC)
    assert r.headers.get("Retry-After") == "60"


@pytest.mark.parametrize(
    "detay,beklenen",
    [
        ("10 per 1 minute", 60),
        ("100 per 1 hour", 3600),
        ("5 per 30 second", 30),
        ("3 per 1 day", 86400),
        ("anlaşılmaz metin", None),
    ],
)
def test_saniye_ayikla(detay, beklenen):
    assert _saniye_ayikla(detay) == beklenen


# ── 500 — JSON, ham traceback yok ───────────────────────────────────
def test_beklenmeyen_hata_json_doner(istemci, monkeypatch):
    """Düz metin 'Internal Server Error' frontend'de SyntaxError'a dönüşüyordu."""
    from app.api import chat as chat_api

    async def patlat(**_k):
        raise OSError(13, "Permission denied", "/salt-okunur/gecmis.db")

    monkeypatch.setattr(chat_api, "clear_history", patlat)
    r = istemci.post(UC)

    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/json"), \
        "gövde JSON değil → istemci r.json() ile patlar"
    d = r.json()
    assert d["ok"] is False
    assert d["kod"] == KOD_BEKLENMEYEN
    assert "SAĞLIK" in d["error"], "kullanıcıya ne yapacağı söylenmiyor"


def test_beklenmeyen_hata_teknik_ayrinti_sizdirmaz(istemci, monkeypatch):
    """Dosya yolu / errno / istisna adı yanıtta görünmemeli (günlüğe gider)."""
    from app.api import chat as chat_api

    async def patlat(**_k):
        raise OSError(13, "Permission denied", "/salt-okunur/gizli/gecmis.db")

    monkeypatch.setattr(chat_api, "clear_history", patlat)
    govde = istemci.post(UC).text

    for sizinti in ("Traceback", "PermissionError", "/salt-okunur", "Errno",
                    "Internal Server Error"):
        assert sizinti not in govde, f"ham teknik ayrıntı sızıyor: {sizinti}"


# ── Paket hijyeni: playwright kaydı da dışlanır ─────────────────────
BUILDER_CONFIGLERI = [
    "electron/electron-builder.yml",
    "electron/electron-builder-full.yml",
    "electron/electron-builder-win.yml",
    "electron/electron-builder-win-full.yml",
]


@pytest.mark.parametrize("cfg", BUILDER_CONFIGLERI)
def test_playwright_dist_info_de_dislanir(cfg):
    """`playwright/` dışlanmıştı ama `playwright-<sürüm>.dist-info/` sızıyordu.

    Ölçüldü (Yuki-0.5.8-win-x64-lite.zip): 34.346 bayt metadata. Boyuttan çok
    tutarlılık sorunu — paket yokken `importlib.metadata` "kurulu" der.
    """
    metin = (KOK / cfg).read_text(encoding="utf-8")
    assert '"!**/site-packages/playwright/**"' in metin
    assert '"!**/site-packages/playwright-*.dist-info/**"' in metin


@pytest.mark.parametrize("cfg", BUILDER_CONFIGLERI)
def test_msvc_dll_yanlislikla_dislanmaz(cfg):
    """Dışlama desenleri MSVC runtime'ı süpürmemeli (onnxruntime ona bağlı)."""
    metin = (KOK / cfg).read_text(encoding="utf-8")
    assert not re.search(r'"!.*msvcp140', metin, re.IGNORECASE)

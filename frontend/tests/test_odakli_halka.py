"""Odaklı Halka — HALKA merkez menüsü, tarayıcı testleri (2026-10-11).

Yapı kapıları: `backend/tests/test_odakli_halka.py`.

Çalıştırma (sunucu gerekli — ikinci port):
    YUKI_URL=http://127.0.0.1:8021 backend/venv/bin/python -m pytest frontend/tests/test_odakli_halka.py -q

Ölçülenler:
  1. Halkaya tıklayınca menü açılır; SEKMELER = gezinme çubuğunda GÖRÜNEN sekmeler
     (kademe kilidi yok — hepsi).
  2. Sekme düğümü sekmeye geçirir ve menüyü kapatır.
  3. KARAKTER: tek karakterde (Yuki, 2026-11-14 ürün kararı) grup HİÇ çizilmez — kişisel
     hud-ring.js'teki kapının aynısı; kayıtlı 'kar' seçimi SEKMELER'e düşer.
  4. ← → grup değiştirir (SEKMELER ↔ SİTELER) ve kalıcıdır; Esc kapatır.
  5. 390'da düğümler ≥44px; 390/1280 JS istisnası 0.
"""
from __future__ import annotations

import os

import pytest

from perdesiz import PERDESIZ_JS   # açılış sinematiği + ilk kurulum perdesi tıklamayı keser

BASE = os.getenv("YUKI_URL", "http://127.0.0.1:8001")


def _sunucu_var() -> bool:
    import urllib.request
    try:
        return urllib.request.urlopen(BASE + "/health", timeout=3).status == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _sunucu_var(), reason=f"sunucu yok: {BASE}")


@pytest.fixture(scope="module")
def tarayici():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _halka(br, vp=(1280, 800), grup="sekme"):
    ctx = br.new_context(viewport={"width": vp[0], "height": vp[1]}, service_workers="block")
    pg = ctx.new_page()
    pg.add_init_script(PERDESIZ_JS)
    pg._hatalar = []
    pg.on("pageerror", lambda e: pg._hatalar.append(str(e)))
    pg.add_init_script("if (!sessionStorage.getItem('_k')) { localStorage.setItem('yukiViewMode','hud-ring'); "
                       "localStorage.setItem('halka_menu_grup_v1','%s'); sessionStorage.setItem('_k','1'); }" % grup)
    pg.goto(BASE + "/ui/", wait_until="networkidle")
    if "hud-ring-mode" not in pg.evaluate("() => document.body.className"):
        pg.evaluate("() => window.setViewMode('hud-ring')")
    pg.wait_for_selector("#hr-odak")
    return pg


def _ac(pg):
    r = pg.locator("#hr-ring-wrap").bounding_box()
    pg.mouse.click(r["x"] + r["width"] / 2, r["y"] + r["height"] / 2)
    pg.wait_for_function("() => document.getElementById('hr-ring-wrap').classList.contains('hr-wheel-open')")
    pg.wait_for_timeout(450)   # düğüm geçişi (opacity/scale) bitsin


DUGUMLER = "() => [...document.querySelectorAll('#hr-odak .hr-od-dugum')].map(b => b.dataset.od)"
NAV_GORUNUR = "() => [...document.querySelectorAll('#tab-items .tab-btn[data-tab]')].filter(b => !b.hidden).map(b => b.dataset.tab)"


@pytest.mark.parametrize("vp", [(390, 844), (1280, 800)], ids=["390", "1280"])
def test_sekmeler_nav_ile_ayni_ve_hedef_boyutu(tarayici, vp):
    pg = _halka(tarayici, vp)
    try:
        _ac(pg)
        assert pg.evaluate(DUGUMLER) == pg.evaluate(NAV_GORUNUR)
        boy = pg.evaluate("() => [...document.querySelectorAll('#hr-odak .hr-od-dugum')].map(b => Math.min(b.getBoundingClientRect().width, b.getBoundingClientRect().height))")
        assert min(boy) >= 43.5, f"düğüm 44px altında: {boy}"
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


def test_tum_sekmeler_menude(tarayici):
    """Açık kaynak sürüm: kademe kilidi yok — PLAN dahil sekmeler hem nav'da hem menüde."""
    pg = _halka(tarayici)
    try:
        assert "planner" in pg.evaluate(NAV_GORUNUR), "PLAN herkese açık olmalı"
        _ac(pg)
        assert "planner" in pg.evaluate(DUGUMLER)
    finally:
        pg.context.close()


def test_sekme_dugumu_gecirir_ve_kapatir(tarayici):
    pg = _halka(tarayici)
    try:
        _ac(pg)
        pg.click('#hr-odak .hr-od-dugum[data-od="hq"]')
        assert not pg.evaluate("() => document.getElementById('hr-ring-wrap').classList.contains('hr-wheel-open')")
        pg.wait_for_function("() => document.getElementById('tab-btn-hq').getAttribute('aria-selected') === 'true'", timeout=3000)
    finally:
        pg.context.close()


def test_tek_karakterde_karakter_grubu_yok(tarayici):
    """Tek karakter (Yuki): KARAKTER grubu çizilmez; eski kurulumdan kalan 'kar' seçimi SEKMELER açar."""
    pg = _halka(tarayici, grup="kar")
    try:
        _ac(pg)
        gruplar = pg.evaluate("() => [...document.querySelectorAll('#hr-odak .hr-od-grup')].map(b => b.dataset.odGrup)")
        assert gruplar == ["sekme", "site"], gruplar
        assert pg.evaluate(DUGUMLER) == pg.evaluate(NAV_GORUNUR), "kayıtlı 'kar' SEKMELER'e düşmedi"
        assert pg.locator("#hr-odak .hr-od-kar").count() == 0
    finally:
        pg.context.close()


def test_ok_tusu_grup_degistirir_kalici_esc_kapatir(tarayici):
    pg = _halka(tarayici)
    try:
        _ac(pg)
        pg.keyboard.press("ArrowRight")
        assert pg.evaluate("() => localStorage.getItem('halka_menu_grup_v1')") == "site"
        assert "__tum" in pg.evaluate(DUGUMLER)   # SİTELER grubunun her zaman var olan düğümü
        pg.keyboard.press("ArrowLeft")
        assert pg.evaluate("() => localStorage.getItem('halka_menu_grup_v1')") == "sekme"
        pg.keyboard.press("Escape")
        assert not pg.evaluate("() => document.getElementById('hr-ring-wrap').classList.contains('hr-wheel-open')")
    finally:
        pg.context.close()

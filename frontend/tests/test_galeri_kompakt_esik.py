"""GALERİ klasör rayı 1280 ekranda AÇIK başlar (2026-11-13 arayüz turu).

Kök neden (11-13 ölçümü): sekme kabuğu çerçevesi 1280 ekranda galeri iframe'ini 1256 px'e indiriyor; kompakt
eşik 1279 olduğu için ray her 1280 ekranda çekmeceye düşüp kapalı başlıyordu. Eşik 1239'a indi; CSS
(`css/galeri.css` @media) ile JS (`js/galeri.js` KOMPAKT) AYNI sayıyı taşımalı.

    YUKI_URL=http://127.0.0.1:18831 python -m pytest frontend/tests/test_galeri_kompakt_esik.py -q
(sunucu: dosya_sinav_sunucu.py — galeri kökü geçici `Resimlerim`; ya da parolasız herhangi bir ikinci örnek)

Ölçülenler:
  1. Statik: CSS kompakt eşiği == JS KOMPAKT eşiği == 1239.
  2. 1256 genişlikte (kabuk içi 1280): ray yerinde (x ≥ 0, görünür), sıralama segmenti görünür, ☰ klasör düğmesi gizli.
  3. 1200 genişlikte: ray çekmece (ekran dışı), klasör düğmesi görünür. JS istisnası 0.
"""
from __future__ import annotations

import os
import re
import urllib.request
from pathlib import Path

import pytest

BASE = os.getenv("YUKI_URL", "http://127.0.0.1:18831")
ANAHTAR = os.getenv("YUKI_ANAHTAR", "sinav-anahtari")
ON = Path(__file__).resolve().parents[1]


def _esikler():
    css = (ON / "css/galeri.css").read_text(encoding="utf-8")
    js = (ON / "js/galeri.js").read_text(encoding="utf-8")
    c = re.search(r"KOMPAKT[^\n]*\n(?:[^\n]*\n){0,4}?@media \(max-width: (\d+)px\)", css)
    j = re.search(r"var KOMPAKT = window\.matchMedia\('\(max-width: (\d+)px\)'\)", js)
    return (int(c.group(1)) if c else None), (int(j.group(1)) if j else None)


def test_css_js_esik_ayni():
    c, j = _esikler()
    assert c == j == 1239, (c, j)


def _sunucu_var() -> bool:
    try:
        return urllib.request.urlopen(BASE + "/ui/galeri.html", timeout=3).status == 200
    except Exception:
        return False


tarayicili = pytest.mark.skipif(not _sunucu_var(), reason=f"sunucu yok: {BASE}")


@pytest.fixture(scope="module")
def tarayici():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _ac(tarayici, gen):
    ctx = tarayici.new_context(viewport={"width": gen, "height": 800}, service_workers="block")
    ctx.add_init_script(f"try{{localStorage.setItem('aliceToken','{ANAHTAR}')}}catch(e){{}}")
    pg = ctx.new_page()
    hatalar = []
    pg.on("pageerror", lambda e: hatalar.append(str(e)))
    pg.goto(BASE + "/ui/galeri.html")
    pg.wait_for_timeout(1500)
    return ctx, pg, hatalar


@tarayicili
def test_1256_ray_yerinde(tarayici):
    ctx, pg, hatalar = _ac(tarayici, 1256)
    ray = pg.locator("#gl-ray").bounding_box()
    assert ray and ray["x"] >= 0 and ray["width"] > 150, ray
    assert pg.locator("#gl-ray").is_visible()
    assert pg.locator("#gl-sirala-seg").is_visible()
    assert pg.locator("#gl-ray-ac").is_hidden()
    assert hatalar == [], hatalar
    ctx.close()


@tarayicili
def test_1200_ray_cekmece(tarayici):
    ctx, pg, hatalar = _ac(tarayici, 1200)
    ray = pg.locator("#gl-ray").bounding_box()
    assert ray is None or ray["x"] + ray["width"] <= 0, ray
    assert pg.locator("#gl-ray-ac").is_visible()
    assert hatalar == [], hatalar
    ctx.close()

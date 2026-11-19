"""Yuki `show_media` → WS `{type:'galeri_ac', id, ad, klasor_id}` → GALERİ sekmesi o dosyayla açılır.

Arka uç yarısı: `backend/app/services/tools/galeri.py` (yayın) + `backend/tests/test_galeri_arac.py`.
Bu dosya ön yüz yarısını ölçer: core.js WS dalı → `window.galeriAc` (tab-nav.js) → `galeri.html?ac=<id>`.
Mesaj sahte: `/ws/realtime` gerçek sunucuya bağlı kalır, test araya kendi mesajını sokar.

Çalıştırma (sunucu gerekli — ikinci port, geçici veri):
    YUKI_URL=http://127.0.0.1:18821 python -m pytest frontend/tests/test_galeri_ac.py -q

Ölçülenler (390 ve 1280, JS istisnası 0):
  1. Galeri hiç açılmamışken mesaj → sekme seçili + görünür, iframe `?ac=<id>` ile kurulur.
  2. Galeri önceden `?ac`'siz açıksa → iframe yeni `?ac=<id>` ile yeniden kurulur (galeri.js `ac`'yi yalnız yüklenirken okur).
  3. Kimliksiz mesaj → hiçbir şey değişmez.
"""
from __future__ import annotations

import json
import os

import pytest

from perdesiz import PERDESIZ_JS

BASE = os.getenv("YUKI_URL", "http://127.0.0.1:8001")
GENISLIKLER = [(390, 844), (1280, 800)]
KIMLIK = "0123456789abcdef"


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


def _sayfa(br, vp):
    ctx = br.new_context(viewport={"width": vp[0], "height": vp[1]}, service_workers="block")
    pg = ctx.new_page()
    pg._hatalar = []
    pg.on("pageerror", lambda e: pg._hatalar.append(str(e)))
    pg._ws = []

    def _yonlendir(ws):
        ws.connect_to_server()          # gerçek sunucu bağlantısı sürer; test yalnız ARAYA mesaj sokar
        pg._ws.append(ws)

    pg.route_web_socket("**/ws/realtime*", _yonlendir)
    pg.add_init_script(PERDESIZ_JS)
    pg.goto(BASE + "/ui/", wait_until="networkidle")
    pg.wait_for_function("() => typeof window.galeriAc === 'function' && typeof window.switchTab === 'function'")
    for _ in range(40):
        if pg._ws:
            break
        pg.wait_for_timeout(100)
    assert pg._ws, "/ws/realtime bağlantısı kurulmadı"
    return pg


def _gonder(pg, mesaj):
    pg._ws[-1].send(json.dumps(mesaj))


def _galeri_acik(pg):
    return pg.evaluate("""() => { const b = document.getElementById('tab-btn-galeri'), t = document.getElementById('tab-galeri');
        return b.getAttribute('aria-selected') === 'true' && !t.hidden && t.getClientRects().length > 0; }""")


def _src(pg):
    return pg.evaluate("() => document.getElementById('galeri-iframe').getAttribute('src') || ''")


@pytest.mark.parametrize("vp", GENISLIKLER, ids=["390", "1280"])
def test_ilk_acilista_ac_parametresiyle_kurulur(tarayici, vp):
    pg = _sayfa(tarayici, vp)
    try:
        assert not _galeri_acik(pg)
        assert "galeri.html" not in _src(pg)
        _gonder(pg, {"type": "galeri_ac", "id": KIMLIK, "ad": "deniz.png", "klasor_id": "k1"})
        pg.wait_for_function("() => (document.getElementById('galeri-iframe').getAttribute('src') || '').includes('ac=')")
        assert f"/ui/galeri.html?ac={KIMLIK}&" in _src(pg), _src(pg)
        pg.wait_for_function("""() => document.getElementById('tab-btn-galeri').getAttribute('aria-selected') === 'true'""")
        assert _galeri_acik(pg)
        pg.wait_for_timeout(300)
        assert f"ac={KIMLIK}" in _src(pg), "tembel ilk kurulum ?ac'yi ezdi: " + _src(pg)
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


@pytest.mark.parametrize("vp", GENISLIKLER, ids=["390", "1280"])
def test_acik_galeri_yeni_kimlikle_yeniden_kurulur(tarayici, vp):
    pg = _sayfa(tarayici, vp)
    try:
        pg.evaluate("() => window.switchTab('galeri')")
        pg.wait_for_function("() => (document.getElementById('galeri-iframe').getAttribute('src') || '').includes('galeri.html')")
        once = _src(pg)
        assert "ac=" not in once
        pg.evaluate("() => window.switchTab('chat')")
        _gonder(pg, {"type": "galeri_ac", "id": KIMLIK, "ad": "deniz.png", "klasor_id": None})
        pg.wait_for_function("(k) => (document.getElementById('galeri-iframe').getAttribute('src') || '').includes('ac=' + k)", arg=KIMLIK)
        pg.wait_for_function("() => document.getElementById('tab-btn-galeri').getAttribute('aria-selected') === 'true'")
        assert _galeri_acik(pg)
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


def test_kimliksiz_mesaj_bir_sey_degistirmez(tarayici):
    pg = _sayfa(tarayici, (1280, 800))
    try:
        _gonder(pg, {"type": "galeri_ac", "ad": "deniz.png"})
        pg.wait_for_timeout(600)
        assert not _galeri_acik(pg)
        assert "galeri.html" not in _src(pg)
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()

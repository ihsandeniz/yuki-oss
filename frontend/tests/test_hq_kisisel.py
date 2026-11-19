"""HQ — kişiseldeki gibi: Bilgisayarım (sistem gözlemevi) ile açılır + Gözlemevi dili (2026-11-13).

Kurallar:
  · Kurulum tamamsa (anahtar var ya da yerel model) HQ 'sistem' paneliyle açılır; değilse ya da durum
    bilinmiyorsa Anahtar sihirbazı ('key') — kurulumu eksik kullanıcı boş monitöre düşmez.
  · Çağıranın koyduğu hedef (window._hqHedefPanel) ezilmez.
  · Menüde Bilgisayarım en üstte.
  · Gözlemevi dili YALNIZ koyu temada (tema.js koyu temada data-tema'yı siler); açık/orta temada eski görünüm.

Tarayıcı katı için geçici veriyle ikinci portta sunucu:
    YUKI_DATA_DIR=$(mktemp -d) AUTH_TOKEN= uvicorn app.main:app --port 18823
    YUKI_URL=http://127.0.0.1:18823 python -m pytest frontend/tests/test_hq_kisisel.py -q
Monitör verisi (makine adı, süreçler) testte SAHTE yanıtla değiştirilir — ekran/çıktıya gerçek makine girmez.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

import pytest

FE = Path(__file__).resolve().parent.parent
INDEX = (FE / "index.html").read_text(encoding="utf-8")
INTRO = (FE / "js/intro-sequences.js").read_text(encoding="utf-8")
CSS = (FE / "css/hq-gozlemevi.css").read_text(encoding="utf-8")
BASE = os.getenv("YUKI_URL", "http://127.0.0.1:8001")


# ══ A · STATİK ═══════════════════════════════════════════════════════════════

def test_stil_bagi_hq_csslerinden_sonra():
    i = INDEX.find("/ui/css/hq-gozlemevi.css")
    assert i > 0, "hq-gozlemevi.css bağlı değil"
    for onceki in ("hq.css", "hq-monitor.css", "hq-ayarlar.css", "hq-cihazlar.css"):
        j = INDEX.find(f"/ui/css/{onceki}")
        assert 0 < j < i, f"hq-gozlemevi.css {onceki}'ten SONRA yüklenmeli"


def test_gozlemevi_fontlari_bagli():
    """Fraunces · Figtree · Martian Mono @font-face'i ana sayfaya bağlı (yoksa Georgia/Inter'e düşer)."""
    assert "/ui/css/fontlar-gozlemevi.css" in INDEX


def test_menu_bilgisayarim_en_ustte():
    a = INTRO.index("var HQ_MENU=[")
    ilk = re.search(r"\{tip:'panel', id:'(\w+)'", INTRO[a:])
    assert ilk and ilk.group(1) == "sistem", f"menünün ilk girdisi {ilk and ilk.group(1)}"
    assert len(re.findall(r"\{tip:'panel', id:'sistem'", INTRO)) == 1, "Bilgisayarım menüde iki kez"


def test_acilis_paneli_kancasi():
    assert "window.hqAcilisPaneli" in INTRO
    govde = INTRO[INTRO.index("window.hqAcilisPaneli"):]
    govde = govde[:govde.index("\n")]
    assert "'sistem'" in govde and "'key'" in govde and "_anKurulu()" in govde
    kanca = INTRO[INTRO.index("document.addEventListener('tabchange', function(e){\n    if(!e || !e.detail || e.detail.tab!=='hq')"):]
    kanca = kanca[:kanca.index("});")]
    assert "if(!window._hqHedefPanel)" in kanca, "çağıranın hedefi ezilebilir"


def _ustvirgul(metin):
    """Yalnız en dış düzeydeki virgülden böl (:is(a, b) içindeki virgül seçici ayırmaz)."""
    parca, d, cur = [], 0, ""
    for c in metin:
        d += c == "("; d -= c == ")"
        if c == "," and d == 0:
            parca.append(cur); cur = ""
        else:
            cur += c
    return parca + [cur]


def test_css_yalniz_koyu_temada():
    govde = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    seciciler = []
    for blok in re.findall(r"([^{}]+)\{", govde):
        blok = blok.strip()
        if not blok or blok.startswith("@"):
            continue
        seciciler += [x.strip() for x in _ustvirgul(blok) if x.strip()]
    assert seciciler
    yasak = [s for s in seciciler if not s.startswith(":root:not([data-tema]) #tab-hq") and not s.startswith(("from", "to"))]
    assert not yasak, f"tema kapısız / HQ dışı kural: {yasak[:5]}"


# ══ B · TARAYICI ═════════════════════════════════════════════════════════════

def _sunucu_var(url: str) -> bool:
    try:
        return urllib.request.urlopen(url + "/health", timeout=3).status == 200
    except Exception:
        return False


tarayici_gerek = pytest.mark.skipif(not _sunucu_var(BASE), reason=f"sunucu yok ({BASE})")


@pytest.fixture(scope="module")
def tarayici():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--disable-features=LocalNetworkAccessChecks,BlockInsecurePrivateNetworkRequests"])
        yield b
        b.close()


def _sayfa(br, vp=(1280, 800), anahtar=None, tema=None, hedef=None):
    """anahtar: None = sunucunun gerçek cevabı · dict = /api/llm/key/status sahte cevabı."""
    from perdesiz import PERDESIZ_JS
    ctx = br.new_context(viewport={"width": vp[0], "height": vp[1]}, service_workers="block")
    if anahtar is not None:
        ctx.route("**/api/llm/key/status*", lambda r: r.fulfill(json=anahtar))
    pg = ctx.new_page()
    pg._hatalar = []
    pg.on("pageerror", lambda e: pg._hatalar.append(str(e)))
    pg.add_init_script(PERDESIZ_JS)
    if tema:
        pg.add_init_script(f"try {{ localStorage.setItem('yukiTema_v1', {json.dumps(tema)}); }} catch (e) {{}}")
    pg.goto(BASE + "/ui/", wait_until="domcontentloaded")
    pg.wait_for_function("() => typeof window.switchTab === 'function' && typeof window.hqAcilisPaneli === 'function'")
    pg.wait_for_timeout(800)   # _hqDurumOgren
    if hedef:
        pg.evaluate(f"() => {{ window._hqHedefPanel = {json.dumps(hedef)}; }}")
    pg.evaluate("() => window.switchTab('hq')")
    pg.wait_for_function("() => { const h = document.getElementById('tab-hq'); return h && !h.hidden && h.dataset.hq; }")
    pg.wait_for_timeout(500)
    return pg


def _panel(pg):
    return pg.evaluate("() => document.getElementById('tab-hq').dataset.hq")


@tarayici_gerek
def test_kurulu_ise_bilgisayarim_acilir(tarayici):
    pg = _sayfa(tarayici, anahtar={"set": True, "yerel": False, "provider": "openrouter", "masked": "sk-…demo"})
    try:
        assert _panel(pg) == "sistem"
        assert pg.evaluate("() => document.getElementById('hq-panel-sistem').offsetParent !== null")
        assert not pg._hatalar, pg._hatalar
    finally:
        pg.context.close()


@tarayici_gerek
def test_yerel_model_de_kurulu_sayilir(tarayici):
    pg = _sayfa(tarayici, anahtar={"set": False, "yerel": True, "provider": "ollama"})
    try:
        assert _panel(pg) == "sistem"
    finally:
        pg.context.close()


@tarayici_gerek
def test_anahtarsiz_kurulumda_sihirbaz(tarayici):
    pg = _sayfa(tarayici, anahtar={"set": False, "yerel": False, "provider": "openrouter", "anahtar_gerekir": True})
    try:
        assert _panel(pg) == "key", "anahtarsız kurulum Anahtar sihirbazıyla açılmalı"
    finally:
        pg.context.close()


@tarayici_gerek
def test_cagiranin_hedefi_ezilmez(tarayici):
    pg = _sayfa(tarayici, anahtar={"set": True, "yerel": False, "provider": "openrouter"}, hedef="memmgr")
    try:
        assert _panel(pg) == "memmgr"
    finally:
        pg.context.close()


@tarayici_gerek
@pytest.mark.parametrize("vp", [(390, 844), (1280, 800)], ids=lambda v: f"{v[0]}")
def test_gozlemevi_dili_koyu_temada(tarayici, vp):
    pg = _sayfa(tarayici, vp, anahtar={"set": True, "yerel": False, "provider": "openrouter"})
    try:
        o = pg.evaluate("""() => {
          const b = document.querySelector('#hq-panel-sistem .oda-baslik'), k = document.querySelector('#hq-panel-sistem .mon-kart');
          const cb = getComputedStyle(b), ck = getComputedStyle(k);
          return { font: cb.fontFamily, italik: cb.fontStyle, kenar: ck.borderLeftWidth, ust: ck.borderTopWidth,
                   zemin: ck.backgroundColor, sw: document.documentElement.scrollWidth, w: innerWidth,
                   tema: document.documentElement.getAttribute('data-tema') };
        }""")
        assert o["tema"] is None, o
        assert "Fraunces" in o["font"] and o["italik"] == "italic", o
        assert o["kenar"] == "0px" and o["ust"] != "0px", f"kart → kıl çizgi değil: {o}"
        assert o["zemin"] in ("rgba(0, 0, 0, 0)", "transparent"), o
        assert o["sw"] <= o["w"] + 1, f"yatay taşma {o['sw']} > {o['w']}"
        assert not pg._hatalar, pg._hatalar
    finally:
        pg.context.close()


@tarayici_gerek
def test_acik_temada_eski_gorunum(tarayici):
    pg = _sayfa(tarayici, anahtar={"set": True, "yerel": False, "provider": "openrouter"}, tema="acik")
    try:
        o = pg.evaluate("""() => { const b = document.querySelector('#hq-panel-sistem .oda-baslik');
          return { font: getComputedStyle(b).fontFamily, tema: document.documentElement.getAttribute('data-tema') }; }""")
        assert o["tema"] == "acik", o
        assert "Fraunces" not in o["font"], f"Gözlemevi dili açık temaya sızdı: {o}"
    finally:
        pg.context.close()

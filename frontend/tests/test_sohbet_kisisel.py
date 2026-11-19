"""Sohbet ilk açılışı kişisel Yuki'deki gibi — HALKA + KARA MANA + PANEL (arayüz turu şerit A1, 2026-11-13).

Geliştirici seçimi (11-13): "Sohbet kişiseldeki gibi". Kişiselin ilk açılışı portre + 4 öneri kartı
DEĞİL; HALKA, KARA MANA teması, sağda PANEL listesi, HAFIZA rayın solunda, giriş altında durum
satırı (model · dil · küçült); telefonda PANEL alt çekmece (▴).

Çalıştırma:
    python3 frontend/tests/test_sohbet_kisisel.py                       # yalnız yapı kapıları
    YUKI_URL=http://127.0.0.1:8012 python3 -m pytest frontend/tests/test_sohbet_kisisel.py -q
Tarayıcı testleri sunucu yoksa atlanır; yapı kapıları her zaman koşar.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

FE = Path(__file__).resolve().parents[1]
BASE = os.getenv("YUKI_URL", "http://127.0.0.1:8001")


def _oku(yol: str) -> str:
    return (FE / yol).read_text(encoding="utf-8")


# ── Yapı kapıları (sunucusuz) ──────────────────────────────────────────

def test_varsayilan_mod_halka():
    js = _oku("modes/chat-modes.js")
    assert re.search(r"const VARSAYILAN_MOD = 'hud-ring';", js), "varsayılan mod HALKA değil"
    assert "localStorage.getItem(LS_MOD) || VARSAYILAN_MOD" in js, "ilk açılış varsayılanı kullanmıyor"
    # TAM BOY kullanıcısı sohbetteydi → HALKA'ya değil SOHBET'e döner
    assert "_mode = 'chat'; localStorage.setItem(LS_MOD, 'chat');" in js, "fullbody → chat göçü kalkmış"


def test_varsayilan_tema_kara_mana():
    js = _oku("modes/hud-ring.js")
    assert "const HALKA_TEMA_VARSAYILAN = 'kara-mana-goz';" in js
    ilk = re.search(r"const HALKA_TEMALAR = \[\s*\{ key: '([\w-]+)'", js).group(1)
    assert ilk == "kara-mana-goz", "seçicide varsayılan tema önde değil"


def test_widget_anahtari_v4_ve_ray_solu():
    js = _oku("modes/hud-ring.js")
    assert "const RING_STORAGE_KEY = 'yuki_hr_widgets_v4';" in js, "varsayılan yer değişti ama anahtar bump'lanmadı"
    assert "x: Math.max(10, sagSinir - cfg.w - 20)" in js, "HAFIZA PANEL rayının soluna oturmuyor"
    assert "collapsed: cekirdegeBiner(cfg.w)" in js, "çekirdeği örten widget başlık hâlinde açılmıyor"


def test_kisayollar_yeni_sekme_listesi():
    js = _oku("modes/hud-ring.js")
    od = dict(re.findall(r"(\w+): (\d)", re.search(r"const OD_KISAYOL = \{([^}]*)\}", js).group(1)))
    assert od == {"chat": "1", "planner": "2", "hq": "3", "map": "4", "ajan": "5", "yedek": "6", "galeri": "7", "dosya": "8"}


def test_dar_ekranda_ray_gizlenmiyor_cekmece_var():
    css = _oku("modes/hud-ring.css")
    assert not re.search(r"body\.hud-ring-mode #hr-side,\s*body\.hud-ring-mode \.hr-widget \{ display: none; \}", css), \
        "dar ekranda PANEL + widget'lar yine gizli"
    assert "body.hud-ring-mode.hr-cekmece-acik #hr-side" in css
    assert "body.hud-ring-mode #hr-cekmece-fab" in css
    js = _oku("modes/hud-ring.js")
    assert "_cekmeceKur();" in js and "_mobilTekWidget(widget);" in js
    assert "pane.appendChild(perde);" in js, "perde body'de: kabuğun yığın bağlamı dışında kalır, çekmeceyi örter"


def test_durum_satiri_halkada():
    js = _oku("modes/sohbet-sahne.js")
    assert "satir.hidden = !(on || halkada);" in js, "durum satırı HALKA'da gizli"
    assert "body.hud-ring-mode #hizli-satir:not([hidden])" in _oku("modes/hud-ring.css")


def test_kara_mana_zemini_mor():
    css = _oku("modes/halka-tema/kara-mana-goz.css")
    for ad in ("--kg-mor-gece", "--kg-bosluk", "--kg-bosluk-derin"):
        m = re.search(re.escape(ad) + r":\s*color-mix\(in oklab, var\(--(\w[\w-]*)\)", css)
        assert m and m.group(1) == "mor-yuzey", f"{ad} renksiz --bg'den türüyor (sahne düz siyah okunur)"


# ── Tarayıcı (sunucu gerekli) ───────────────────────────────────────────

def _sunucu_var() -> bool:
    import urllib.request
    try:
        return urllib.request.urlopen(BASE + "/health", timeout=3).status == 200
    except Exception:
        return False


tarayici_gerek = pytest.mark.skipif(not _sunucu_var(), reason=f"sunucu yok: {BASE}")


@pytest.fixture(scope="module")
def tarayici():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _sayfa(br, vp, on_kayit: str = "", hareket: str = "reduce"):
    sys.path.insert(0, str(Path(__file__).parent))
    from perdesiz import PERDESIZ_JS   # açılış sinematiği + ilk kurulum perdesi tıklamayı keser
    ctx = br.new_context(viewport={"width": vp[0], "height": vp[1]}, service_workers="block", reduced_motion=hareket)
    ctx.route("http://127.0.0.1:8000/**", lambda r: r.abort())   # kişisel Yuki'ye asla istek gitmesin
    pg = ctx.new_page()
    pg._hatalar = []
    pg.on("pageerror", lambda e: pg._hatalar.append(str(e)))
    pg.add_init_script(PERDESIZ_JS)
    if on_kayit:
        pg.add_init_script("if (!sessionStorage.getItem('_k')) { %s; sessionStorage.setItem('_k','1'); }" % on_kayit)
    pg.goto(BASE + "/ui/", wait_until="networkidle")
    pg.wait_for_function("() => document.body.classList.contains('hud-ring-mode') || document.body.classList.contains('sohbet-mode')")
    pg.wait_for_timeout(600)
    return pg


@tarayici_gerek
@pytest.mark.parametrize("hareket", ["reduce", "no-preference"], ids=["sabit", "animasyonlu"])
def test_ilk_acilis_1280(tarayici, hareket):
    pg = _sayfa(tarayici, (1280, 800), hareket=hareket)
    try:
        d = pg.evaluate("""() => {
          const r = e => e && e.getBoundingClientRect();
          const side = document.getElementById('hr-side'), w = document.querySelector('.hr-widget[data-hr-tab="memory"]');
          const ring = r(document.getElementById('hr-ring-wrap'));
          return { mod: document.body.className, tema: document.documentElement.dataset.halkaTema,
                   side: side && getComputedStyle(side).display, sideL: r(side).left,
                   wR: w && r(w).right, wL: w && r(w).left, wGizli: w && w.classList.contains('hr-w-hidden'),
                   cekirdekX: ring.left + ring.width / 2,
                   satir: !document.getElementById('hizli-satir').hidden,
                   fab: getComputedStyle(document.getElementById('hr-cekmece-fab')).display };
        }""")
        assert "hud-ring-mode" in d["mod"], f"ilk açılış HALKA değil: {d['mod']}"
        assert d["tema"] == "kara-mana-goz"
        assert d["side"] == "flex", "PANEL görünmüyor"
        assert not d["wGizli"], "HAFIZA açılışta kapalı"
        assert d["wR"] <= d["sideL"] + 1, f"HAFIZA PANEL'in üstüne biniyor ({d['wR']} > {d['sideL']})"
        assert d["wL"] > d["cekirdekX"], "HAFIZA rayın solunda değil (sol sütunda kalmış)"
        assert d["satir"], "durum satırı HALKA'da görünmüyor"
        assert d["fab"] == "none", "geniş ekranda çekmece düğmesi görünüyor"
        # ▲ gerçekten tıklanabilir (✕'in isabet alanı yutmuyor) — trial=False: gerçek tık
        w = '.hr-widget[data-hr-tab="memory"]'
        if pg.evaluate(f"() => document.querySelector('{w}').classList.contains('hr-w-collapsed')"):
            pg.locator(w + " .hr-wb-collapse").click(timeout=3000)
            assert not pg.evaluate(f"() => document.querySelector('{w}').classList.contains('hr-w-collapsed')"), "▲ widget'ı açmadı"
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


@tarayici_gerek
def test_kayitli_sohbet_secimi_ezilmez(tarayici):
    pg = _sayfa(tarayici, (1280, 800), on_kayit="localStorage.setItem('yukiViewMode_v1','chat')")
    try:
        assert "sohbet-mode" in pg.evaluate("() => document.body.className")
        assert "hud-ring-mode" not in pg.evaluate("() => document.body.className")
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


@tarayici_gerek
@pytest.mark.parametrize("hareket", ["reduce", "no-preference"], ids=["sabit", "animasyonlu"])
def test_telefon_cekmece_ve_tek_widget(tarayici, hareket):
    pg = _sayfa(tarayici, (390, 844), hareket=hareket)
    try:
        ekranda = "() => { const r = document.getElementById('hr-side').getBoundingClientRect(); return r.top < innerHeight - 4 && getComputedStyle(document.getElementById('hr-side')).visibility !== 'hidden'; }"
        gorunen_w = "() => [...document.querySelectorAll('.hr-widget')].filter(w => getComputedStyle(w).display !== 'none').map(w => w.dataset.hrTab)"
        assert "hud-ring-mode" in pg.evaluate("() => document.body.className")
        assert not pg.evaluate(ekranda), "çekmece açılışta açık (halkayı/girişi örter)"
        # 11-14 tam hizala: kişisel Yuki'deki gibi açılışta kayıtlı açık widget'lardan TEK biri görünür
        # (eskiden hiçbiri). Tabaka giriş çubuğunu örtmemeli.
        acilista = pg.evaluate(gorunen_w)
        assert len(acilista) <= 1, f"açılışta birden çok widget tabakası: {acilista}"
        if acilista:
            alt0 = pg.evaluate(f"() => document.querySelector('.hr-widget[data-hr-tab=\"{acilista[0]}\"]').getBoundingClientRect().bottom")
            giris0 = pg.evaluate("() => document.getElementById('input-area').getBoundingClientRect().top")
            assert alt0 <= giris0 + 1, f"açılış tabakası giriş çubuğunu örtüyor ({alt0} > {giris0})"
        fab = pg.locator("#hr-cekmece-fab")
        assert fab.is_visible()
        kutu = fab.bounding_box()
        assert min(kutu["width"], kutu["height"]) >= 43.5, "▴ düğmesi 44px altında"
        fab.click()
        pg.wait_for_timeout(400)
        assert pg.evaluate(ekranda), "▴ çekmeceyi açmadı"
        assert fab.get_attribute("aria-expanded") == "true"
        # açılışta zaten açık olan (kayıtlı) widget'a değil, kapalı birine basılır: açık olanın düğmesi
        # onu kapatır (masaüstüyle aynı) — tam hizala sonrası açılışta HAFIZA açık geliyor.
        pg.locator('#hr-side .hr-tab-btn[data-tab="modes"]').click()
        pg.wait_for_timeout(500)
        assert not pg.evaluate("() => document.body.classList.contains('hr-cekmece-acik')"), "seçince çekmece kapanmadı"
        assert pg.evaluate(gorunen_w) == ["modes"]
        alt = pg.evaluate("() => document.querySelector('.hr-widget[data-hr-tab=\"modes\"]').getBoundingClientRect().bottom")
        giris = pg.evaluate("() => document.getElementById('input-area').getBoundingClientRect().top")
        assert alt <= giris + 1, f"MODLAR tabakası giriş çubuğunu örtüyor ({alt} > {giris})"
        # ikinci widget açılınca ilki görsel olarak çekilir (aynı anda tek tabaka)
        fab.click(); pg.wait_for_timeout(400)
        pg.locator('#hr-side .hr-tab-btn[data-tab="alarms"]').click(); pg.wait_for_timeout(500)
        assert pg.evaluate(gorunen_w) == ["alarms"]
        # Esc kapatır
        fab.click(); pg.wait_for_timeout(300)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
        assert not pg.evaluate("() => document.body.classList.contains('hr-cekmece-acik')")
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))

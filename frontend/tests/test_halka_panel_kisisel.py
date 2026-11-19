"""HALKA PANEL'i kişisel Yuki'deki gibi — tarayıcı testleri (2026-11-14).

Çalıştırma (sunucu gerekli):
    YUKI_URL=http://127.0.0.1:8151 backend/venv/bin/python -m pytest frontend/tests/test_halka_panel_kisisel.py -q

Ölçülenler:
  1. PANEL 8 widget, kişisel sıra ve gruplar: ZİHİN HAFIZA·MODLAR·GÖZ · İŞ ALARM·GÖREV ·
     SİSTEM AKIŞ·HQ·SİTELER. KRİPTO yok (kişisel finans). HALKA TEMASI kartı ve dar ekran tema hapı yok.
  2. `window.HalkaTema`: liste() → [{key, ad}] · al() · sec(key) temayı gerçekten uygular
     (<html data-halka-tema>, localStorage, `halka:tema-degisti` olayı); geçersiz anahtar false, değişiklik yok;
     seçim yeniden yüklemede kalır.
  3. GÖZ: kurulum bayrağı kapalıyken (/api/gorus/durum 404) yalnız dürüst satır — kamera kartı, düğme yok.
     Bayrak açıkken gövde açık kaynağın kendi YukiGorusPanel kamera kartı (rıza "Aç" düğmesi); ses kimliği kartı GÖZ'e girmez.
  4. SİTELER: HalkaSiteler listesini gösterir; satır sistem tarayıcısında açar (window.open), ✕ siler,
     boş liste dürüst boş metin.
  5. 390 ve 1280'de JS istisnası (pageerror) 0. Normal (animasyonlu) mod.
/api/gorus/* Playwright'la taklit edilir (sunucu ayarı değişmez, kamera açılmaz).
"""
from __future__ import annotations

import json
import os

import pytest

from perdesiz import PERDESIZ_JS   # açılış sinematiği + ilk kurulum perdesi tıklamayı keser

BASE = os.getenv("YUKI_URL", "http://127.0.0.1:8001")
SITE_ANAHTAR = "yuki_halka_siteler_v1"


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


def _gorus_taklit(ctx, bayrak: bool):
    """Bayrak kapalı = sunucunun gerçek davranışı (404). Açık = rıza verilmemiş durum."""
    def gorus(route):
        if not bayrak:
            route.fulfill(status=404, content_type="application/json", body='{"detail":"Not Found"}')
        else:
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"riza": {"verildi": False}, "model": {"hazir": True}}))

    def ses(route):
        if not bayrak:
            route.fulfill(status=404, content_type="application/json", body='{"detail":"Not Found"}')
        else:
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"riza": {"verildi": False}, "kayit": {"var": False}, "model": {"var": True}}))
    ctx.route("**/api/gorus/durum*", gorus)
    ctx.route("**/api/ses-kimlik/durum*", ses)


def _halka(br, vp=(1280, 800), siteler="[]", gorus=False):
    ctx = br.new_context(viewport={"width": vp[0], "height": vp[1]}, service_workers="block")
    _gorus_taklit(ctx, gorus)
    pg = ctx.new_page()
    pg.add_init_script(PERDESIZ_JS)
    pg._hatalar = []
    pg.on("pageerror", lambda e: pg._hatalar.append(str(e)))
    pg.add_init_script(
        "if (!sessionStorage.getItem('_k')) { localStorage.setItem('yukiViewMode','hud-ring'); "
        "localStorage.setItem('%s', %s); sessionStorage.setItem('_k','1'); }"
        "window.__acilan = []; window.open = function (u, h, o) { window.__acilan.push([String(u), h, o]); return null; };"
        % (SITE_ANAHTAR, json.dumps(siteler)))
    pg.goto(BASE + "/ui/", wait_until="networkidle")
    if "hud-ring-mode" not in pg.evaluate("() => document.body.className"):
        pg.evaluate("() => window.setViewMode('hud-ring')")
    pg.wait_for_selector("#hr-side .hr-tabs-bar", state="attached")
    pg.wait_for_selector(".hr-widget[data-hr-tab]", state="attached")
    return pg


def _widget_ac(pg, wid):
    """PANEL düğmesine bas; widget yalnız başlığıyla açıldıysa (çekirdeği örtmesin diye) gövdesini aç."""
    pg.click(f'#hr-side .hr-tab-btn[data-tab="{wid}"]')
    w = pg.locator(f'.hr-widget[data-hr-tab="{wid}"]')
    pg.wait_for_function(f"""() => !document.querySelector('.hr-widget[data-hr-tab="{wid}"]').classList.contains('hr-w-hidden')""")
    if "hr-w-collapsed" in (w.get_attribute("class") or ""):
        w.locator(".hr-wb-collapse").click()
    pg.wait_for_timeout(150)
    return w


PANEL = """() => {
  const o = [];
  for (const el of document.querySelectorAll('#hr-side .hr-tabs-bar > *')) {
    if (el.classList.contains('hr-grup')) o.push([el.querySelector('.hr-grup-ad').dataset.hrGrup, []]);
    else if (el.classList.contains('hr-tab-btn') && o.length) o[o.length - 1][1].push(el.dataset.tab);
  }
  return o;
}"""
BEKLENEN = [["zihin", ["memory", "modes", "gaze"]],
            ["is", ["alarms", "todos"]],
            ["sistem", ["chat", "hq", "sites"]]]


@pytest.mark.parametrize("vp", [(390, 844), (1280, 800)], ids=["390", "1280"])
def test_panel_kisisel_sira_kripto_yok_tema_karti_yok(tarayici, vp):
    pg = _halka(tarayici, vp)
    try:
        assert pg.evaluate(PANEL) == BEKLENEN
        assert pg.locator('[data-tab="kripto"], .hr-widget[data-hr-tab="kripto"]').count() == 0, "KRİPTO oss'a girmez"
        assert pg.locator("#hr-side .hr-tema, #hr-side .hr-tema-btn, #hr-tema-hap, .hr-tema-sec").count() == 0, \
            "HALKA TEMASI kartı/hapı hâlâ var"
        sayilar = pg.evaluate("() => [...document.querySelectorAll('#hr-side .hr-grup-sayi')].map(e => +e.textContent)")
        assert sayilar == [3, 2, 3]
        assert pg.locator(".hr-widget[data-hr-tab]").count() == 8
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


def test_halka_tema_api(tarayici):
    pg = _halka(tarayici)
    try:
        liste = pg.evaluate("() => window.HalkaTema.liste()")
        assert [t["key"] for t in liste] == ["kara-mana-goz", "buz"]
        assert all(t["ad"] and not t["ad"].startswith("hudring.") for t in liste), liste
        bas = pg.evaluate("() => window.HalkaTema.al()")
        assert bas == pg.evaluate("() => document.documentElement.getAttribute('data-halka-tema')")
        hedef = "buz" if bas != "buz" else "kara-mana-goz"
        sonuc = pg.evaluate("""(h) => {
          window.__olay = null;
          document.addEventListener('halka:tema-degisti', e => { window.__olay = e.detail.key; }, { once: true });
          const r = window.HalkaTema.sec(h);
          return { r, al: window.HalkaTema.al(), attr: document.documentElement.getAttribute('data-halka-tema'),
                   ls: localStorage.getItem('yuki_halka_tema_v1'), olay: window.__olay };
        }""", hedef)
        assert sonuc == {"r": True, "al": hedef, "attr": hedef, "ls": hedef, "olay": hedef}, sonuc
        # kara mana seçilince süs katmanı kurulur (kartın yaptığı her şey: senkron dahil)
        if hedef == "kara-mana-goz":
            pg.wait_for_selector("link[data-halka-tema-css='kara-mana-goz']", state="attached")
        gecersiz = pg.evaluate("() => [window.HalkaTema.sec('yok-boyle'), window.HalkaTema.al()]")
        assert gecersiz == [False, hedef]
        pg.reload(wait_until="networkidle")
        pg.wait_for_selector("#hr-side .hr-tabs-bar", state="attached")
        assert pg.evaluate("() => window.HalkaTema.al()") == hedef
        assert pg.evaluate("() => document.documentElement.getAttribute('data-halka-tema')") == hedef
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


def test_goz_bayrak_kapali_durust_satir(tarayici):
    pg = _halka(tarayici, gorus=False)
    try:
        w = _widget_ac(pg, "gaze")
        pg.wait_for_selector('#hr-goz-body .hr-goz-kapali[data-goz="kapali"]')
        govde = w.locator("#hr-goz-body")
        assert govde.locator(".gp-kart, button, video").count() == 0, "bayrak kapalıyken kamera arayüzü vaat ediliyor"
        metin = govde.inner_text().strip()
        assert metin, "GÖZ gövdesi boş"
        # sözlükte anahtar varsa metin onun çevirisi olmalı (anahtar ana oturumda eklenir)
        tr = pg.evaluate("() => window.YukiDil ? window.YukiDil.t('hudring.goz.kapali') : ''")
        assert tr in metin, (tr, metin)
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


def test_goz_bayrak_acik_kendi_paneli(tarayici):
    pg = _halka(tarayici, gorus=True)
    try:
        w = _widget_ac(pg, "gaze")
        pg.wait_for_selector("#hr-goz-body .hr-goz-panel .gp-kart")
        assert w.locator(".gp-kart").count() == 1, "GÖZ'e ses kimliği kartı da girdi"
        assert w.locator(".gp-kart .gp-ac").count() == 1, "rıza 'Aç' düğmesi yok"
        assert w.locator(".hr-goz-kapali").count() == 0
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


def test_siteler_listeyi_gosterir_acar_siler(tarayici):
    siteler = json.dumps([
        {"id": "s1", "ad": "Vikipedi", "url": "https://tr.wikipedia.org/", "host": "tr.wikipedia.org"},
        {"id": "s2", "ad": "Örnek", "url": "https://example.com/", "host": "example.com"},
    ])
    pg = _halka(tarayici, siteler=siteler)
    try:
        assert pg.evaluate("() => window.HalkaSiteler.liste().length") == 2, "depo tohumu okunmadı"
        w = _widget_ac(pg, "sites")
        pg.wait_for_selector("#hr-sites-body .hr-site-item")
        adlar = pg.evaluate("() => [...document.querySelectorAll('#hr-sites-body .hr-site-item .hr-si-txt b')].map(b => b.textContent)")
        assert adlar == ["Vikipedi", "Örnek"]
        assert "2/" in w.locator(".hr-site-serit").inner_text()
        w.locator('.hr-si-txt[data-id="s2"]').click()
        acilan = pg.evaluate("() => window.__acilan")
        assert acilan and acilan[-1][0] == "https://example.com/", acilan
        w.locator('.hr-si-del[data-id="s1"]').click()
        pg.wait_for_function("() => document.querySelectorAll('#hr-sites-body .hr-site-item').length === 1")
        assert pg.evaluate("() => window.HalkaSiteler.liste().map(s => s.id)") == ["s2"]
        w.locator('.hr-si-del[data-id="s2"]').click()
        pg.wait_for_selector("#hr-sites-body .hr-site-bos")
        assert w.locator(".hr-site-ekle").count() == 1
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()

"""DOSYA sekmesi: "Yuki'ye gönder" + güvenli dosya işlemleri (çöpe at · taşı · geri al) — tarayıcıda.

Sunucu: `frontend/tests/dosya_sinav_sunucu.py` (ikinci port, geçici veri, sahte sohbet soketi).
    python frontend/tests/dosya_sinav_sunucu.py 18831 &
    YUKI_URL=http://127.0.0.1:18831 python -m pytest frontend/tests/test_dosya_gonder_guvenli.py -q

Ölçülenler (390 ve 1280, JS istisnası 0):
  1. Gönder: menüden belge → bilet → medya yükleme → çıkarılan metin TEK sohbet mesajında soketten gider.
  2. Gönder: görsel → `/api/media/send-to-chat` çağrılır; iki belge → tek mesaj, ikisinin içeriği.
  3. Gönder kapısı: başka pencereden (iframe dışı) gelen aynı mesaj hiçbir şey yüklemez.
  4. Güvenli dosya KAPALI (varsayılan): menüde çöpe at / taşı yok, kilit "salt okunur" der.
  5. Açık: çöpe at → onay penceresi → Vazgeç hiçbir şey yapmaz; onay → listeden düşer → "Geri al" geri getirir.
  6. Açık: taşımak için seç → hedef klasör → Buraya taşı → onay → taşındı; Son işlemler'den geri al.
"""
from __future__ import annotations

import os
import urllib.request
from pathlib import Path

import pytest

BASE = os.getenv("YUKI_URL", "http://127.0.0.1:18831")
GENISLIKLER = [(390, 844), (1280, 800)]
EKRAN = os.getenv("EKRAN_DIZINI")          # verilirse ekran görüntüleri buraya


def _sunucu_var() -> bool:
    try:
        return urllib.request.urlopen(BASE + "/api/guvenli-dosya/durum", timeout=3).status == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _sunucu_var(), reason=f"sınav sunucusu yok: {BASE}")


@pytest.fixture(scope="module")
def tarayici():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture(params=GENISLIKLER, ids=lambda v: f"{v[0]}px")
def sayfa(request, tarayici):
    req = urllib.request.Request(BASE + "/sinav/sifirla", method="POST")
    urllib.request.urlopen(req, timeout=5)
    vp = request.param
    ctx = tarayici.new_context(viewport={"width": vp[0], "height": vp[1]}, service_workers="block")
    pg = ctx.new_page()
    pg._hatalar = []
    pg._istekler = []
    pg.on("pageerror", lambda e: pg._hatalar.append(str(e)))
    pg.on("request", lambda r: pg._istekler.append((r.method, r.url)))
    pg.goto(BASE + "/sinav/kabuk.html")
    fr = pg.frame_locator("#dosya-iframe")
    fr.locator(".dy-oge").first.wait_for()
    pg._fr = fr
    pg._gen = vp[0]
    yield pg
    assert pg._hatalar == [], pg._hatalar
    ctx.close()


def _oge(pg, ad):
    return pg._fr.locator(".dy-oge", has_text=ad).first


def _menu(pg, ad, satir):
    _oge(pg, ad).click(button="right")
    m = pg._fr.locator(".dy-menu-oge", has_text=satir)
    m.wait_for()
    m.click()


def _ekran(pg, ad):
    if EKRAN:
        Path(EKRAN).mkdir(parents=True, exist_ok=True)
        pg.wait_for_timeout(350)                 # normal (animasyonlu) mod: giriş animasyonu bitsin
        pg.screenshot(path=str(Path(EKRAN) / f"{ad}-{pg._gen}.png"))


def _sinav(pg):
    return pg.evaluate("window._sinav")


# ── Gönder ──────────────────────────────────────────────────────── #

def test_belge_gonder_tek_mesaj(sayfa):
    pg = sayfa
    _menu(pg, "not.txt", "Yuki'ye gönder")
    pg.wait_for_function("window._sinav.gonderilen.length === 1")
    s = _sinav(pg)
    assert "merhaba dunya — sınav metni" in s["gonderilen"][0]["message"]
    assert s["gonderilen"][0]["type"] == "text"
    assert s["sekme"] == ["chat"]
    assert any(m == "POST" and u.endswith("/api/media/upload") for m, u in pg._istekler)


def test_onizlemeden_gonder_dugmesi(sayfa):
    pg = sayfa
    _oge(pg, "rapor.md").click()
    btn = pg._fr.locator("#dy-on-gonder")
    if pg._gen < 1100:                        # telefonda önizleme alt sayfası Enter/çift tıkla açılır
        _oge(pg, "rapor.md").press("Enter")
    btn.wait_for(state="visible")
    _ekran(pg, "gonder-onizleme")
    btn.click()
    pg.wait_for_function("window._sinav.gonderilen.length === 1")
    assert "Haftalık rapor" in _sinav(pg)["gonderilen"][0]["message"]


def test_iki_belge_tek_mesaj_gorsel_ayri(sayfa):
    pg = sayfa
    _oge(pg, "not.txt").click()
    _oge(pg, "rapor.md").click(modifiers=["Control"])
    _oge(pg, "resim.png").click(modifiers=["Control"])
    _oge(pg, "resim.png").click(button="right")
    pg._fr.locator(".dy-menu-oge", has_text="Yuki'ye gönder").click()
    pg.wait_for_function("window._sinav.gonderilen.length === 1")
    pg.wait_for_timeout(300)
    s = _sinav(pg)
    assert len(s["gonderilen"]) == 1
    msg = s["gonderilen"][0]["message"]
    assert "merhaba dunya" in msg and "Haftalık rapor" in msg
    assert sum(1 for m, u in pg._istekler if m == "POST" and "/api/media/send-to-chat/" in u) == 1


def test_iframe_disindan_gelen_mesaj_yok_sayilir(sayfa):
    pg = sayfa
    kid = pg.evaluate("""async () => {
        const r = await fetch('/api/dosya/git', {method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({yol: (await (await fetch('/api/dosya/kokler')).json()).kokler[0].yol + '/not.txt'})});
        return (await r.json()).id; }""")
    pg.evaluate("""(kid) => window.postMessage({tur:'yuki-dosya-gonder', ogeler:[{id: kid, ad:'not.txt', boyut: 10}]},
                  location.origin)""", kid)
    pg.wait_for_timeout(600)
    assert _sinav(pg)["gonderilen"] == []
    assert not any("/api/media/upload" in u for _, u in pg._istekler)


# ── Güvenli dosya ───────────────────────────────────────────────── #

def _ac(pg):
    pg._fr.locator(".gd-kilit").click()
    pg._fr.locator("#gd-anahtar").fill("sinav-anahtari")
    _ekran(pg, "guvenli-ac")
    pg._fr.locator(".gd-eylem button", has_text="Düzenlemeyi aç").click()
    pg._fr.locator(".gd-kilit.gd-acik").wait_for()


def test_kapaliyken_yazma_satiri_yok(sayfa):
    pg = sayfa
    kilit = pg._fr.locator(".gd-kilit")
    kilit.wait_for()
    assert "Salt okunur" in kilit.get_attribute("title")
    _oge(pg, "not.txt").click(button="right")
    pg._fr.locator(".dy-menu-oge").first.wait_for()
    metin = pg._fr.locator("#dy-menu").inner_text()
    assert "Çöpe at" not in metin and "Taşı" not in metin
    pg.keyboard.press("Escape")
    _oge(pg, "not.txt").click()
    pg.keyboard.press("Delete")
    pg.wait_for_timeout(300)
    assert pg._fr.locator(".gd-pencere").count() == 0
    assert not any("/api/guvenli-dosya/hazirla" in u for _, u in pg._istekler)   # istek bile gitmez


def test_cope_at_onay_ve_geri_al(sayfa):
    pg = sayfa
    _ac(pg)
    _menu(pg, "not.txt", "Çöpe at")
    pen = pg._fr.locator(".gd-pencere")
    pen.wait_for()
    assert "not.txt" in pen.inner_text() and "Kalıcı silinmez" in pen.inner_text()
    pk = pen.bounding_box()                      # pencere ortalı ve tamamı ekranda (akışa düşmedi)
    assert pk["y"] > 0 and pk["y"] + pk["height"] <= pg.viewport_size["height"]
    assert abs((pk["y"] + pk["height"] / 2) - pg.viewport_size["height"] / 2) < 60, pk
    _ekran(pg, "guvenli-onay")
    pg._fr.locator(".gd-eylem button", has_text="Vazgeç").click()
    assert _oge(pg, "not.txt").is_visible()                      # vazgeç → hiçbir şey olmadı
    _menu(pg, "not.txt", "Çöpe at")
    pg._fr.locator(".gd-eylem .gd-tehlike").click()
    pg._fr.locator(".dy-oge", has_text="not.txt").wait_for(state="detached")
    geri = pg._fr.locator("#dy-duyuru-eylem", has_text="Geri al")
    geri.wait_for()
    _ekran(pg, "guvenli-geri-al")
    geri.click()
    _oge(pg, "not.txt").wait_for()


def test_tasi_ve_son_islemlerden_geri_al(sayfa):
    pg = sayfa
    _ac(pg)
    _menu(pg, "rapor.md", "Taşımak için seç")
    serit = pg._fr.locator(".gd-serit")
    serit.wait_for()
    kutu = serit.bounding_box()                  # sabit konum: ekranın alt yarısında, tamamı görünür
    assert kutu["y"] > 844 / 2 * (pg._gen < 1100) and kutu["y"] + kutu["height"] <= pg.viewport_size["height"], kutu
    _oge(pg, "alt").dblclick()
    _oge(pg, "eski.txt").wait_for()
    _ekran(pg, "guvenli-serit")
    serit.locator("button", has_text="Buraya taşı").click()
    pen = pg._fr.locator(".gd-pencere")
    pen.wait_for()
    assert "rapor.md" in pen.inner_text()
    pg._fr.locator(".gd-eylem .gd-ana", has_text="Taşı").click()
    _oge(pg, "rapor.md").wait_for()                              # alt/ içinde göründü
    assert serit.is_hidden()
    pg._fr.locator(".gd-kilit").click()
    pg._fr.locator(".gd-gunluk li").first.wait_for()
    _ekran(pg, "guvenli-gunluk")
    pg._fr.locator(".gd-gunluk li").first.locator("button", has_text="Geri al").click()
    pg._fr.locator(".gd-gunluk .gd-rozet").first.wait_for()
    pg._fr.locator(".gd-eylem button", has_text="Kapat").last.click()
    pg._fr.locator(".dy-oge", has_text="rapor.md").wait_for(state="detached")


# ── Galeri fişi ─────────────────────────────────────────────────── #

@pytest.fixture(params=GENISLIKLER, ids=lambda v: f"galeri-{v[0]}px")
def galeri(request, tarayici):
    urllib.request.urlopen(urllib.request.Request(BASE + "/sinav/sifirla", method="POST"), timeout=5)
    vp = request.param
    ctx = tarayici.new_context(viewport={"width": vp[0], "height": vp[1]}, service_workers="block")
    pg = ctx.new_page()
    pg._hatalar = []
    pg.on("pageerror", lambda e: pg._hatalar.append(str(e)))
    pg._gen = vp[0]
    pg._istekler = []
    pg.on("request", lambda r: pg._istekler.append((r.method, r.url)))
    yield pg
    assert pg._hatalar == [], pg._hatalar
    ctx.close()


def _galeri_ac(pg, acik):
    if acik:
        r = pg.request.put(BASE + "/api/guvenli-dosya/ayar", data={"acik": True, "anahtar": "sinav-anahtari"})
        assert r.ok, r.text()
    pg.goto(BASE + "/ui/galeri.html")
    pg.locator(".gl-kart").first.wait_for()


def _var(pg, yol):
    return pg.request.get(BASE + "/sinav/var?yol=" + yol).json()["var"]


def _fis_ac(pg, ad):
    pg.locator(".gl-kart").first.wait_for()
    kartlar = pg.locator(".gl-kart")
    for i in range(kartlar.count()):
        kartlar.nth(i).click()
        pg.locator("#gl-buyuk").wait_for()
        if pg.locator("#gl-fis-ad").inner_text() == ad:
            return
    raise AssertionError(f"kart yok: {ad}")


def test_galeri_kapaliyken_dugme_yok(galeri):
    pg = galeri
    _galeri_ac(pg, False)
    _fis_ac(pg, "deniz.png")
    pg.wait_for_timeout(300)
    assert pg.locator(".gg-dugme").count() == 2 and pg.locator(".gg-dugme:visible").count() == 0
    pg.keyboard.press("Delete")
    pg.wait_for_timeout(300)
    assert pg.locator(".gd-pencere").count() == 0 and _var(pg, "deniz.png")
    assert not any("/api/guvenli-dosya/hazirla" in u for _, u in pg._istekler)   # istek bile gitmez
    assert "Salt okunur" in pg.locator(".gl-salt").first.text_content()


def test_galeri_cope_at_ve_geri_al(galeri):
    pg = galeri
    _galeri_ac(pg, True)
    _fis_ac(pg, "deniz.png")
    assert "Düzenleme açık" in pg.locator(".gl-salt").first.text_content()
    _ekran(pg, "galeri-fis")
    pg.locator(".gg-cop-dugme").click()
    pg.locator(".gd-pencere").wait_for()
    assert "deniz.png" in pg.locator(".gd-pencere").inner_text()
    _ekran(pg, "galeri-onay")
    pg.locator(".gd-eylem .gd-tehlike").click()
    geri = pg.locator(".gd-duyuru button", has_text="Geri al")
    geri.wait_for()
    assert not _var(pg, "deniz.png")
    _ekran(pg, "galeri-geri-al")
    geri.click()
    pg.wait_for_function("document.querySelector('.gd-duyuru span').textContent.includes('eski yerine')")
    assert _var(pg, "deniz.png")


def test_galeri_tasi(galeri):
    pg = galeri
    _galeri_ac(pg, True)
    _fis_ac(pg, "deniz.png")
    pg.locator(".gg-tasi-dugme").click()
    pg.locator(".gd-sec button", has_text="aile").click()
    _ekran(pg, "galeri-tasi")
    pg.locator(".gd-eylem button", has_text="Devam").click()
    pg.locator(".gd-pencere h2", has_text="taşınsın mı").wait_for()
    pg.locator(".gd-eylem .gd-ana", has_text="Taşı").click()
    pg.locator(".gd-duyuru button", has_text="Geri al").wait_for()
    assert _var(pg, "aile/deniz.png") and not _var(pg, "deniz.png")


# ── Kip şeridi: kip notu + "Gönder" düğmesi (2026-11-13 arayüz turu) ── #
# 7. Kip notu görünür; uç + anahtar varken nasıl açılacağını söyler ("rozetten"); düzenleme açıkken gizli.
# 8. Gönder açılışta kapalı, dosya seçilince açık, klasörde kapalı; menü (Yuki'ye gönder · İndir) → TEK mesaj.
# 9. Telefonda not şeridin ilk satırı, tam genişlik.

def test_kip_notu_gorunur_ve_anahtarli_kurulumda_yol_gosterir(sayfa):
    pg = sayfa
    not_ = pg._fr.locator("#dy-kapi-not")
    not_.wait_for(state="visible")
    pg.wait_for_timeout(400)                       # dosya-guvenli.js /durum yanıtı
    metin = not_.inner_text()
    assert metin.startswith("Salt okunur"), metin
    assert "rozetten" in metin, metin              # sınav sunucusunda uç + anahtar var


def test_gonder_acilista_kapali_dosya_secince_acik(sayfa):
    pg = sayfa
    btn = pg._fr.locator("#dy-gonder")
    btn.wait_for(state="visible")
    if pg._gen >= 769:                             # masada açılış imleci ilk öğede (klasör) → yine kapalı
        assert btn.is_disabled()
    _oge(pg, "not.txt").click()
    pg.wait_for_timeout(150)
    assert btn.is_enabled()
    assert "not.txt" in (btn.get_attribute("title") or "")


def test_klasor_seciliyken_gonder_kapali(sayfa):
    pg = sayfa
    _oge(pg, "not.txt").click()
    _oge(pg, "alt").click()
    pg.wait_for_timeout(150)
    assert pg._fr.locator("#dy-gonder").is_disabled()


def test_gonder_menusu_yukiye_tek_mesaj(sayfa):
    pg = sayfa
    _oge(pg, "not.txt").click()
    pg._fr.locator("#dy-gonder").click()
    menu = pg._fr.locator(".dy-menu-oge")
    menu.first.wait_for()
    adlar = [m.strip() for m in menu.all_inner_texts()]
    assert any(a.startswith("Yuki'ye gönder") for a in adlar), adlar
    assert any(a.startswith("İndir") for a in adlar), adlar
    assert pg._fr.locator("#dy-gonder").get_attribute("aria-expanded") == "true"
    pg._fr.locator(".dy-menu-oge", has_text="Yuki'ye gönder").click()
    pg.wait_for_function("window._sinav.gonderilen.length === 1")
    s = pg.evaluate("window._sinav")
    assert "merhaba dunya — sınav metni" in s["gonderilen"][0]["message"]


def test_duzenleme_acikken_not_gizli(sayfa):
    pg = sayfa
    pg._fr.locator("#dy-kip-rozet").click()
    pg._fr.locator("#gd-anahtar").fill("sinav-anahtari")
    pg._fr.locator("button", has_text="Düzenlemeyi aç").click()
    pg._fr.locator("#dy-kip", has_text="Düzenleme açık").wait_for()
    assert pg._fr.locator("#dy-kapi-not").is_hidden()


def test_telefonda_not_ilk_satir(sayfa):
    pg = sayfa
    if pg._gen > 768:
        pytest.skip("yalnız telefon")
    n = pg._fr.locator("#dy-kapi-not").bounding_box()
    k = pg._fr.locator("#dy-kirinti").bounding_box()
    assert n["y"] < k["y"], (n, k)
    assert n["width"] > pg._gen * 0.8, n

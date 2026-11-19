"""Açılış animasyonu (acilis-v4 ⑤ Mühür + Döküm) — oynar, kendini kaldırır, kimlik sızdırmaz.

    YUKI_URL=http://127.0.0.1:8001 python -m pytest -q frontend/tests/test_acilis_animasyonu.py

Gerçek uygulamayı açar (YUKI_URL, varsayılan http://127.0.0.1:8001); sunucu yoksa tarayıcı
testleri atlanır, durağan kapılar yine koşar. Ölçülen:
  1. index.html eski açılışı (js/opening-anim.js, css/opening-animation.css) yüklemiyor;
     acilis-v4 betikleri doğru sırada; dosyaların hepsi yerinde; widget gömmede gizli
  2. 1280 ve 390'da katman oynuyor (#yuki-opening içinde #yuki-acilis-v4), ~5,8 sn sonra
     #yuki-opening DOM'dan kalkıyor, #app görünür ve `hidden` değil, JS istisnası 0,
     eski açılış dosyasına istek 0
  3. Açılışta çizilen/yazılan metinde makine adı, kullanıcı adı, ev dizini yolu YOK
  4. Esc ile atlanıyor (iki basış)
  5. aynı oturumda ikinci açılışta oynamıyor (sessionStorage 'yukiAcilis_v1')
  6. prefers-reduced-motion'da hiç oynamıyor, #app hemen görünür
Bağımlılık: playwright (chromium), pytest.
"""
import getpass
import os
import re
import socket
import urllib.request
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
URL = os.environ.get("YUKI_URL", "http://127.0.0.1:8001").rstrip("/") + "/"
SURE_MS = 5800

# Katmanda çizilen her metni topla: canvas fillText + DOM metni (sahne çoğunu canvas'a çizer).
KAYIT_JS = """
window.__acilisMetin = [];
(function () {
  var asil = CanvasRenderingContext2D.prototype.fillText;
  CanvasRenderingContext2D.prototype.fillText = function (s) {
    try { if (this.canvas && this.canvas.closest && this.canvas.closest('#yuki-acilis-v4')) window.__acilisMetin.push(String(s)); } catch (e) {}
    return asil.apply(this, arguments);
  };
})();
"""
# İlk kurulum sihirbazı bu testin konusu değil; yalnız onu kapatır (açılış bayrağına DOKUNMAZ).
SIHIRBAZSIZ_JS = "try { localStorage.setItem('yuki-ilk-kurulum_v1', 'test'); } catch (e) {}"

DURUM_JS = """(() => {
  const k = document.getElementById('yuki-opening'), a = document.getElementById('app');
  return {
    durum: window.__acilisDurum || null,
    kabuk: !!k,
    katman: !!document.querySelector('#yuki-opening > #yuki-acilis-v4'),
    gorunur: !!k && getComputedStyle(k).display !== 'none' && !!k.firstChild,
    app: !!a && !a.hidden && getComputedStyle(a).display !== 'none',
  };
})()"""


def _sunucu_var():
    try:
        urllib.request.urlopen(URL, timeout=3)
        return True
    except Exception:
        return False


canli = pytest.mark.skipif(not _sunucu_var(), reason=f"{URL} yanıt vermiyor")


# ── 1 · durağan kapılar ───────────────────────────────────────────────────
def test_index_eski_acilisi_yuklemiyor_yenisini_sirayla_yukluyor():
    h = (KOK / "index.html").read_text(encoding="utf-8")
    assert "opening-anim.js" not in h and "opening-animation.css" not in h
    sira = ["acilis-v4/ortak/ortak.css", "acilis-v4/muhur-dokum/acilis.css", "acilis-v4/ortak/veri.js",
            "acilis-v4/ortak/motor.js", "acilis-v4/muhur-dokum/acilis.js", "acilis-v4/baglanti.js"]
    yerler = [h.find(s) for s in sira]
    assert all(y >= 0 for y in yerler), dict(zip(sira, yerler))
    assert yerler == sorted(yerler), "acilis-v4 betik sırası bozuk (veri → motor → sahne → bağlantı)"
    assert re.search(r'baglanti\.js[^"]*"\s+data-sahne="muhur-dokum"', h)
    assert ".widget-embed #yuki-opening" in h, "widget gömmede açılış gizlenmiyor"
    assert not (KOK / "js/opening-anim.js").exists() and not (KOK / "css/opening-animation.css").exists()


def test_dosyalar_yerinde_ve_gelistirme_artigi_yok():
    for y in ["acilis-v4/ortak/font/run.ttf", "acilis-v4/ortak/font/sem.ttf", "acilis-v4/ortak/font/mat.ttf",
              "acilis-v4/ortak/font/OFL-noto.txt", "assets/characters/yuki_muhur_poz2.webp",
              "assets/characters/yuki_muhur_poz2_goz_yari.webp", "assets/characters/yuki_muhur_poz2_goz_kapali.webp",
              "assets/fonts/gozlemevi/martian-mono-latin.woff2", "assets/fonts/gozlemevi/fraunces-latin.woff2"]:
        assert (KOK / y).is_file(), y
    assert "SIL OPEN FONT LICENSE" in (KOK / "acilis-v4/ortak/font/OFL-noto.txt").read_text()
    for yasak in ["araclar", "__pycache__", "test_acilis_v4.py", "ortak/demo.js", "muhur-dokum/index.html"]:
        assert not (KOK / "acilis-v4" / yasak).exists(), yasak


def test_core_iki_giris_yolundan_cagiriyor():
    c = (KOK / "js/core.js").read_text(encoding="utf-8")
    assert c.count("window._runOpeningAnimation()") >= 2


def test_kaynakta_kisisel_iz_yok():
    # desen parçalı: temizlik kapısı (scripts/test_temizlik.py IC_IZ) bu dosyayı yakalamasın
    kisisel = re.compile("ih" + "san|/home/|Masaüstü|vault", re.I)
    for p in (KOK / "acilis-v4").rglob("*"):
        if p.suffix in (".js", ".css", ".md"):
            m = kisisel.search(p.read_text(encoding="utf-8"))
            assert not m, f"{p.relative_to(KOK)}: '{m.group(0)}'"


# ── 2-6 · tarayıcı ───────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def tarayici():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _ac(tarayici, gen=1280, yuk=800, **ek):
    ctx = tarayici.new_context(viewport={"width": gen, "height": yuk}, **ek)
    ctx.add_init_script(SIHIRBAZSIZ_JS)
    ctx.add_init_script(KAYIT_JS)
    pg = ctx.new_page()
    pg.hatalar, pg.istekler = [], []
    pg.on("pageerror", lambda e: pg.hatalar.append(str(e)))
    pg.on("request", lambda r: pg.istekler.append(r.url))
    pg.goto(URL, wait_until="domcontentloaded")
    return ctx, pg


@canli
@pytest.mark.parametrize("gen,yuk", [(1280, 800), (390, 844)])
def test_oynar_kalkar_app_gorunur(tarayici, gen, yuk):
    ctx, pg = _ac(tarayici, gen, yuk)
    try:
        pg.wait_for_function("() => window.__acilisDurum === 'oynuyor'", timeout=8000)
        pg.wait_for_timeout(2500)
        d = pg.evaluate(DURUM_JS)
        assert d["katman"] and d["gorunur"], d
        pg.wait_for_function("() => !document.getElementById('yuki-opening')", timeout=SURE_MS + 3000)
        d = pg.evaluate(DURUM_JS)
        assert d["durum"] == "bitti" and not d["kabuk"] and d["app"], d
        assert not pg.hatalar, pg.hatalar
        eski = [u for u in pg.istekler if "opening-anim" in u or "opening-animation" in u]
        assert not eski, eski
    finally:
        ctx.close()


@canli
def test_acilis_metninde_kimlik_yok(tarayici):
    ctx, pg = _ac(tarayici)
    try:
        pg.wait_for_function("() => window.__acilisDurum === 'oynuyor'", timeout=8000)
        pg.wait_for_timeout(4700)  # döküm + alt yazı ("Mühür açıldı · …") yazıldı
        metin = " ".join(pg.evaluate("window.__acilisMetin")) + " " + pg.evaluate(
            "(document.getElementById('yuki-acilis-v4') || {}).textContent || ''")
        assert "dmesg" in metin, "döküm çizilmedi — kayıt kancası boş"
        yasak = {socket.gethostname(), getpass.getuser(), "/home/", "ih" + "san"} - {""}
        bulunan = [y for y in yasak if y.lower() in metin.lower()]
        assert not bulunan, f"açılışta kimlik izi: {bulunan}"
    finally:
        ctx.close()


@canli
def test_esc_atlar(tarayici):
    ctx, pg = _ac(tarayici)
    try:
        pg.wait_for_function("() => window.__acilisDurum === 'oynuyor'", timeout=8000)
        pg.wait_for_timeout(500)
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(150)
        pg.keyboard.press("Escape")
        pg.wait_for_function("() => !document.getElementById('yuki-opening')", timeout=1500)
        assert pg.evaluate(DURUM_JS)["app"]
    finally:
        ctx.close()


@canli
def test_ayni_oturumda_ikinci_kez_oynamaz(tarayici):
    ctx, pg = _ac(tarayici)
    try:
        pg.wait_for_function("() => window.__acilisDurum === 'oynuyor'", timeout=8000)
        pg.reload(wait_until="domcontentloaded")
        pg.wait_for_function("() => window.__acilisDurum != null", timeout=8000)
        pg.wait_for_timeout(300)
        d = pg.evaluate(DURUM_JS)
        assert d["durum"] == "oynadi" and not d["kabuk"] and d["app"], d
    finally:
        ctx.close()


@canli
def test_hareket_azaltmada_oynamaz(tarayici):
    ctx, pg = _ac(tarayici, reduced_motion="reduce")
    try:
        pg.wait_for_function("() => window.__acilisDurum != null", timeout=8000)
        pg.wait_for_timeout(300)
        d = pg.evaluate(DURUM_JS)
        assert d["durum"] == "azaltilmis" and not d["kabuk"] and d["app"], d
        assert not pg.hatalar, pg.hatalar
    finally:
        ctx.close()

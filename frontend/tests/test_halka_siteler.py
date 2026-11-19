"""Odaklı Halka SİTELER — tarayıcı testleri (2026-10-11).

Yapı kapıları: `backend/tests/test_birebir_konsol.py` (§ 3).

Çalıştırma (sunucu gerekli — ikinci port):
    YUKI_URL=http://127.0.0.1:8021 backend/venv/bin/python -m pytest frontend/tests/test_halka_siteler.py -q

Ölçülenler:
  1. Adres kapısı: yalnız http/https; javascript:/data:/file:/kimlikli adres reddi.
  2. Elle bozulmuş depo (javascript: kayıt) halkaya ve açılışa ulaşmaz.
  3. SİTE EKLE formu (Enter) → düğüm; hatalı adres kaydedilmez; aynı site ikinci kez yok;
     7'de dolar, SİTE EKLE düğümü kalkar (halkada en çok 8 düğüm).
  4. TÜM SİTELER'den silme; yeniden yüklemede liste kalır (yerel).
  5. Açılış: window.open(https…, '_blank', 'noopener…') — iframe kurulmaz; menü kapanır.
  6. Panelde Esc yalnız paneli kapatır.
  7. 390/1280: düğüm ≥44px, form alanları ≥44px, etiketler çakışmaz, JS istisnası 0.
  8. EN arayüzde grup adı ve panel İngilizce.
Yetki: sunucunun gerçek `/api/yetki` cevabı toplama anında bir kez alınır ve sayfaya
yönlendirilir (slowapi sınırına takılmamak için). Açık kaynak sürümde SİTELER herkese açık.
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
ANAHTAR = "yuki_halka_siteler_v1"


@pytest.fixture(scope="module")
def tarayici():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _yetki_ham() -> dict:
    """Sunucunun GERÇEK entitlements cevabı — TOPLAMA anında bir kez (testler sunucuya dokunmadan önce).
    Her sayfa yüklemesi bu uca 4-5 istek atıyor; sunucuya geçirilirse slowapi'nin 100/dk sınırı
    aşılıyor → 429 → kapı (doğru biçimde) kapalıya düşüyordu. Test anında alınırsa da önceki test
    dosyaları sınırı tüketmiş oluyor (frontend/tests tam koşusunda 16× 429, ölçüldü 10-12)."""
    import json
    import time
    import urllib.error
    import urllib.request
    # 429'da bekle ve yeniden dene: aynı sunucuya hemen önce koşan başka bir test DOSYASI (ayrı pytest süreci)
    # dakikalık sınırı doldurmuş olabilir — toplama anında almak tek süreç içini çözüyor, süreçler arasını değil
    # (ölçüldü 11-04: giris/birebir/odakli ardından koşunca 13 testin 13'ü "yetki alınamadı" ile düştü).
    son = time.time() + 75
    while True:
        try:
            with urllib.request.urlopen(BASE + "/api/yetki", timeout=5) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code != 429 or time.time() > son:
                return {}
            time.sleep(min(max(int(e.headers.get("Retry-After") or 5), 1), 15))
        except Exception:
            return {}


_YETKI_HAM = _yetki_ham() if _sunucu_var() else {}


def _yetki():
    import json
    assert _YETKI_HAM, "yetki toplama anında alınamadı"

    def isle(route):
        govde = json.loads(json.dumps(_YETKI_HAM))
        route.fulfill(status=200, content_type="application/json", body=json.dumps(govde))
    return isle


def _halka(br, vp=(1280, 800), siteler="[]"):
    ctx = br.new_context(viewport={"width": vp[0], "height": vp[1]}, service_workers="block", color_scheme="dark")
    ctx.route("**/api/yetki*", _yetki())
    pg = ctx.new_page()
    pg.add_init_script(PERDESIZ_JS)
    pg._hatalar = []
    pg.on("pageerror", lambda e: pg._hatalar.append(str(e)))
    pg.add_init_script(
        "if (!sessionStorage.getItem('_k')) { localStorage.setItem('yukiViewMode','hud-ring'); "
        "localStorage.setItem('halka_menu_grup_v1','site'); localStorage.setItem('%s', %r); sessionStorage.setItem('_k','1'); }"
        "window.__acilan = []; window.open = function (u, h, o) { window.__acilan.push([String(u), h, o]); return null; };"
        % (ANAHTAR, siteler))
    pg.goto(BASE + "/ui/", wait_until="networkidle")
    if "hud-ring-mode" not in pg.evaluate("() => document.body.className"):
        pg.evaluate("() => window.setViewMode('hud-ring')")
    pg.wait_for_selector("#hr-odak")
    pg.wait_for_function("() => window._yukiPanelOk === true")
    pg.wait_for_timeout(50)
    return pg


def _ac(pg):
    r = pg.locator("#hr-ring-wrap").bounding_box()
    pg.mouse.click(r["x"] + r["width"] / 2, r["y"] + r["height"] / 2)
    pg.wait_for_function("() => document.getElementById('hr-ring-wrap').classList.contains('hr-wheel-open')")
    pg.wait_for_timeout(450)


DUGUM = "() => [...document.querySelectorAll('#hr-odak .hr-od-dugum')].map(b => [b.dataset.odTur, b.querySelector('.hr-od-etiket').textContent])"


def _ekle(pg, ad, adres):
    if not pg.locator("#hr-sp-adres").count():
        pg.locator("#hr-odak [data-sp=ekle]:visible, #hr-odak .hr-od-ekle:visible").first.click()   # panel açıkken düğümler gizli (goz 10-12 #3)
    pg.fill("#hr-sp-ad", ad)
    pg.fill("#hr-sp-adres", adres)
    pg.press("#hr-sp-adres", "Enter")
    pg.wait_for_timeout(120)
    return pg.evaluate("() => { const h = document.getElementById('hr-sp-hata'); return h ? h.textContent : null; }")


KABUL = ["youtube.com", "https://www.pinterest.com/x?y=1#z", "http://localhost:8080/panel", "localhost:3000",
         "example.com:8443/a", "HTTPS://Example.COM", "tr.wikipedia.org/wiki/İstanbul"]
RET = ["javascript:alert(1)", "JaVaScRiPt:alert(1)", " javascript:alert(1)", "java\tscript:alert(1)",
       "data:text/html,<script>alert(1)</script>", "file:///etc/passwd", "ftp://example.com", "blob:https://x.com/1",
       "vbscript:msgbox", "//evil.com", "https://user:pw@example.com", "https://", "youtube", "", "   ",
       "mailto:a@b.com", "chrome://settings", "about:blank", "https://exa mple.com"]


def test_adres_kapisi(tarayici):
    pg = _halka(tarayici)
    try:
        sonuc = pg.evaluate("(l) => l.map(a => [a, window.HalkaSiteler.dogrula(a)])", KABUL + RET)
        for adres, r in sonuc[:len(KABUL)]:
            assert r["ok"] and r["url"].split(":")[0] in ("http", "https"), (adres, r)
        for adres, r in sonuc[len(KABUL):]:
            assert not r["ok"], f"reddedilmeliydi: {adres!r} → {r}"
        # Şemalı girdi "şema" hatasıyla döner (kullanıcıya "yalnız http/https" denir), adres sanılmaz
        for a in ("javascript:alert(1)", "data:text/html,x", "mailto:a@b.com", "vbscript:msgbox", "about:blank"):
            assert pg.evaluate("(a) => window.HalkaSiteler.dogrula(a).hata", a) == "sema", a
        assert pg.evaluate("() => window.HalkaSiteler.dogrula('youtube.com').url") == "https://youtube.com/"
        assert pg.evaluate("() => window.HalkaSiteler.dogrula('x.com/' + 'a'.repeat(2100)).hata") == "uzun"
    finally:
        pg.context.close()


def test_bozuk_depo_halkaya_ve_acilisa_ulasmaz(tarayici):
    bozuk = ('[{"id":"k","ad":"Kötü","url":"javascript:alert(1)"},{"id":"d","ad":"Data","url":"data:text/html,x"},'
             '{"id":"y","ad":"<img src=x onerror=alert(1)>","url":"https://youtube.com"},{"id":"y2","ad":"Kopya","url":"https://youtube.com/"}, 5, null]')
    pg = _halka(tarayici, siteler=bozuk)
    try:
        _ac(pg)
        d = pg.evaluate(DUGUM)
        assert [x for x in d if x[0] == "site"] == [["site", "<img src=x onerror=alert(1)>"[:24]]], d   # ad 24 karakterde kesilir
        assert pg.evaluate("() => document.querySelectorAll('#hr-odak img').length") == 0, "ad HTML olarak çizildi"
        assert pg.evaluate("() => window.HalkaSiteler.ac('javascript:alert(1)')") is False
        assert pg.evaluate("() => window.__acilan") == []
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


def test_ekle_dogrula_tekrar_dolu_sil_kalici(tarayici):
    pg = _halka(tarayici)
    try:
        _ac(pg)
        assert [x[0] for x in pg.evaluate(DUGUM)] == ["ekle", "tum"], "boş halkada yalnız SİTE EKLE + TÜM SİTELER"
        hata = _ekle(pg, "Kötü", "javascript:alert(1)")
        assert hata and "http" in hata, hata
        assert pg.evaluate("() => document.getElementById('hr-sp-adres').getAttribute('aria-invalid')") == "true"
        assert pg.evaluate(f"() => localStorage.getItem('{ANAHTAR}')") == "[]", "hatalı adres kaydedildi"
        assert _ekle(pg, "YouTube", "youtube.com") is None, "geçerli adres panelde hata bıraktı"
        assert "YouTube" in pg.locator("#hr-odak .hr-od-panel").inner_text()
        assert "zaten" in _ekle(pg, "", "https://youtube.com/")
        for i in range(6):
            assert _ekle(pg, f"S{i}", f"site{i}.example.com") is None
        tur = [x[0] for x in pg.evaluate(DUGUM)]
        assert tur.count("site") == 7 and "ekle" not in tur and len(tur) == 8, f"7'de dolmalı: {tur}"
        assert pg.locator("#hr-odak [data-sp=ekle]").count() == 0
        # Tavan arayüzde değil depoda: doğrudan çağrı da 8. siteyi yazamaz
        r = pg.evaluate("() => window.HalkaSiteler.ekle('Fazla', 'fazla.example.com')")
        assert r == {"ok": False, "hata": "dolu"}, r
        assert pg.evaluate(f"() => JSON.parse(localStorage.getItem('{ANAHTAR}')).length") == 7
        # sil
        pg.locator("#hr-odak .hr-sp-sil").first.click()
        pg.wait_for_timeout(120)
        assert pg.evaluate(f"() => JSON.parse(localStorage.getItem('{ANAHTAR}')).length") == 6
        assert "YouTube" not in pg.locator("#hr-odak .hr-od-panel").inner_text()
        # yeniden yükleme — liste yerel kalır
        pg.reload(wait_until="networkidle")
        pg.wait_for_selector("#hr-odak")
        _ac(pg)
        assert [x[0] for x in pg.evaluate(DUGUM)].count("site") == 6
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


def test_acilis_sistem_tarayicisinda(tarayici):
    pg = _halka(tarayici, siteler='[{"id":"p","ad":"Pinterest","url":"https://www.pinterest.com/"}]')
    try:
        _ac(pg)
        cerceve = pg.evaluate("() => document.querySelectorAll('iframe').length")
        pg.locator("#hr-odak .hr-od-site").click()
        pg.wait_for_timeout(200)
        acilan = pg.evaluate("() => window.__acilan")
        assert acilan == [["https://www.pinterest.com/", "_blank", "noopener,noreferrer"]], acilan
        assert pg.evaluate("() => document.querySelectorAll('iframe').length") == cerceve, "site iframe'de açıldı"
        assert not pg.evaluate("() => document.getElementById('hr-ring-wrap').classList.contains('hr-wheel-open')")
        # TÜM SİTELER listesinden de açılır
        _ac(pg)
        pg.locator("#hr-odak .hr-od-tum").click()
        pg.locator("#hr-odak .hr-sp-ac").click()
        pg.wait_for_timeout(150)
        assert len(pg.evaluate("() => window.__acilan")) == 2
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


def test_panelde_esc_yalniz_paneli_kapatir(tarayici):
    pg = _halka(tarayici)
    try:
        _ac(pg)
        pg.locator("#hr-odak .hr-od-ekle").click()
        pg.wait_for_selector("#hr-sp-adres")
        pg.wait_for_function("() => document.activeElement && document.activeElement.id === 'hr-sp-adres'")
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(120)
        assert pg.locator("#hr-odak .hr-od-panel").count() == 0
        assert pg.evaluate("() => document.getElementById('hr-ring-wrap').classList.contains('hr-wheel-open')"), \
            "Esc menüyü de kapattı"
        # panel açıkken ← → grup DEĞİŞTİRMEZ (paneldeki düğmede odak varken de)
        pg.locator("#hr-odak .hr-od-tum").click()
        pg.wait_for_selector("#hr-odak .hr-od-panel")
        pg.locator("#hr-odak .hr-od-panel button").first.focus()
        pg.keyboard.press("ArrowRight")
        pg.wait_for_timeout(120)
        assert pg.locator("#hr-odak .hr-od-panel").count() == 1, "ok tuşu paneli kapattı"
        assert pg.evaluate("() => localStorage.getItem('halka_menu_grup_v1')") == "site"
        # panelin boş yerine tıklamak menüyü kapatmaz
        b = pg.locator("#hr-odak .hr-sp-baslik").bounding_box()
        pg.mouse.click(b["x"] + 4, b["y"] + b["height"] / 2)
        assert pg.evaluate("() => document.getElementById('hr-ring-wrap').classList.contains('hr-wheel-open')")
    finally:
        pg.context.close()


DOLU = "[" + ",".join('{"id":"s%d","ad":"%s","url":"https://site%d.example.com/"}' % (i, a, i)
                      for i, a in enumerate(["YouTube", "Pinterest", "YT Music", "Vikipedi", "GitHub", "Gmail", "Çok uzun bir site adı"])) + "]"
OLC = """() => {
  const d = [...document.querySelectorAll('#hr-odak .hr-od-dugum')];
  const kutu = e => e.getBoundingClientRect();
  const kes = (a, b) => !(a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top);
  const cakisma = [];
  d.forEach((x, i) => d.forEach((y, j) => {
    if (i === j) return;
    const ex = kutu(x.querySelector('.hr-od-etiket'));
    if (kes(ex, kutu(y)) || (j > i && kes(ex, kutu(y.querySelector('.hr-od-etiket'))))) cakisma.push([x.dataset.od, y.dataset.od]);
  }));
  return { min: Math.min(...d.map(x => Math.min(kutu(x).width, kutu(x).height))), cakisma,
           tasma: document.documentElement.scrollWidth - innerWidth };
}"""


@pytest.mark.parametrize("vp", [(390, 844), (1280, 800)], ids=["390", "1280"])
def test_dolu_halka_yerlesim_ve_hedef_boyutu(tarayici, vp):
    pg = _halka(tarayici, vp, siteler=DOLU)
    try:
        _ac(pg)
        r = pg.evaluate(OLC)
        assert r["min"] >= 43.5, r
        assert r["cakisma"] == [], f"etiket çakışması: {r['cakisma']}"
        assert r["tasma"] <= 0, r
        pg.locator("#hr-odak .hr-od-tum").click()
        pg.wait_for_selector("#hr-odak .hr-od-panel")
        boy = pg.evaluate("() => [...document.querySelectorAll('#hr-odak .hr-od-panel button')].map(b => Math.min(b.getBoundingClientRect().width, b.getBoundingClientRect().height)).filter(v => v > 0)")
        assert min(boy) >= 43.5, boy
        pg.locator("#hr-odak [data-sp=kapat]").click()
        pg.locator("#hr-odak .hr-sp-sil").count()
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


@pytest.mark.parametrize("vp", [(390, 844), (1280, 800)], ids=["390", "1280"])
def test_form_alanlari_44px(tarayici, vp):
    pg = _halka(tarayici, vp)
    try:
        _ac(pg)
        pg.locator("#hr-odak .hr-od-ekle").click()
        pg.wait_for_selector("#hr-sp-adres")
        boy = pg.evaluate("() => [...document.querySelectorAll('#hr-odak .hr-od-panel input, #hr-odak .hr-od-panel button')].map(e => [e.id || e.className, Math.round(e.getBoundingClientRect().height)])")
        assert all(h >= 44 for _, h in boy), boy
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


def test_ingilizce_arayuz(tarayici):
    pg = _halka(tarayici)
    try:
        pg.evaluate("() => window.YukiDil.ayarla('en')")
        pg.wait_for_timeout(400)
        _ac(pg)
        grup = pg.locator('#hr-odak .hr-od-grup[data-od-grup="site"]').inner_text()
        assert grup.strip().upper() == "SITES", grup
        pg.locator("#hr-odak .hr-od-ekle").click()
        assert "address" in pg.get_attribute("#hr-sp-adres", "placeholder")
        assert _ekle(pg, "", "ftp://x.com").startswith("Only http")
    finally:
        try:
            pg.evaluate("() => window.YukiDil.ayarla('tr')")
        finally:
            pg.context.close()


BES = ('[{"id":"a","ad":"Pinterest","url":"https://www.pinterest.com/"},{"id":"b","ad":"YouTube","url":"https://youtube.com/"},'
       '{"id":"c","ad":"YTMusic","url":"https://music.youtube.com/"},{"id":"d","ad":"Vikipedi","url":"https://tr.wikipedia.org/"},'
       '{"id":"e","ad":"GitHub","url":"https://github.com/"}]')


@pytest.mark.parametrize("vp", [(390, 844), (1280, 800)])
def test_tum_siteler_paneli_opak_kaydirma_ipucu_dugumler_cekilir(tarayici, vp):
    """goz 10-12 #1-#4: panel zemini tam opak · liste sığmıyorsa alt kenar solar, uçta kalkar ·
    panel açıkken düğümler ve grup anahtarı görünmez ve odaklanamaz (etiket kesmez, şeride binmez) ·
    kapanınca geri gelir."""
    pg = _halka(tarayici, vp, BES)
    _ac(pg)
    pg.locator("#hr-odak .hr-od-tum").click()
    pg.wait_for_selector("#hr-odak .hr-sp-liste")
    pg.wait_for_timeout(150)
    assert pg.evaluate("() => getComputedStyle(document.querySelector('#hr-odak .hr-od-panel')).backgroundColor") == "rgb(6, 8, 18)"
    d = pg.evaluate("""() => { const u = document.querySelector('#hr-odak .hr-sp-liste');
        return { tasar: u.scrollHeight > u.clientHeight + 1, cls: u.className, mask: getComputedStyle(u).maskImage || getComputedStyle(u).webkitMaskImage }; }""")
    assert d["tasar"], "5 site bu ölçüde sığmamalıydı — ölçü değişti mi?"
    assert "hr-sp-kayar" in d["cls"] and "hr-sp-son" not in d["cls"] and "gradient" in d["mask"], d
    pg.evaluate("() => { const u = document.querySelector('#hr-odak .hr-sp-liste'); u.scrollTop = u.scrollHeight; }")
    pg.wait_for_timeout(120)
    assert "hr-sp-son" in pg.evaluate("() => document.querySelector('#hr-odak .hr-sp-liste').className")
    gorunen = pg.evaluate("""() => [...document.querySelectorAll('#hr-odak .hr-od-dugum, #hr-odak .hr-od-anahtar')]
        .filter(e => getComputedStyle(e).visibility !== 'hidden' && +getComputedStyle(e).opacity > 0).length""")
    assert gorunen == 0, f"panel açıkken {gorunen} düğüm/anahtar görünüyor"
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(450)
    assert pg.locator("#hr-odak .hr-od-panel").count() == 0
    assert pg.evaluate("() => getComputedStyle(document.querySelector('#hr-odak .hr-od-tum')).visibility") == "visible"
    assert pg._hatalar == []
    pg.context.close()


# ── 9 · Kilit yok (açık kaynak) ───────────────────────────────────────────

IKI = '[{"id":"a","ad":"Pinterest","url":"https://www.pinterest.com/"},{"id":"b","ad":"YouTube","url":"https://youtube.com/"}]'


def test_siteler_kilitsiz(tarayici):
    pg = _halka(tarayici, siteler=IKI)
    try:
        pg.wait_for_function("() => window._yukiPanelOk === true")
        _ac(pg)
        assert pg.locator("#hr-odak .hr-od-grup-kilitli, #hr-odak .hr-od-grup .hr-od-kilit").count() == 0
        assert [x[0] for x in pg.evaluate(DUGUM)].count("site") == 2
    finally:
        pg.context.close()

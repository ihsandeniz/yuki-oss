"""HQ › Cihazlar — riskli eylem izinleri (dosya yazma · dosya silme · program kapatma), tarayıcı testleri.

Karar 2026-11-01: üçü kurulumdan KAPALI. Açmak erişim anahtarı (`AUTH_TOKEN`) ister; sunucu kuralı
`backend/app/services/cihaz_yetki.py` + `backend/tests/test_cihaz_yetki.py`. Bu dosya ARAYÜZÜ ölçer:
sunucunun cevabını doğru söylüyor mu, yalan "açıldı" var mı.

Çalıştırma (iki geçici sunucu, ikinci port, geçici veri — canlıya dokunmaz):
    YUKI_DATA_DIR=$(mktemp -d) AUTH_TOKEN=bl51-test-anahtar uvicorn app.main:app --port 18822   # anahtarlı
    YUKI_DATA_DIR=$(mktemp -d) AUTH_TOKEN=               uvicorn app.main:app --port 18821   # anahtarsız
    YUKI_URL=http://127.0.0.1:18822 YUKI_URL_ANAHTARSIZ=http://127.0.0.1:18821 \\
      YUKI_TEST_ANAHTAR=bl51-test-anahtar python -m pytest frontend/tests/test_cihaz_izinleri.py -q

Ölçülenler (390 ve 1280, JS istisnası 0):
  1. Üç anahtar da kapalı gelir.
  2. Aç → anahtar sorulur (odak alanda) → yanlış anahtar → 403 cümlesi, anahtar KAPALI kalır (sunucu da kapalı der).
  3. Doğru anahtar + Enter → açık (sunucu da açık der); alan boşalır.
  4. Açıkken bas → anahtar SORULMADAN kapanır.
  5. Esc formu kapatır, istek gitmez.
  6. Anahtarsız kurulum: not görünür, açma pasif.
  7. Yarış: durum "anahtar var" deyip PUT 409 dönerse 409 cümlesi görünür, anahtar kapalı kalır.
  8. Panel yatay taşmaz.
  9. Kilitli anahtar kesik çerçeveli + "Kilitli" etiketi ve kilit simgesi; form etiketi/notu 14px koyu.
"""
from __future__ import annotations

import json
import os
import urllib.request

import pytest

from perdesiz import PERDESIZ_JS

BASE = os.getenv("YUKI_URL", "http://127.0.0.1:8001")
BASE_ANAHTARSIZ = os.getenv("YUKI_URL_ANAHTARSIZ", "")
ANAHTAR = os.getenv("YUKI_TEST_ANAHTAR", "")
GENISLIKLER = [(390, 844), (1280, 800)]
EYLEMLER = ("writefile", "deletefile", "killproc")


def _sunucu_var(url: str) -> bool:
    if not url:
        return False
    try:
        return urllib.request.urlopen(url + "/health", timeout=3).status == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not (_sunucu_var(BASE) and ANAHTAR),
                                reason=f"anahtarlı sunucu yok ({BASE}) ya da YUKI_TEST_ANAHTAR boş")


def _api(base, yol, veri=None, metot="GET", token=ANAHTAR):
    istek = urllib.request.Request(base + yol, method=metot,
                                   data=json.dumps(veri).encode() if veri is not None else None,
                                   headers={"Content-Type": "application/json",
                                            **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(istek, timeout=5) as r:
        return json.loads(r.read())


def _hepsini_kapat():
    """Yalnız AÇIK olanı kapatır — PUT ucu dakikada 10 istekle sınırlı (`devices_api.izin_ayarla`)."""
    durum = _api(BASE, "/api/devices/izinler")["izinler"]
    for e in EYLEMLER:
        if durum.get(e):
            _api(BASE, "/api/devices/izinler", {"eylem": e, "acik": False}, "PUT")


@pytest.fixture(autouse=True)
def _hepsi_kapali():
    """Her test temiz başlar: üç izin sunucuda kapalı (kapatmak anahtarsız)."""
    _hepsini_kapat()
    yield
    _hepsini_kapat()


@pytest.fixture(scope="module")
def tarayici():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _sayfa(br, vp, base=BASE, token=ANAHTAR):
    ctx = br.new_context(viewport={"width": vp[0], "height": vp[1]}, service_workers="block")
    pg = ctx.new_page()
    pg._hatalar = []
    pg._istekler = []
    pg.on("pageerror", lambda e: pg._hatalar.append(str(e)))
    pg.on("request", lambda r: pg._istekler.append((r.method, r.url)) if "/api/devices/izinler" in r.url else None)
    pg.add_init_script(PERDESIZ_JS)   # açılış sinematiği + ilk kurulum sihirbazı yoldan çekilir
    pg.goto(base + "/ui/", wait_until="networkidle")
    if token:
        # anahtarlı kurulumda AUTH_TOKEN aynı zamanda giriş parolasıdır — kullanıcının yolu: giriş ekranı
        pg.locator("#auth-input").fill(token)
        pg.locator("#auth-input").press("Enter")
        pg.wait_for_function("() => document.getElementById('auth-screen').classList.contains('hidden')")
    pg.wait_for_function("() => typeof window.switchTab === 'function' && typeof window.switchHqTab === 'function'")
    # ⚠️ switchTab('hq') varsayılan paneli (ör. anahtar sihirbazı) bir an SONRA seçer ve önceki seçimi ezer →
    #    HQ yerleşene kadar bekle, sonra Cihazlar'a geç; panel görünene dek yinele.
    pg.evaluate("() => window.switchTab('hq')")
    pg.wait_for_function("() => { const h = document.getElementById('tab-hq'); return h && h.dataset.hq; }")
    for _ in range(20):
        pg.evaluate("() => { const h = document.getElementById('tab-hq'); if (h.dataset.hq !== 'cihazlar') window.switchHqTab('cihazlar'); }")
        pg.wait_for_timeout(250)
        if pg.evaluate("() => { const p = document.getElementById('hq-panel-cihazlar'); return !!p && p.offsetParent !== null && document.getElementById('tab-hq').dataset.hq === 'cihazlar'; }"):
            break
    pg.wait_for_selector("#hq-panel-cihazlar [data-cz='izin'][data-id='writefile'], #hq-panel-cihazlar [data-izin-bilinmiyor]",
                         timeout=15000)
    return pg


def _dugme(pg, e):
    return pg.locator(f"#hq-panel-cihazlar [data-cz='izin'][data-id='{e}']")


def _sunucuda(e, base=BASE, token=ANAHTAR):
    return _api(base, "/api/devices/izinler", token=token)["izinler"][e]


@pytest.mark.parametrize("vp", GENISLIKLER, ids=["390", "1280"])
def test_ac_yanlis_dogru_kapat(tarayici, vp):
    pg = _sayfa(tarayici, vp)
    try:
        for e in EYLEMLER:
            assert _dugme(pg, e).get_attribute("aria-checked") == "false", f"{e} kapalı gelmeli"
            assert _dugme(pg, e).is_enabled(), f"{e}: anahtarlı kurulumda açma etkin olmalı"

        # aç → anahtar sorulur, odak alanda, henüz istek yok
        _dugme(pg, "writefile").click()
        girdi = pg.locator("[data-cz-girdi='writefile']")
        girdi.wait_for()
        assert girdi.get_attribute("type") == "password"
        # Görsel denetim 2026-11-10: form etiketi ve notu --yazi-14 (gövde boyu), koyu (ink-1) — --yazi-12 soluk değil.
        # Token rem: kök 15px → 14 token = 13.125px; sabit "14px" değil token'ın kendisiyle kıyaslanır.
        bek = pg.evaluate("""() => { const s = document.createElement('span'); s.style.cssText = 'font-size:var(--yazi-14);color:var(--ink-1)';
            const k = document.createElement('span'); k.style.fontSize = 'var(--yazi-12)';
            // Ölçü kabı HQ'nun içi: Gözlemevi dili (koyu tema) --ink-1'i #tab-hq'da yeniden tanımlar (11-13).
            const kap = document.querySelector("[data-izin-form='writefile']") || document.body; kap.append(s, k);
            const c = getComputedStyle(s), r = [c.fontSize, c.color, getComputedStyle(k).fontSize]; s.remove(); k.remove(); return r; }""")
        assert float(bek[0][:-2]) > float(bek[2][:-2]), bek
        for sec in ("[data-izin-form='writefile'] label", "[data-izin-form='writefile'] .cz-not"):
            boy, renk = pg.locator(sec).evaluate("n => [getComputedStyle(n).fontSize, getComputedStyle(n).color]")
            assert [boy, renk] == bek[:2], f"{sec}: {boy} {renk} (beklenen {bek[:2]})"
        # anahtarlı kurulumda "Kilitli" etiketi YOK
        assert pg.locator("[data-izin-kilitli]").count() == 0
        assert pg.evaluate("() => document.activeElement && document.activeElement.getAttribute('data-cz-girdi')") == "writefile"
        assert not [m for m, _ in pg._istekler if m == "PUT"], "form açılırken istek gitmemeli"

        # yanlış anahtar → 403 cümlesi, anahtar kapalı
        girdi.fill("yanlis-anahtar")
        pg.locator("[data-cz='izin-ac'][data-id='writefile']").click()
        hata = pg.locator("#cz-izin-hata-writefile")
        hata.wait_for()
        metin = hata.inner_text()
        assert "yanlış" in metin.lower() or "wrong" in metin.lower(), metin
        assert _dugme(pg, "writefile").get_attribute("aria-checked") == "false"
        assert _sunucuda("writefile") is False
        assert pg.locator("[data-cz-girdi='writefile']").input_value() == "", "anahtar denemeden sonra silinmeli"

        # doğru anahtar + Enter → açık
        g = pg.locator("[data-cz-girdi='writefile']")
        g.fill(ANAHTAR)
        g.press("Enter")
        pg.wait_for_function("() => { const b = document.querySelector(\"[data-cz='izin'][data-id='writefile']\"); return b && b.getAttribute('aria-checked') === 'true'; }")
        assert _sunucuda("writefile") is True
        assert pg.locator("[data-cz-girdi]").count() == 0, "açılınca form kapanmalı"
        assert pg.locator("#cz-izin-hata-writefile").count() == 0
        assert ANAHTAR not in pg.content(), "anahtar DOM'da kalmamalı"
        # öbür ikisi etkilenmedi
        assert _dugme(pg, "deletefile").get_attribute("aria-checked") == "false"
        assert _dugme(pg, "killproc").get_attribute("aria-checked") == "false"

        # açıkken bas → anahtarsız kapanır
        n = len(pg._istekler)
        _dugme(pg, "writefile").click()
        pg.wait_for_function("() => document.querySelector(\"[data-cz='izin'][data-id='writefile']\").getAttribute('aria-checked') === 'false'")
        assert pg.locator("[data-cz-girdi]").count() == 0, "kapatmak anahtar sormamalı"
        assert ("PUT", BASE + "/api/devices/izinler") in pg._istekler[n:]
        assert _sunucuda("writefile") is False

        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


@pytest.mark.parametrize("vp", GENISLIKLER, ids=["390", "1280"])
def test_esc_formu_kapatir_istek_gitmez(tarayici, vp):
    pg = _sayfa(tarayici, vp)
    try:
        _dugme(pg, "killproc").click()
        g = pg.locator("[data-cz-girdi='killproc']")
        g.wait_for()
        g.fill("bir-sey")
        g.press("Escape")
        assert pg.locator("[data-cz-girdi]").count() == 0
        assert not [m for m, _ in pg._istekler if m == "PUT"]
        assert _dugme(pg, "killproc").get_attribute("aria-checked") == "false"
        # Vazgeç düğmesi de aynı
        _dugme(pg, "deletefile").click()
        pg.locator("[data-cz='izin-vazgec'][data-id='deletefile']").click()
        assert pg.locator("[data-cz-girdi]").count() == 0
        assert not [m for m, _ in pg._istekler if m == "PUT"]
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


@pytest.mark.parametrize("vp", GENISLIKLER, ids=["390", "1280"])
def test_yaris_409_cumlesi(tarayici, vp):
    """Durum okunduktan sonra AUTH_TOKEN kalkmış olabilir: PUT 409 → kurulumda anahtar yok cümlesi."""
    pg = _sayfa(tarayici, vp)
    try:
        pg.route("**/api/devices/izinler", lambda r: r.fulfill(status=409, content_type="application/json",
                                                               body='{"detail":"x"}') if r.request.method == "PUT" else r.continue_())
        _dugme(pg, "deletefile").click()
        g = pg.locator("[data-cz-girdi='deletefile']")
        g.fill(ANAHTAR)
        g.press("Enter")
        hata = pg.locator("#cz-izin-hata-deletefile")
        hata.wait_for()
        assert "AUTH_TOKEN" in hata.inner_text()
        assert _dugme(pg, "deletefile").get_attribute("aria-checked") == "false"
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


@pytest.mark.parametrize("vp", GENISLIKLER, ids=["390", "1280"])
def test_panel_tasmaz(tarayici, vp):
    pg = _sayfa(tarayici, vp)
    try:
        _dugme(pg, "writefile").click()
        pg.locator("[data-cz-girdi='writefile']").wait_for()
        tasan = pg.evaluate("""() => { const p = document.getElementById('hq-panel-cihazlar'); const s = p.getBoundingClientRect();
            return [...p.querySelectorAll('[data-izin-bas], [data-izin-bas] *, [data-izin], [data-izin] *')].filter(e => { const r = e.getBoundingClientRect();
              return r.width > 0 && (r.right > Math.min(s.right, innerWidth) + 1 || r.left < s.left - 1); })
              .map(e => e.tagName + '.' + e.className).slice(0, 5); }""")
        assert tasan == [], tasan
        # satırlar üst üste binmez (goz #2 #4): ardışık satırın üstü öncekinin altından aşağıda
        binen = pg.evaluate("""() => { const r = [...document.querySelectorAll('#hq-panel-cihazlar [data-izin-bas], #hq-panel-cihazlar [data-izin]')]
            .map(e => e.getBoundingClientRect()); const out = [];
            for (let i = 1; i < r.length; i++) if (r[i].top < r[i - 1].bottom - 0.5) out.push([i, r[i - 1].bottom, r[i].top]);
            return out; }""")
        assert binen == [], binen
        # dokunma hedefi: anahtar ve form düğmeleri ≥ 44px yükseklik (390'da)
        if vp[0] <= 400:
            for sec in ("[data-cz='izin'][data-id='writefile']", "[data-cz='izin-ac']", "[data-cz='izin-vazgec']", "[data-cz-girdi]"):
                h = pg.locator(sec).bounding_box()["height"]
                assert h >= 44, f"{sec}: {h}px"
        # anahtarlar aynı dikey çizgide (goz #3) — kapalı/açık karışıkken de: biri açılınca kaymaz
        KONUM = """() => [...document.querySelectorAll("#hq-panel-cihazlar [data-cz='izin']")].map(b => Math.round(b.getBoundingClientRect().left))"""
        sol = pg.evaluate(KONUM)
        assert max(sol) - min(sol) <= 1, sol
        g = pg.locator("[data-cz-girdi='writefile']")
        g.fill(ANAHTAR)
        g.press("Enter")
        pg.wait_for_function("() => document.querySelector(\"[data-cz='izin'][data-id='writefile']\").getAttribute('aria-checked') === 'true'")
        sol2 = pg.evaluate(KONUM)
        assert max(sol2) - min(sol2) <= 1 and sol2 == sol, (sol, sol2)
        assert pg.locator("[data-izin='writefile'] [data-izin-durum]").inner_text().strip() in ("Açık", "On")
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


@pytest.mark.skipif(not _sunucu_var(BASE_ANAHTARSIZ), reason="anahtarsız sunucu yok (YUKI_URL_ANAHTARSIZ)")
@pytest.mark.parametrize("vp", GENISLIKLER, ids=["390", "1280"])
def test_anahtarsiz_kurulumda_acma_pasif(tarayici, vp):
    pg = _sayfa(tarayici, vp, base=BASE_ANAHTARSIZ, token="")
    try:
        assert pg.locator("[data-izin-anahtarsiz]").is_visible()
        for e in EYLEMLER:
            assert _dugme(pg, e).is_disabled(), f"{e}: anahtarsız kurulumda açma pasif olmalı"
            assert _dugme(pg, e).get_attribute("aria-checked") == "false"
            # Görsel denetim 2026-11-10: kilitli anahtar kapalıdan AYRI görünür — soluk değil, kesik çerçeve;
            # yanında "Kilitli" yazısı + kilit simgesi (ayrım yalnız çizgiye bırakılmaz)
            st = _dugme(pg, e).evaluate("b => { const c = getComputedStyle(b); return [c.opacity, c.borderTopStyle, c.borderTopWidth]; }")
            assert st == ["1", "dashed", "2px"], f"{e}: kilitli anahtar stili {st}"
            et = pg.locator(f"[data-izin='{e}'] [data-izin-durum]")
            assert et.inner_text().strip() in ("Kilitli", "Locked"), et.inner_text()
            assert et.get_attribute("data-izin-kilitli") is not None
            assert et.locator("svg.cz-kilit").count() == 1 and et.locator("svg.cz-kilit").is_visible()
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()

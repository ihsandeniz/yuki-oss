"""Atölye genişletmesi (G1) — araştırma sahnesi ön yüzü + bitiş duyurusu, tarayıcı testleri.

Çalıştırma (ikinci port, geçici veri; canlıya dokunmaz). Site görevi için modelin yerine
OpenAI uyumlu sahte yürütücü konur; sahne görevi yuki-oss'un kendi sahte motoruyla koşar
(`YUKI_SAHNE_MOTOR` varsayılanı `sahte`: ağ yok, para yok):

    python3 <rapor>/olc/sahte_llm.py 18840 &
    YUKI_DATA_DIR=$(mktemp -d) ATOLYE=true AUTH_TOKEN=g1-ornek-anahtar USE_LOCAL_LLM=true \\
      OLLAMA_BASE_URL=http://127.0.0.1:18840/v1 OLLAMA_MODEL=sahte SCHEDULER_ENABLED=false \\
      uvicorn app.main:app --port 18841
    YUKI_URL=http://127.0.0.1:18841 YUKI_TEST_ANAHTAR=g1-ornek-anahtar \\
      YUKI_EKRAN_DIZINI=<klasör> python -m pytest frontend/tests/test_atolye_g1.py -q

Ölçülenler (390 ve 1280, normal/animasyonlu kip, JS istisnası 0):
  1. Atölye açıkken sahne dosyaları tembel yüklenir (index.html'de etiket yok).
  2. Sahne görevi koşarken ilerleme kartı görünür, aşama + sayaçlar dolar.
  3. Görev bitince sahne katmanı kendiliğinden açılır: ≥6 blok, türler çizilir, yatay taşma yok,
     kaynak bağlantıları https + noopener.
  4. Esc kapatır → köşede ◈ düğmesi; ◈ yeniden açar; GEÇMİŞ menüsü kayıtlı sahneyi listeler.
  5. Site görevi gerçek servisten geçip `bitti` olunca ekranda duyuru (bir kez).
  6. Hareketi azalt tercihinde blok animasyonu kapalı.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

import pytest

from perdesiz import PERDESIZ_JS

BASE = os.getenv("YUKI_URL", "http://127.0.0.1:8001")
ANAHTAR = os.getenv("YUKI_TEST_ANAHTAR", "")
EKRAN = os.getenv("YUKI_EKRAN_DIZINI", "")
GENISLIKLER = [(390, 844), (1280, 800)]


def _sunucu_var(url: str) -> bool:
    try:
        return urllib.request.urlopen(url + "/health", timeout=3).status == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not (_sunucu_var(BASE) and ANAHTAR),
                                reason=f"anahtarlı Atölye sunucusu yok ({BASE}) ya da YUKI_TEST_ANAHTAR boş")


def _api(yol, veri=None, metot="GET"):
    istek = urllib.request.Request(BASE + yol, method=metot,
                                   data=json.dumps(veri).encode() if veri is not None else None,
                                   headers={"Content-Type": "application/json",
                                            "Authorization": f"Bearer {ANAHTAR}"})
    with urllib.request.urlopen(istek, timeout=10) as r:
        return json.loads(r.read())


def _gorev(gid):
    return next((g for g in _api("/api/gorev")["gorevler"] if g["id"] == gid), None)


def _ekran(pg, ad):
    if EKRAN:
        Path(EKRAN).mkdir(parents=True, exist_ok=True)
        pg.screenshot(path=str(Path(EKRAN) / f"{ad}.png"))


@pytest.fixture(scope="module")
def tarayici():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _sayfa(br, vp, hareket="no-preference"):
    ctx = br.new_context(viewport={"width": vp[0], "height": vp[1]}, service_workers="block",
                         reduced_motion=hareket)
    pg = ctx.new_page()
    pg._hatalar = []
    pg.on("pageerror", lambda e: pg._hatalar.append(str(e)))
    pg.add_init_script(PERDESIZ_JS)
    pg.goto(BASE + "/ui/", wait_until="networkidle")
    pg.locator("#auth-input").fill(ANAHTAR)
    pg.locator("#auth-input").press("Enter")
    pg.wait_for_function("() => document.getElementById('auth-screen').classList.contains('hidden')")
    pg.wait_for_function("() => !!window.ArastirmaSahnesi && !!window.GorevSerit", timeout=20000)
    return pg


def _bekle(kosul, sure=30.0, adim=0.2):
    son = time.monotonic() + sure
    while time.monotonic() < son:
        v = kosul()
        if v:
            return v
        time.sleep(adim)
    return None


@pytest.mark.parametrize("vp", GENISLIKLER, ids=["390", "1280"])
def test_sahne_karti_katman_gecmis(tarayici, vp):
    pg = _sayfa(tarayici, vp)
    try:
        # 1) tembel yükleme: index.html'de etiket yok, sayfada var
        html = urllib.request.urlopen(BASE + "/ui/index.html", timeout=5).read().decode()
        assert "arastirma-sahnesi" not in html
        assert pg.locator("link[href*='arastirma-sahnesi.css']").count() == 1

        ad = f"g1-sahne-{vp[0]}-{int(time.time())}"
        _api("/api/gorev/baslat", {"tur": "sahne", "ad": ad,
                                   "istek": "Elektrikli bisikletlerde pil ömrünü uzatan alışkanlıkları araştır"}, "POST")
        # 2) ilerleme kartı
        pg.wait_for_selector("#sahne-kart:not([hidden])", timeout=15000)
        assert pg.locator("#sahne-kart .sh-kart-ad").inner_text() == ad
        _bekle(lambda: pg.evaluate("() => +document.querySelector('#sahne-kart [data-k=kaynak]').textContent > 0"), 15)
        _ekran(pg, f"sahne-kart-{vp[0]}")

        # 3) katman kendiliğinden açılır
        pg.wait_for_selector("#sahne-katman:not([hidden])", timeout=30000)
        pg.wait_for_timeout(1200)                      # dizilme animasyonu bitsin
        bloklar = pg.locator("#sahne-katman .sh-blok")
        assert bloklar.count() >= 6
        turler = set(pg.evaluate("() => [...document.querySelectorAll('#sahne-katman .sh-blok')].map(b => b.dataset.tur)"))
        assert len(turler) >= 2, turler
        tasma = pg.evaluate("() => { const k = document.getElementById('sahne-katman');"
                            " return [document.documentElement.scrollWidth, innerWidth, k.scrollWidth, k.clientWidth]; }")
        assert tasma[0] <= tasma[1] + 1 and tasma[2] <= tasma[3] + 1, tasma
        for a in pg.locator("#sahne-katman a.sh-kaynak").all():
            assert a.get_attribute("href").startswith("https://")
            assert "noopener" in a.get_attribute("rel") and a.get_attribute("target") == "_blank"
        assert pg.evaluate("() => document.activeElement && document.activeElement.classList.contains('sh-kapat')")
        _ekran(pg, f"sahne-katman-{vp[0]}")
        assert _gorev(f"sahne/{ad}")["durum"] in ("bitti", "yarim")

        # 4) Esc → ◈ → yeniden aç → GEÇMİŞ
        pg.keyboard.press("Escape")
        pg.wait_for_selector("#sahne-katman", state="hidden", timeout=5000)
        pg.wait_for_selector("#sahne-ac:not([hidden])", timeout=5000)
        _ekran(pg, f"sahne-dugme-{vp[0]}")
        pg.locator("#sahne-ac").click()
        pg.wait_for_selector("#sahne-katman:not([hidden])", timeout=5000)
        pg.locator("#sahne-katman .sh-gecmis-d").click()
        pg.wait_for_selector("#sahne-katman .sh-gecmis:not([hidden]) button", timeout=5000)
        assert pg.locator("#sahne-katman .sh-gecmis button").count() >= 1
        _ekran(pg, f"sahne-gecmis-{vp[0]}")
        pg.locator("#sahne-katman .sh-kapat").click()
        pg.wait_for_selector("#sahne-katman", state="hidden", timeout=5000)
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


@pytest.mark.parametrize("vp", GENISLIKLER, ids=["390", "1280"])
def test_site_gorevi_biter_ekranda_duyurulur(tarayici, vp):
    pg = _sayfa(tarayici, vp)
    try:
        ad = f"g1-site-{vp[0]}-{int(time.time())}"
        _api("/api/gorev/baslat", {"tur": "site", "ad": ad,
                                   "istek": "Mahalle fırını için tek sayfalık tanıtım sitesi yap."}, "POST")
        g = _bekle(lambda: (lambda x: x if x and x["durum"] != "kosuyor" else None)(_gorev(f"site/{ad}")), 60)
        assert g and g["durum"] == "bitti", g
        assert g["dogrulama"]["temiz"] is True
        assert _bekle(lambda: pg.evaluate("() => window.GorevSerit.duyuruDurum().soylenen") >= 1, 15)
        pg.wait_for_timeout(500)
        _ekran(pg, f"site-bitti-duyuru-{vp[0]}")
        assert pg.evaluate("() => window.GorevSerit.duyuruDurum().soylenen") == 1     # bir kez
        # çalışma alanındaki gerçek çıktı (servis doğrulamasından geçmiş site)
        alan = Path(g["alan"])
        assert (alan / "index.html").is_file() and (alan / "css" / "stil.css").is_file()
        if EKRAN:
            sp = pg.context.new_page()
            sp.set_viewport_size({"width": vp[0], "height": vp[1]})
            sp.goto((alan / "index.html").as_uri())
            _ekran(sp, f"site-cikti-{vp[0]}")
            sp.close()
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


def test_hareketi_azalt_animasyonsuz(tarayici):
    pg = _sayfa(tarayici, (1280, 800), hareket="reduce")
    try:
        sahneler = _api("/api/gorev/sahne")["sahneler"]
        if not sahneler:
            pytest.skip("kayıtlı sahne yok — önce test_sahne_karti_katman_gecmis")
        assert pg.evaluate(f"() => window.ArastirmaSahnesi.ac({json.dumps(sahneler[0]['id'])})")
        pg.wait_for_selector("#sahne-katman:not([hidden])", timeout=5000)
        assert pg.evaluate("() => document.getElementById('sahne-katman').classList.contains('az-hareket')")
        ad = pg.evaluate("() => getComputedStyle(document.querySelector('#sahne-katman .sh-blok')).animationName")
        assert ad == "none", ad
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()

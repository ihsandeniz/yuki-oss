"""Kamera görüşü + ses kimliği paneli ve RIZA EKRANI — tarayıcı testi (390 ve 1280, JS istisnası 0).

Sunucu gerekmez: `frontend/` geçici bir statik sunucuyla (ikinci port) açılır, `/api/**` istekleri
Playwright içinde sahte cevaplarla karşılanır, kamera `getUserMedia` sahtesiyle verilir.
Animasyonlar AÇIK (normal mod) ölçülür; ekran görüntüleri `EKRAN_DIZIN` verilirse oraya yazılır.

    EKRAN_DIZIN=/tmp/ekran python -m pytest frontend/tests/test_gorus_panel.py -q

Ölçülenler:
  1. İki bayrak da kapalıyken (404) panel görünmez, kart yok.
  2. Bayrak açık, rıza yok → kart "Kapalı" + "Aç"; Aç → rıza ekranı açılır, odak kutuda.
  3. Kutu işaretlenmeden "İzin ver ve aç" pasif; Esc ekranı kapatır, rıza isteği GİTMEZ.
  4. Kutu + onay → POST /api/gorus/riza {kabul:true, surum:<metin sürümü>} → kamera başlar, "Yuki bak" görünür.
  5. "Yuki bak" cevabı ekranda; yerel model yoksa açık hata cümlesi.
  6. "Rızayı geri çek" → DELETE gider, kamera izleri durur, kart yine "Aç".
  7. Ses kimliği: rıza ekranı kendi metniyle; model yoksa indirme yolu yazılır, "Sesimi kaydet" pasif.
  8. Sayfa yatay taşmaz; rıza ekranı görünür alana sığar; metin en az 14px.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

FRONTEND = Path(__file__).resolve().parents[1]
GENISLIKLER = [(390, 844), (1280, 800)]
EKRAN = os.getenv("EKRAN_DIZIN", "")

SAHTE_KAMERA = """
(() => {
  window.__izler = [];
  const sahte = () => {
    const c = document.createElement('canvas'); c.width = 64; c.height = 48;
    const s = c.captureStream(1);
    s.getTracks().forEach(t => { const dur = t.stop.bind(t); t.stop = () => { t.__durdu = true; dur(); }; window.__izler.push(t); });
    return s;
  };
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true,
    value: { getUserMedia: async () => sahte() } });
})();
"""


def _bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def taban():
    port = _bos_port()
    p = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                         cwd=FRONTEND, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    p.terminate()
    p.wait(5)


@pytest.fixture(scope="module")
def tarayici():
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


class SahteApi:
    def __init__(self, gorus=True, ses=True, model_hazir=True, ses_model=True):
        self.gorus, self.ses = gorus, ses
        self.g_riza = False
        self.s_riza = False
        self.model_hazir, self.ses_model = model_hazir, ses_model
        self.istekler: list[tuple[str, str, dict | None]] = []

    def _gdurum(self):
        return {"acik": True, "riza": {"verildi": self.g_riza, "surum": 1},
                "model": {"hazir": self.model_hazir, "neden": "" if self.model_hazir else
                          "yerel görsel model bulunamadı (http://127.0.0.1:11434/v1)"}, "kamera_bagli": False}

    def _sdurum(self):
        return {"acik": True, "riza": {"verildi": self.s_riza, "surum": 1},
                "model": {"var": self.ses_model, "yol": "/veri/modeller/ses-kimlik/campplus.onnx",
                          "indir": "https://huggingface.co/csukuangfj/speaker-embedding-models"},
                "kayit": {"var": False}}

    def __call__(self, route):
        r = route.request
        yol = r.url.split("://", 1)[1].split("/", 1)[1]
        yol = "/" + yol.split("?")[0]
        govde = None
        if r.post_data and "json" in (r.headers.get("content-type") or ""):
            govde = json.loads(r.post_data)
        self.istekler.append((r.method, yol, govde))

        def cevap(veri, kod=200):
            route.fulfill(status=kod, content_type="application/json", body=json.dumps(veri))
        if yol.startswith("/api/gorus/") and not self.gorus:
            return cevap({"detail": "Not Found"}, 404)
        if yol.startswith("/api/ses-kimlik/") and not self.ses:
            return cevap({"detail": "Not Found"}, 404)
        if yol == "/api/gorus/durum":
            return cevap(self._gdurum())
        if yol == "/api/gorus/riza":
            self.g_riza = r.method == "POST"
            return cevap({"riza": {"verildi": self.g_riza, "surum": 1}})
        if yol == "/api/gorus/bak":
            if self.model_hazir:
                return cevap({"ok": True, "metin": "Masada bir kupa ve açık bir defter var."})
            return cevap({"ok": False, "metin": "Şu an göremiyorum: yerel görsel model bulunamadı."})
        if yol == "/api/ses-kimlik/durum":
            return cevap(self._sdurum())
        if yol == "/api/ses-kimlik/riza":
            self.s_riza = r.method == "POST"
            return cevap(self._sdurum())
        return cevap({"detail": "Not Found"}, 404)


def _sahte_ws(ws):
    """Sunucusuz /ws/gorus: her kareye 'durum' cevabı (kamera açık kalır)."""
    ws.on_message(lambda m: ws.send(json.dumps({"tip": "durum", "durum": "burada", "yuz": 1, "olaylar": [], "soyle": None})))


def _sayfa(tarayici, taban, api, gen):
    ctx = tarayici.new_context(viewport={"width": gen[0], "height": gen[1]})
    pg = ctx.new_page()
    hatalar: list[str] = []
    pg.on("pageerror", lambda e: hatalar.append(str(e)))
    pg.add_init_script(SAHTE_KAMERA)
    pg.route("**/api/**", api)
    pg.route_web_socket("**/ws/gorus*", _sahte_ws)
    pg.goto(taban + "/tests/gorus-sahne.html")
    pg.wait_for_function("document.querySelector('[data-gorus-panel]').dataset.gpKurulu === '1'")
    pg.wait_for_timeout(150)
    return ctx, pg, hatalar


def _ekran(pg, ad):
    if EKRAN:
        Path(EKRAN).mkdir(parents=True, exist_ok=True)
        pg.wait_for_timeout(300)           # giriş animasyonu bitsin (normal mod)
        pg.screenshot(path=str(Path(EKRAN) / ad), full_page=True)


def _tasma_yok(pg):
    assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


@pytest.mark.parametrize("gen", GENISLIKLER, ids=lambda g: str(g[0]))
def test_kapaliyken_panel_yok(tarayici, taban, gen):
    ctx, pg, hatalar = _sayfa(tarayici, taban, SahteApi(gorus=False, ses=False), gen)
    pg.wait_for_timeout(200)
    assert pg.locator(".gp-kart").count() == 0
    assert pg.locator("[data-gorus-panel]").is_hidden()
    assert hatalar == []
    ctx.close()


@pytest.mark.parametrize("gen", GENISLIKLER, ids=lambda g: str(g[0]))
def test_gorus_riza_akisi(tarayici, taban, gen):
    api = SahteApi()
    ctx, pg, hatalar = _sayfa(tarayici, taban, api, gen)
    kart = pg.locator(".gp-kart").first
    assert "Kapalı" in kart.locator(".gp-rozet").inner_text()
    _ekran(pg, f"panel-kapali-{gen[0]}.png")

    kart.locator(".gp-ac").click()
    riza = pg.locator(".gp-riza[data-ozellik='gorus']")
    riza.wait_for()
    assert pg.evaluate("document.activeElement.classList.contains('gp-riza__kutu')")
    onay = riza.locator(".gp-riza__onayla")
    assert onay.is_disabled()
    assert "buluta gönderilmez" in riza.inner_text()
    kutu = riza.bounding_box()
    assert kutu["x"] >= 0 and kutu["x"] + kutu["width"] <= gen[0] + 1
    assert kutu["y"] >= 0 and kutu["y"] + kutu["height"] <= gen[1] + 1
    for sinif in (".gp-riza__maddeler li", ".gp-riza__onay"):
        assert pg.eval_on_selector(sinif, "e => parseFloat(getComputedStyle(e).fontSize)") >= 14
    _tasma_yok(pg)
    _ekran(pg, f"riza-gorus-{gen[0]}.png")

    pg.keyboard.press("Escape")
    assert riza.count() == 0
    assert not any(m == "POST" and y == "/api/gorus/riza" for m, y, _ in api.istekler)

    kart.locator(".gp-ac").click()
    riza.wait_for()
    riza.locator(".gp-riza__kutu").check()
    assert onay.is_enabled()
    onay.click()
    pg.locator(".gp-bak").wait_for()
    assert ("POST", "/api/gorus/riza", {"kabul": True, "surum": 1}) in api.istekler
    assert pg.evaluate("window.__izler.length") >= 1

    durum = pg.locator(".gp-kart").first.locator(".gp-kart__durum").inner_text()
    assert "Kamera açık" in durum and "kapalı" not in durum      # rozet ile gövde çelişmesin (goz 1. tur)
    pg.locator(".gp-bak").click()
    pg.wait_for_function("document.querySelector('.gp-kart__cevap').textContent.includes('kupa')")
    _tasma_yok(pg)
    _ekran(pg, f"kamera-acik-{gen[0]}.png")

    pg.locator(".gp-kart").first.locator(".gp-geri").click()
    pg.locator(".gp-kart").first.locator(".gp-ac").wait_for()
    assert any(m == "DELETE" and y == "/api/gorus/riza" for m, y, _ in api.istekler)
    assert pg.evaluate("window.__izler.every(t => t.__durdu)")
    assert hatalar == []
    ctx.close()


@pytest.mark.parametrize("gen", GENISLIKLER, ids=lambda g: str(g[0]))
def test_model_yoksa_acik_hata(tarayici, taban, gen):
    api = SahteApi(model_hazir=False, ses_model=False)
    api.g_riza = api.s_riza = True
    ctx, pg, hatalar = _sayfa(tarayici, taban, api, gen)
    hata = pg.locator(".gp-kart").first.locator(".gp-kart__hata")
    assert hata.is_visible() and "yerel görsel model" in hata.inner_text()
    ses = pg.locator(".gp-kart").nth(1)
    assert "huggingface.co" in ses.locator(".gp-kart__hata").inner_text()
    assert ses.locator(".gp-kaydet").is_disabled()
    for h in pg.eval_on_selector_all(".gp-dugme", "es => es.map(e => e.getBoundingClientRect().height)"):
        assert h >= 44                                  # dokunma hedefi (goz 1. tur)
    # uzun model yolu kelime ortasından kırılmaz, kendi içinde kayar; sayfa taşmaz (goz 2. tur)
    assert pg.eval_on_selector(".gp-kart__yol", "e => getComputedStyle(e).whiteSpace") == "nowrap"
    _tasma_yok(pg)
    _ekran(pg, f"model-yok-{gen[0]}.png")
    assert hatalar == []
    ctx.close()


@pytest.mark.parametrize("gen", GENISLIKLER, ids=lambda g: str(g[0]))
def test_ses_kimlik_riza_ekrani(tarayici, taban, gen):
    api = SahteApi(gorus=False)
    ctx, pg, hatalar = _sayfa(tarayici, taban, api, gen)
    assert pg.locator(".gp-kart").count() == 1
    pg.locator(".gp-kart .gp-ac").click()
    riza = pg.locator(".gp-riza[data-ozellik='ses_kimlik']")
    riza.wait_for()
    assert "biyometrik" in riza.inner_text() and "silinir" in riza.inner_text()
    _tasma_yok(pg)
    _ekran(pg, f"riza-ses-{gen[0]}.png")
    riza.locator(".gp-riza__kutu").check()
    riza.locator(".gp-riza__onayla").click()
    pg.locator(".gp-kaydet").wait_for()
    assert ("POST", "/api/ses-kimlik/riza", {"kabul": True, "surum": 1}) in api.istekler
    assert hatalar == []
    ctx.close()

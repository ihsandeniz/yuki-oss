"""Kamerayla çekilen fotoğraf Yuki'ye gider — gerçek Chromium'da (`tab-switcher.js`, sunucu sahte).

Kusur: `_cameraSend()` yüklemeden ÖNCE `closeCameraCapture()`'ı çağırıyordu, o da
`_capturedBlob = null` yapıyordu → `FormData.append('file', null, …)` hata veriyor,
`/api/media/upload` hiç çağrılmıyor, kullanıcı "fotoğraf gönderilemedi" görüyordu.
Fotoğraf sohbette yalnız kullanıcı tarafında görünüyor, Yuki'ye hiç ulaşmıyordu.

Ölçülen: ÇEK → GÖNDER sonrası yükleme isteği tek kez gider, gövdesinde JPEG dosyası vardır,
ardından `send-to-chat/<kayıtlı ad>` çağrılır, hata bildirimi çıkmaz, pencere kapanır.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

JS = Path(__file__).resolve().parents[2] / "frontend" / "js" / "tab-switcher.js"

SAYFA = """<!doctype html><html><body>
<input type="file" id="mediaFileInput">
<div id="messages"></div>
<div id="camera-capture-modal" style="display:none">
  <video id="camera-video"></video>
  <img id="camera-preview">
  <canvas id="camera-canvas"></canvas>
  <button id="camera-snap-btn"></button>
  <button id="camera-retake-btn"></button>
  <button id="camera-send-btn"></button>
</div>
</body></html>"""

KUR = """() => {
  window.istekler = [];
  window.bildirimler = [];
  window.showToast = (m, tur) => window.bildirimler.push([m, tur]);
  window.authFetch = async (url, opt) => {
    const kayit = { url, yontem: (opt && opt.method) || 'GET', dosya: null };
    if (opt && opt.body instanceof FormData) {
      const f = opt.body.get('file');
      kayit.dosya = f ? { ad: f.name, tur: f.type, boyut: f.size } : null;
    }
    window.istekler.push(kayit);
    if (url === '/api/media/upload') {
      return { ok: true, status: 200, json: async () => ({ filename: 'kayitli.jpg' }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  };
  // Kamera yerine boyalı bir tuval akışı: getUserMedia gerçek aygıt istemesin.
  const tuval = document.createElement('canvas');
  tuval.width = 64; tuval.height = 48;
  const c = tuval.getContext('2d'); c.fillStyle = '#c33'; c.fillRect(0, 0, 64, 48);
  const akis = tuval.captureStream(5);
  // set_content güvenli bağlam değil → mediaDevices yok; sahte nesne konur.
  if (!navigator.mediaDevices) Object.defineProperty(navigator, 'mediaDevices', { value: {}, configurable: true });
  navigator.mediaDevices.getUserMedia = async () => akis;
}"""


@pytest.fixture(scope="module")
def tarayici():
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # tarayıcı kurulu değilse ölçülemedi — yeşil SAYILMAZ
            pytest.skip(f"chromium açılamadı: {e}")
        yield b
        b.close()


@pytest.fixture
def sayfa(tarayici):
    s = tarayici.new_page()
    s._hatalar = []
    s.on("pageerror", lambda e: s._hatalar.append(str(e)))
    s.set_content(SAYFA)
    s.evaluate(KUR)
    s.add_script_tag(path=str(JS))
    yield s
    s.close()


def _cek(s):
    s.evaluate("openCameraCapture()")
    s.wait_for_function("document.getElementById('camera-video').srcObject !== null")
    s.evaluate("""() => new Promise(r => {
        const v = document.getElementById('camera-video');
        v.play().then(() => setTimeout(r, 150));
    })""")
    s.evaluate("_cameraSnap()")
    s.wait_for_function("document.getElementById('camera-send-btn').style.display === 'inline-block'")


def test_cekilen_fotograf_yuklenir_ve_sohbete_gider(sayfa):
    _cek(sayfa)
    sayfa.evaluate("_cameraSend()")
    sayfa.wait_for_function("window.istekler.length >= 2 || window.bildirimler.length > 0", timeout=5000)

    istekler = sayfa.evaluate("window.istekler")
    assert sayfa.evaluate("window.bildirimler") == []
    assert [i["url"] for i in istekler] == ["/api/media/upload", "/api/media/send-to-chat/kayitli.jpg"]
    dosya = istekler[0]["dosya"]
    assert dosya and dosya["tur"] == "image/jpeg" and dosya["boyut"] > 0
    assert dosya["ad"].startswith("photo_") and dosya["ad"].endswith(".jpg")
    assert sayfa._hatalar == []


def test_gonderince_pencere_kapanir_ve_kamera_durur(sayfa):
    _cek(sayfa)
    sayfa.evaluate("_cameraSend()")
    sayfa.wait_for_function("window.istekler.length >= 2", timeout=5000)
    assert sayfa.evaluate("document.getElementById('camera-capture-modal').style.display") == "none"
    assert sayfa.evaluate("document.getElementById('camera-video').srcObject") is None
    # Kullanıcının kendi fotoğrafı sohbette görünür (yerel önizleme).
    assert sayfa.locator("#messages img").count() == 1


def test_fotograf_cekilmeden_gonder_bir_sey_yapmaz(sayfa):
    sayfa.evaluate("openCameraCapture()")
    sayfa.evaluate("_cameraSend()")
    sayfa.wait_for_timeout(200)
    assert sayfa.evaluate("window.istekler") == []

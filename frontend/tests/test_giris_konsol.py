"""Halka Konsolu yazı çubuğu — tarayıcı testleri (2026-10-11).

Kişisel 933779b'nin ürün çevirisi. Yapı kapıları: `backend/tests/test_giris_konsol.py`.

Çalıştırma (sunucu gerekli — ikinci port):
    YUKI_URL=http://127.0.0.1:8021 backend/venv/bin/python -m pytest frontend/tests/test_giris_konsol.py -q

Ölçülenler (390 ve 1280):
  1. Cam hap düğmelerin ALTINDA: gönder/⋯/yazı alanının merkezindeki en üst
     eleman kendisi (ilk sürümde hap backdrop-filter yüzünden üstte boyanıyordu).
  2. Küçült → yalnız mikrofon + YAZ görünür; tercih yeniden yüklemede kalır.
  3. "/" küçük hâli açar, yazı alanına odaklar ve TASLAĞI SİLMEZ.
  4. YAZ düğmesi açar, odak yazı alanına döner. JS istisnası 0.
"""
from __future__ import annotations

import os

import pytest

from perdesiz import PERDESIZ_JS   # açılış sinematiği + ilk kurulum perdesi tıklamayı keser

BASE = os.getenv("YUKI_URL", "http://127.0.0.1:8001")
GENISLIKLER = [(390, 844), (1280, 800)]


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


def _sayfa(br, vp, kucuk="0"):
    ctx = br.new_context(viewport={"width": vp[0], "height": vp[1]}, service_workers="block")
    pg = ctx.new_page()
    pg.add_init_script(PERDESIZ_JS)
    pg._hatalar = []
    pg.on("pageerror", lambda e: pg._hatalar.append(str(e)))
    pg.add_init_script("if (!sessionStorage.getItem('_kurulu')) { localStorage.setItem('giris_kucuk_v1', '%s'); sessionStorage.setItem('_kurulu', '1'); }" % kucuk)
    pg.goto(BASE + "/ui/", wait_until="networkidle")
    pg.wait_for_function("() => window.GirisKonsol && document.getElementById('send-btn')")
    return pg


EN_USTTEKI = """(id) => { const e = document.getElementById(id); const r = e.getBoundingClientRect();
  const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return !!t && (t === e || e.contains(t)); }"""
GORUNUR = "(id) => { const e = document.getElementById(id); return !!e && e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden'; }"


def _ikon_kontrasti(pg, secici) -> float:
    """Düğmenin iç karesindeki parlaklık aralığı (en parlak − en koyu, 0-255).
    ⚠️ elementFromPoint burada İŞE YARAMAZ: hap `pointer-events:none`, tıklama
    düğmeye gider ama hap yine de ÜSTÜNE boyanır (ilk sürümde gönder ikonu
    görünmüyordu). Soru boyama sırası → piksel ölçülür."""
    import io
    from PIL import Image
    kutu = pg.locator(secici).bounding_box()
    p = 0.25
    kare = {"x": kutu["x"] + kutu["width"] * p, "y": kutu["y"] + kutu["height"] * p,
            "width": kutu["width"] * (1 - 2 * p), "height": kutu["height"] * (1 - 2 * p)}
    img = Image.open(io.BytesIO(pg.screenshot(clip=kare))).convert("L")
    lo, hi = img.getextrema()
    return hi - lo


@pytest.mark.parametrize("vp", GENISLIKLER, ids=["390", "1280"])
def test_hap_dugmelerin_altinda(tarayici, vp):
    pg = _sayfa(tarayici, vp)
    try:
        for kimlik in ("send-btn", "input-more-btn", "msg-input", "mic-btn"):
            assert pg.evaluate(EN_USTTEKI, kimlik), f"{kimlik} merkezinde başka bir eleman var"
        # Eşikler ÖLÇÜLDÜ (10-11, açık tema = en düşük): doğru boyamada gönder 57 · ⋯ 174;
        # hap üste boyanınca (z-index mutasyonu) gönder 7 · ⋯ 42. Gönderin 57'si ürünün
        # açık tema rengi (giris-konsol.css olmadan da 56) — bu testin konusu değil.
        k_gonder, k_daha = _ikon_kontrasti(pg, "#send-btn"), _ikon_kontrasti(pg, "#input-more-btn")
        assert k_gonder >= 30 and k_daha >= 100, \
            f"ikon soluk (gönder {k_gonder}, ⋯ {k_daha}) — hap düğmelerin üstüne mi boyanıyor?"
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


@pytest.mark.parametrize("vp", GENISLIKLER, ids=["390", "1280"])
def test_kucult_ve_kalicilik(tarayici, vp):
    pg = _sayfa(tarayici, vp)
    try:
        pg.click("#giris-kucult")
        assert pg.evaluate("() => document.getElementById('input-area').classList.contains('kucuk')")
        assert pg.evaluate("() => localStorage.getItem('giris_kucuk_v1')") == "1"
        for kimlik in ("msg-input", "send-btn", "input-more-btn", "hizli-satir"):
            assert not pg.evaluate(GORUNUR, kimlik), f"küçük hâlde {kimlik} görünüyor"
        for kimlik in ("mic-btn", "giris-ac"):
            assert pg.evaluate(GORUNUR, kimlik), f"küçük hâlde {kimlik} yok"
        assert pg.evaluate("() => document.activeElement.id") == "giris-ac", "odak kayboldu"
        pg.reload(wait_until="networkidle")
        pg.wait_for_function("() => window.GirisKonsol")
        assert pg.evaluate("() => window.GirisKonsol.kucukMu()"), "tercih yeniden yüklemede kalmadı"
        pg.click("#giris-ac")
        assert not pg.evaluate("() => window.GirisKonsol.kucukMu()")
        assert pg.evaluate("() => document.activeElement.id") == "msg-input"
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


def test_slash_acar_ve_taslagi_silmez(tarayici):
    pg = _sayfa(tarayici, (1280, 800), kucuk="1")
    try:
        pg.evaluate("() => { document.getElementById('msg-input').value = 'yarım taslak'; document.activeElement.blur(); document.body.focus(); }")
        pg.keyboard.press("/")
        assert not pg.evaluate("() => window.GirisKonsol.kucukMu()"), "/ küçük hâli açmadı"
        assert pg.evaluate("() => document.activeElement.id") == "msg-input"
        assert pg.evaluate("() => document.getElementById('msg-input').value") == "yarım taslak", "/ taslağı sildi"
    finally:
        pg.context.close()


def test_koyu_temada_hap_tek_ton(tarayici):
    """Göz tur 3 A1: yazı alanındaki eski backdrop-filter hapın camını ikinci kez
    bulanıklaştırıyordu → koyu temada yazı alanı ile ⋯ arasında görünür kutu kenarı
    (32,30,37 ↔ 29,28,34). Hap boyunca, yazı alanının sağ kenarının iki yanı aynı ton olmalı."""
    import io
    from PIL import Image
    ctx = tarayici.new_context(viewport={"width": 1280, "height": 800}, service_workers="block")
    pg = ctx.new_page()
    pg.add_init_script(PERDESIZ_JS)
    try:
        pg.add_init_script("localStorage.setItem('yukiTema_v1','koyu'); localStorage.setItem('giris_kucuk_v1','0');")
        pg.goto(BASE + "/ui/", wait_until="networkidle")
        pg.wait_for_function("() => window.GirisKonsol")
        r = pg.locator("#msg-input").bounding_box()
        y = int(r["y"] + r["height"] / 2)
        sag = int(r["x"] + r["width"])
        img = Image.open(io.BytesIO(pg.screenshot())).convert("RGB")
        ic, dis = img.getpixel((sag - 8, y)), img.getpixel((sag + 3, y))
        fark = max(abs(a - b) for a, b in zip(ic, dis))
        assert fark <= 1, f"hap içinde yazı alanı ayrı kutu gibi: {ic} ↔ {dis}"
    finally:
        ctx.close()

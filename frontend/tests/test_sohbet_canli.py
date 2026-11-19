"""SOHBET · CANLI kipi — tarayıcı testleri (2026-10-11).

Kişisel AliceAi'nin CANLI kipinin (hareketli Yuki) ürün çevirisini DAVRANIŞTAN
ölçer. Yapı kapıları sunucusuz: `backend/tests/test_sohbet_canli.py`.

Çalıştırma (sunucu gerekli — canlı ürüne değil, ikinci porta):
    cd backend && YUKI_DATA_DIR=<geçici> venv/bin/python -m uvicorn app.main:app --port 8021
    YUKI_URL=http://127.0.0.1:8021 backend/venv/bin/python -m pytest frontend/tests/test_sohbet_canli.py -q

Ölçülenler:
  1. Motor kip seçilince kurulur (canvas + motor), RESİM'e geçince kapanır
     (canvas DOM'dan çıkar) — 390 ve 1280'de JS istisnası 0.
  2. 🔴 HAFİF grafik kademesi: CANLI seçeneği yok, kayıtlı 'canli' tercihi RESİM
     gösterir, motor kurulmaz; çalışırken HAFİF'e geçilirse motor kapanır.
  3. Yuki dışı karakterde CANLI seçeneği yok, motor kapanır.
  4. GERÇEK playVoice yolundan (WS `audio`) çalan sesle ağız açılır, bitince kapanır.
  5. GERÇEK WS `emotion` olayı yüze yansır.
  6. Ok tuşu yalnız görünen kipler arasında döner.

⚠️ WebGL2 başsız Chromium'da SwiftShader ile (yazılım GL) — gerçek GPU ölçülmez.
"""
from __future__ import annotations

import base64
import io
import json
import math
import os
import struct
import wave

import pytest

BASE = os.getenv("YUKI_URL", "http://127.0.0.1:8001")
TELEFON = {"width": 390, "height": 844}
MASAUSTU = {"width": 1280, "height": 800}
GL_ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
           "--autoplay-policy=no-user-gesture-required"]
DURUM = "() => window.SohbetSahne.durumOku()"
MOTOR_HAZIR = "() => window.SohbetSahne.durumOku().canliMotor"
CANVAS = "() => document.querySelectorAll('#avatar-pane canvas.ss-canli').length"


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
        b = p.chromium.launch(args=GL_ARGS)
        yield b
        b.close()


def _sayfa(br, viewport=MASAUSTU, kip="canli", gfx="normal"):
    ctx = br.new_context(viewport=viewport, service_workers="block")
    pg = ctx.new_page()
    pg._hatalar = []
    pg.on("pageerror", lambda e: pg._hatalar.append(str(e)))
    # 2026-11-13 : ilk açılış artık HALKA — bu dosya SOHBET sahnesini ölçer, modu açıkça seç.
    pg.add_init_script(
        "localStorage.setItem('yukiViewMode_v1', 'chat'); localStorage.setItem('yukiSohbetKip_v1', %s); localStorage.setItem('yukiGfx_v1', %s);"
        % (json.dumps(kip), json.dumps(gfx)))
    pg.goto(BASE + "/ui/", wait_until="networkidle")
    pg.wait_for_function("() => window.SohbetSahne && document.getElementById('ss-kip')")
    return pg


def _wav_b64(sn=1.2, hz=220) -> str:
    """Yüksek genlikli sinüs → analyser RMS'i belirgin (ağız açılmalı)."""
    oran = 22050
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(oran)
        w.writeframes(b"".join(struct.pack("<h", int(20000 * math.sin(2 * math.pi * hz * i / oran)))
                               for i in range(int(oran * sn))))
    return base64.b64encode(tampon.getvalue()).decode()


# ── 1 · kur / kapat, iki genişlik ─────────────────────────────────────────

@pytest.mark.parametrize("vp", [TELEFON, MASAUSTU], ids=["390", "1280"])
def test_motor_kurulur_ve_resimde_kapanir(tarayici, vp):
    pg = _sayfa(tarayici, vp)
    try:
        pg.wait_for_function(MOTOR_HAZIR, timeout=20000)
        d = pg.evaluate(DURUM)
        assert d["etkinKip"] == "canli" and "canli" in d["secenekler"]
        assert pg.evaluate(CANVAS) == 1
        assert pg.evaluate("() => document.body.classList.contains('sk-canli')")
        pg.evaluate("() => window.SohbetSahne.kip('resim')")
        assert pg.evaluate(DURUM)["canliMotor"] is False
        assert pg.evaluate(CANVAS) == 0, "RESİM'e geçince canvas DOM'da kaldı (GL bağlamı bırakılmadı)"
        assert not pg.evaluate("() => document.body.classList.contains('sk-canli')")
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


# ── 2 · HAFİF kademe kapısı ───────────────────────────────────────────────

def test_hafifte_canli_yok(tarayici):
    pg = _sayfa(tarayici, kip="canli", gfx="hafif")
    try:
        pg.wait_for_timeout(1500)       # motor kurulacak olsaydı bu sürede başlardı
        d = pg.evaluate(DURUM)
        assert "canli" not in d["secenekler"], d
        assert d["kip"] == "canli", "kayıtlı tercih silinmemeli"
        assert d["etkinKip"] == "resim"
        assert d["canliMotor"] is False and pg.evaluate(CANVAS) == 0
        assert pg.evaluate("() => document.querySelector('#ss-kip [data-kip=canli]').hidden")
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


def test_calisirken_hafife_gecince_motor_kapanir(tarayici):
    pg = _sayfa(tarayici, kip="canli", gfx="normal")
    try:
        pg.wait_for_function(MOTOR_HAZIR, timeout=20000)
        pg.evaluate("() => window.Gfx.set('hafif')")
        d = pg.evaluate(DURUM)
        assert d["canliMotor"] is False and pg.evaluate(CANVAS) == 0
        assert d["etkinKip"] == "resim"
        pg.evaluate("() => window.Gfx.set('normal')")   # geri dönünce kayıtlı tercih yeniden canlı
        pg.wait_for_function(MOTOR_HAZIR, timeout=20000)
    finally:
        pg.context.close()


# ── 3 · yalnız Yuki ───────────────────────────────────────────────────────

def test_yuki_disi_karakterde_canli_yok(tarayici):
    pg = _sayfa(tarayici)
    try:
        pg.wait_for_function(MOTOR_HAZIR, timeout=20000)
        # Kilitli karakterler Free'de seçilemiyor → karakter okuyucusunu taklit et,
        # sahneyi gerçek olayıyla yeniden değerlettir.
        pg.evaluate("() => { window.getCharacter = () => 'nova'; document.dispatchEvent(new CustomEvent('gfxchange')); }")
        d = pg.evaluate(DURUM)
        assert "canli" not in d["secenekler"] and d["canliMotor"] is False
        assert pg.evaluate(CANVAS) == 0
    finally:
        pg.context.close()


# ── 4 · ağız sesi izler (gerçek playVoice yolu) ───────────────────────────

AGIZ = """async (ms) => { const o = []; const t0 = performance.now();
  while (performance.now() - t0 < ms) { const c = window.SohbetSahne.canliOku(); if (c) o.push(c.mouthOpen);
    await new Promise(r => requestAnimationFrame(r)); }
  return o; }"""


def test_tts_sesiyle_agiz_acilir_bitince_kapanir(tarayici):
    pg = _sayfa(tarayici)
    try:
        pg.wait_for_function(MOTOR_HAZIR, timeout=20000)
        sessiz = pg.evaluate(AGIZ, 400)
        assert max(sessiz) < 0.15, f"ses yokken ağız açık: {max(sessiz)}"
        pg.evaluate("(b) => socket.onmessage({ data: JSON.stringify({ type: 'audio', data: b }) })", _wav_b64())
        pg.wait_for_function("() => window.YukiAudioBus && window.YukiAudioBus.tts", timeout=5000)
        konusurken = pg.evaluate(AGIZ, 700)
        assert max(konusurken) > 0.3, f"ses çalarken ağız açılmadı: {max(konusurken)}"
        pg.wait_for_function("() => !window.YukiAudioBus.tts", timeout=5000)
        pg.wait_for_timeout(500)
        sonra = pg.evaluate(AGIZ, 300)
        assert max(sonra) < 0.15, f"ses bitince ağız kapanmadı: {max(sonra)}"
    finally:
        pg.context.close()


# ── 5 · duygu yüze yansır (gerçek WS işleyicisi) ──────────────────────────

def test_ws_duygusu_yuze_yansir(tarayici):
    pg = _sayfa(tarayici)
    try:
        pg.wait_for_function(MOTOR_HAZIR, timeout=20000)
        pg.evaluate("() => socket.onmessage({ data: JSON.stringify({ type: 'emotion', emotion: 'shy', intensity: 0.8 }) })")
        c = pg.evaluate("() => window.SohbetSahne.canliOku()")
        assert c["yuz"] == "shy" and c["ifade"] == "shy", c
        # kullanıcının ses tonu (source: voice) karakterin yüzü DEĞİL
        pg.evaluate("() => socket.onmessage({ data: JSON.stringify({ type: 'emotion', emotion: 'angry', source: 'voice' }) })")
        assert pg.evaluate("() => window.SohbetSahne.canliOku().yuz") == "shy"
    finally:
        pg.context.close()


# ── 6 · klavye ────────────────────────────────────────────────────────────

def test_ok_tusu_gorunen_kipleri_dolasir(tarayici):
    pg = _sayfa(tarayici, kip="resim")
    try:
        l = pg.evaluate(DURUM)["secenekler"]
        pg.focus("#ss-kip [data-kip=resim]")
        sira = []
        for _ in range(len(l)):
            pg.keyboard.press("ArrowRight")
            sira.append(pg.evaluate(DURUM)["etkinKip"])
        assert sorted(sira) == sorted(l) and sira[-1] == "resim", sira
        assert pg.evaluate("() => document.activeElement.dataset.kip") == "resim"
    finally:
        pg.context.close()

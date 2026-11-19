"""SOHBET · CANLI kipi — yapı kapıları (2026-10-11).

Kişisel AliceAi'nin CANLI kipi (hareketli Yuki, c53b052…bea6c21) ürüne ÇEVRİLDİ,
kopyalanmadı. Davranış (motor kurulur/kapanır, ağız sesle açılır, HAFİF'te yok)
tarayıcıda ölçülür: `frontend/tests/test_sohbet_canli.py` (sunucu gerekli).
Burada sunucusuz ölçülenler:

  ① Paket: motor + Yuki rig'i yerinde, MIT bildirimi dağıtılan dosyanın ilk
    satırında ve LICENSE yanında; toplam boyut bütçesi (+1,6 MB kabul edildi).
  ② Kapılar KODDA: yalnız Yuki · HAFİF'te kapalı · gfxchange dinleniyor.
  ③ Motor TEMBEL: index.html onu <script> ile yüklemez, sw.js önbelleğe
    almaz — CANLI'yı hiç seçmeyen müşteri 1,6 MB'ı hiç indirmez.
  ④ Ses yolu: core.js TTS analyser'ını YukiAudioBus.tts'e koyar ve her
    bitiş yolunda (onended · stopAudio · hata) temizler.
  ⑤ Çeviri: yeni etiketler tr + en sözlüğünde.
"""
from __future__ import annotations

import re

from yardim import FRONTEND, sozluk, yorumsuz

SAHNE = FRONTEND / "modes" / "sohbet-sahne.js"
MOTOR = FRONTEND / "vendor" / "mesh-avatar" / "avatar.js"
RIG = FRONTEND / "assets" / "avatar" / "yuki"


def _sahne() -> str:
    return yorumsuz(SAHNE.read_text(encoding="utf-8"))


# ── ① paket ────────────────────────────────────────────────────────────────

def test_motor_ve_rig_yerinde():
    assert MOTOR.is_file()
    for yol in ("rig.json", "built/base.png", "built/layers.json", "built/sprites/sprites.json"):
        assert (RIG / yol).is_file(), f"Yuki rig'i eksik: {yol}"


def test_mit_bildirimi_dagitilan_dosyada():
    ilk = MOTOR.read_text(encoding="utf-8").splitlines()[0]
    assert ilk.startswith("/*!") and "MIT" in ilk, "MIT bildirimi avatar.js'in ilk satırı olmalı"
    lisans = (MOTOR.parent / "LICENSE").read_text(encoding="utf-8")
    assert lisans.startswith("MIT License")


def test_boyut_butcesi():
    """Kabul edilen bedel +1,6 MB (rapor #1). Sessizce büyümesin."""
    toplam = MOTOR.stat().st_size + sum(f.stat().st_size for f in RIG.rglob("*") if f.is_file())
    assert toplam <= 1_800_000, f"CANLI paketi {toplam} bayt — bütçe 1,8 MB"


def test_motor_kisisel_bagimlilik_tasimiyor():
    js = MOTOR.read_text(encoding="utf-8")
    for yasak in ("/home/", "ihsan", "localhost:8000", "codex"):
        assert yasak not in js.lower(), f"motor paketinde kişisel iz: {yasak}"


# ── ② kapılar ──────────────────────────────────────────────────────────────

def test_canli_kip_listede():
    assert re.search(r"KIPLER\s*=\s*\[\s*'video',\s*'resim',\s*'canli'\s*\]", _sahne())


def test_kapi_yalniz_yuki_ve_hafifte_kapali():
    js = _sahne()
    m = re.search(r"function canliMumkun\(\)\s*\{([^}]*)\}", js)
    assert m, "canliMumkun() yok — CANLI kapısı tek yerde olmalı"
    govde = m.group(1)
    assert "karakter() === 'yuki'" in govde, "CANLI yalnız Yuki'de (öbür karakterlerin rig'i yok)"
    assert "!hafifMi()" in govde, "HAFİF grafik kademesinde CANLI kapalı olmalı"
    assert re.search(r"function hafifMi\(\)\s*\{\s*return document\.documentElement\.getAttribute\('data-gfx'\) === 'hafif';", js)
    # Seçenek listesi kapıdan geçer; kip() yalnız listedekini kabul eder
    assert "if (canliMumkun()) l.push('canli');" in js
    assert "if (secenekler().indexOf(k) === -1) return;" in js


def test_kademe_degisince_yeniden_degerlenir():
    assert "document.addEventListener('gfxchange', kipUygula);" in _sahne()


def test_motor_kip_disinda_kapanir():
    js = _sahne()
    assert re.search(r"function canliEsitle\(\)\s*\{\s*if \(canliIstenir\(\)\)", js)
    assert "else canliKapat();" in js
    # GL bağlamı bırakılır: motorun kapat()'ı çağrılır, canvas DOM'dan çıkar
    assert "C.av.kapat()" in js and "C.canvas.remove()" in js


# ── ③ tembel yükleme ───────────────────────────────────────────────────────

def test_motor_tembel_yuklenir():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    sw = (FRONTEND / "sw.js").read_text(encoding="utf-8")
    assert "mesh-avatar" not in html, "motor index.html'den yüklenmemeli (dinamik import)"
    assert "mesh-avatar" not in yorumsuz(sw) and "assets/avatar" not in yorumsuz(sw)
    assert "import(AVATAR_JS)" in _sahne()


# ── ④ ses yolu ─────────────────────────────────────────────────────────────

def test_tts_analyser_veri_yolunda():
    core = yorumsuz((FRONTEND / "js" / "core.js").read_text(encoding="utf-8"))
    assert "window.YukiAudioBus = window.YukiAudioBus || { tts: null };" in core
    assert "window.YukiAudioBus.tts = analyser;" in core
    # onended · stopAudio · hata yolu — üçü de temizler (ölü düğüm okunmasın)
    assert core.count("window.YukiAudioBus.tts = null") >= 3


# ── ⑤ çeviri ───────────────────────────────────────────────────────────────

def test_etiketler_iki_sozlukte():
    for dil in ("tr", "en"):
        s = sozluk(dil)
        for a in ("sahne.kip.canli", "sahne.kip.canli-etiket"):
            assert s.get(a), f"{dil} sözlüğünde {a} yok"

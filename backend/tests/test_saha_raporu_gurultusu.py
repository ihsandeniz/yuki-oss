"""Müşterinin hata günlüğü, düzeltemeyeceği şeylerle dolmamalı.

🔴 SAHA RAPORU — 2026-08-02, gerçek Windows 10 (müşteri makinesi).
Müşteri hata günlüğünü paylaştı; içinde GERÇEK hataların yanında dört tane
"normal durum" WARNING olarak duruyordu:

    WARNING dbus_watcher — D-Bus (SYSTEM) bağlantısı kurulamadı:
                           module 'socket' has no attribute 'AF_UNIX'
    WARNING app.main     — AUTH_TOKEN boş — auth DEVRE DIŞI ... KRİTİK
    WARNING stt          — Silero yüklenemedi (No module named 'silero_vad')
    WARNING stt          — VoiceEmotion hata (No module named 'librosa')
    ERROR   websocket    — No audio was received. Please verify that your
                           parameters are correct.

Hiçbiri müşterinin düzeltebileceği bir şey değildi ve hiçbiri gerçek bir arıza
değildi:
  · D-Bus Linux teknolojisi — Windows'ta `AF_UNIX` yok, **denenmemeliydi bile**
  · AUTH_TOKEN masaüstünde bilerek boş — sunucu yalnız 127.0.0.1'e bağlı
  · silero_vad / librosa ürün paketine BİLEREK girmiyor (RMS ve neutral yedekleri var)
  · TTS hatası ise LLM boş cevap verince oluşuyordu → **hata, asıl hatayı gizliyordu**

Gürültü yalnız çirkin değil, TEHLİKELİ: gerçek arızayı gölgeliyor. Bu testler
bu satırların WARNING/ERROR seviyesine geri dönmesini engeller.
"""

import logging

import pytest

from app.services import dbus_watcher, stt, tts


# ── 1) D-Bus: Windows'ta hiç denenmemeli ────────────────────────────

def test_dbus_linux_disinda_desteklenmiyor(monkeypatch):
    for plat in ("win32", "darwin", "cygwin"):
        monkeypatch.setattr(dbus_watcher._sys, "platform", plat)
        assert not dbus_watcher.desteklenen_platform(), plat


def test_dbus_linuxta_destekleniyor(monkeypatch):
    monkeypatch.setattr(dbus_watcher._sys, "platform", "linux")
    assert dbus_watcher.desteklenen_platform()


@pytest.mark.asyncio
async def test_dbus_windowsta_task_ACMIYOR(monkeypatch, caplog):
    """Asıl regresyon: bağlantı denenmediği için uyarı da üretilmiyor."""
    monkeypatch.setattr(dbus_watcher._sys, "platform", "win32")
    monkeypatch.setattr(dbus_watcher, "_task", None)
    with caplog.at_level(logging.INFO):
        await dbus_watcher.start()
    assert dbus_watcher._task is None, "Windows'ta D-Bus task'ı açılmamalı"
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING], \
        "Windows'ta D-Bus için uyarı/hata basılmamalı"


# ── 2) TTS: boş metin bir hata değildir ─────────────────────────────

@pytest.mark.parametrize("metin", ["", "   ", "...", "!!!", "— …", "\n\t", "123", "?!.,;"])
def test_seslendirilecek_sey_yok(metin):
    assert not tts.seslendirilebilir_mi(metin)


@pytest.mark.parametrize("metin", ["merhaba", "a", "Yuki!", "2 kere", "こんにちは"])
def test_seslendirilebilir_metin(metin):
    assert tts.seslendirilebilir_mi(metin)


@pytest.mark.asyncio
async def test_bos_metin_TTS_katmanlarina_hic_gitmiyor(monkeypatch):
    """Edge TTS'in "No audio was received" hatası böyle doğuyordu."""
    cagrildi = []
    for ad in ("_synthesize_edge", "_synthesize_elevenlabs", "_synthesize_fish"):
        async def _sahte(t, _ad=ad):
            cagrildi.append(_ad)
            return b"ses"
        monkeypatch.setattr(tts, ad, _sahte)

    assert await tts.synthesize("   ...   ") == b""
    assert cagrildi == [], f"boş metin TTS katmanına gitti: {cagrildi}"


@pytest.mark.asyncio
async def test_bos_metin_akista_da_atlaniyor(monkeypatch):
    parcalar = [p async for p in tts.synthesize_streaming("  ")]
    assert parcalar == []


@pytest.mark.asyncio
async def test_dolu_metin_hala_seslendiriliyor(monkeypatch):
    """Yanlış negatif üretmediğimizi de göster."""
    async def _sahte_edge(t):
        return b"gercek-ses"
    monkeypatch.setattr(tts, "_synthesize_edge", _sahte_edge)
    monkeypatch.setattr(tts, "USE_FISH_TTS", False)
    monkeypatch.setattr(tts, "_elevenlabs_kapali_sebep", "test")
    assert await tts.synthesize("merhaba") == b"gercek-ses"


# ── 3) Eksik opsiyonel paketler: beklenen durum, uyarı değil ────────

def test_silero_yoksa_UYARI_basmiyor(monkeypatch, caplog):
    monkeypatch.setattr(stt, "_silero_model", None)
    monkeypatch.setattr(stt, "_silero_available", True)

    gercek_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def _yok(ad, *a, **k):
        if ad == "silero_vad":
            raise ModuleNotFoundError("No module named 'silero_vad'")
        return gercek_import(ad, *a, **k)

    monkeypatch.setattr("builtins.__import__", _yok)
    with caplog.at_level(logging.DEBUG):
        assert stt._get_silero_model() is None
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING], \
        "bilerek paketlenmemiş modül için WARNING basılmamalı"


def test_librosa_yoksa_UYARI_basmiyor_ve_neutral_donuyor(monkeypatch, caplog):
    gercek_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def _yok(ad, *a, **k):
        if ad == "librosa":
            raise ModuleNotFoundError("No module named 'librosa'")
        return gercek_import(ad, *a, **k)

    monkeypatch.setattr("builtins.__import__", _yok)
    with caplog.at_level(logging.DEBUG):
        sonuc = stt.analyze_voice_emotion(b"RIFF" + b"\x00" * 100)

    assert sonuc is not None, "None döndü — çağıran taraf patlar"
    assert sonuc.get("emotion") == "neutral"
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# ── 4) AUTH_TOKEN: yalnız gerçekten açıksa uyar ─────────────────────

def test_localhostta_auth_token_uyarisi_YOK(monkeypatch):
    from app.services import startup_validator as sv
    monkeypatch.setattr(sv, "AUTH_TOKEN", "")
    monkeypatch.setattr("app.config.HOST", "127.0.0.1")
    uyarilar = sv.validate_startup()
    assert not [u for u in uyarilar if "AUTH_TOKEN" in u], \
        "masaüstü müşterisi düzeltemeyeceği bir şey için korkutulmamalı"


def test_elevenlabs_yoksa_uyari_YOK(monkeypatch):
    """İsteğe bağlı premium TTS'in yokluğu arıza değil — ürün Edge TTS ile konuşur."""
    from app.services import startup_validator as sv
    monkeypatch.setattr(sv, "ELEVENLABS_API_KEY", "")
    uyarilar = sv.validate_startup()
    assert not [u for u in uyarilar if "ELEVENLABS" in u.upper()]


def test_gercek_eksik_hala_uyariyor(monkeypatch):
    """Gürültüyü kısarken GERÇEK uyarıları susturmadığımızı kanıtla.

    LLM anahtarı yoksa sohbet gerçekten çalışmaz → bu uyarı KALMALI.

    🔴 2026-08-28: Bu test aylarca kırmızıydı ve backlog'a **ürün kusuru** diye
    yazılmıştı (*"anahtarsız müşteri sebebini göremiyor"*). Ölçüldü: kusur üründe
    DEĞİL, testte. Uyarının koşulu `not OPENROUTER_API_KEY and not _yerel_secili`;
    test yalnız anahtarı boşaltıyor, sağlayıcıya dokunmuyordu. geliştiricinin kök
    `.env`'inde `LLM_PROVIDER=ollama` var → `_yerel_secili=True` → uyarı DOĞRU
    olarak susuyor (yerel modelde bulut anahtarı zaten gerekmez, 2026-08-08 kararı).
    Yani test **geliştirme makinesinin ayarını** ölçüyordu, müşterinin durumunu değil.

    📏 Ders: bir testin kırmızı olması ürünün bozuk olduğunu göstermez — testin
    neyi sabitlemediğine bak. Müşteri senaryosu burada açıkça kurulur.
    """
    from app.services import startup_validator as sv
    monkeypatch.setattr(sv, "OPENROUTER_API_KEY", "")
    # Müşteri senaryosu: bulut sağlayıcı seçili, anahtar yok.
    monkeypatch.setattr(sv, "USE_LOCAL_LLM", False)
    monkeypatch.setattr("app.config.LLM_PROVIDER", "openrouter")
    uyarilar = sv.validate_startup()
    assert [u for u in uyarilar if "OPENROUTER" in u.upper()], \
        "gerçek engelleyici eksik susturulmuş — gürültü temizliği fazla ileri gitmiş"


def test_yerel_saglayici_secilince_anahtar_uyarisi_YOK(monkeypatch):
    """Karşı kanat: Ollama seçen kullanıcı bulut anahtarına yönlendirilmemeli.

    Üstteki testin `LLM_PROVIDER`'ı sabitlemesi bu davranışı kazara ters
    çevirebilirdi; iki kanat birlikte kilitler.
    """
    from app.services import startup_validator as sv
    monkeypatch.setattr(sv, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(sv, "USE_LOCAL_LLM", False)
    monkeypatch.setattr("app.config.LLM_PROVIDER", "ollama")
    uyarilar = sv.validate_startup()
    assert not [u for u in uyarilar if "OPENROUTER" in u.upper()], \
        "yerel model seçen kullanıcı kaçındığı bulut anahtarına yönlendiriliyor"


def test_disa_acikken_auth_token_uyarisi_VAR(monkeypatch):
    from app.services import startup_validator as sv
    monkeypatch.setattr(sv, "AUTH_TOKEN", "")
    monkeypatch.setattr("app.config.HOST", "0.0.0.0")
    uyarilar = sv.validate_startup()
    assert [u for u in uyarilar if "AUTH_TOKEN" in u], \
        "gerçekten dışa açıkken uyarı KALKMAMALI (güvenlik)"

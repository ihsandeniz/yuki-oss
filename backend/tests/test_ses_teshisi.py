"""Ses yolu sessizce ölmemeli — her başarısızlık sebebini söylemeli.

🔴 2026-08-01: geliştiricinin Windows kurulumunda "konuşma algılanmıyor" şikâyeti geldi ve
elimizde HİÇBİR teşhis verisi yoktu. Sebep: backend üç ayrı noktada sessizce vazgeçiyor
(VAD reddi · wake-word yok · boş transkript), `stt_status()` de neden yüklenemediğini
saklamıyordu.

Ölçüm notu: "ffmpeg CLI Windows'ta yok → STT ölüyor" hipotezi **test edildi ve
çürütüldü** — faster-whisper webm'i PyAV ile kendi çözüyor (ffmpeg bloke edilerek
Linux'ta ölçüldü, transkript birebir aynı çıktı). ffmpeg eksikliğinin gerçek etkisi
`detect_speech`'in ham webm'i ayrıştıramayıp her sesi konuşma sayması.
"""

import pytest

from app.services import stt


@pytest.fixture(autouse=True)
def _stt_durumu_geri_al():
    onceki = (stt._model, stt._stt_available, stt._stt_last_error)
    yield
    stt._model, stt._stt_available, stt._stt_last_error = onceki


def test_status_yuklenemedi_sebebini_soyluyor(monkeypatch):
    monkeypatch.setattr(stt, "_model", None)
    monkeypatch.setattr(stt, "_stt_available", False)
    monkeypatch.setattr(stt, "_stt_last_error", "OSError: ctranslate2.dll bulunamadı")

    st = stt.stt_status()
    assert st["available"] is False
    assert "ctranslate2.dll" in st["last_error"]
    assert st["reason"], "kullanıcıya gösterilecek sebep boş olmamalı"
    assert "yüklenemedi" in st["reason"]


def test_model_yukleme_hatasi_kaydediliyor(monkeypatch):
    """Hata artık yalnız log'a değil, sorgulanabilir bir alana da yazılmalı."""
    monkeypatch.setattr(stt, "_model", None)
    monkeypatch.setattr(stt, "_stt_available", True)
    monkeypatch.setattr(stt, "_stt_last_error", "")

    def _patla(*a, **kw):
        raise OSError("ctranslate2.dll yüklenemedi")

    import sys, types
    sahte = types.ModuleType("faster_whisper")
    sahte.WhisperModel = _patla
    monkeypatch.setitem(sys.modules, "faster_whisper", sahte)

    assert stt._get_model() is None
    assert "ctranslate2.dll" in stt._stt_last_error
    assert stt.stt_status()["reason"]


def test_model_yokken_sebep_indirme_diyor(monkeypatch):
    monkeypatch.setattr(stt, "_model", None)
    monkeypatch.setattr(stt, "_stt_available", True)
    monkeypatch.setattr(stt, "_stt_last_error", "")
    monkeypatch.setattr(stt, "stt_model_present", lambda: False)

    assert "indirilmemiş" in stt.stt_status()["reason"]


def test_saglikliyken_sebep_bos(monkeypatch):
    monkeypatch.setattr(stt, "_stt_available", True)
    monkeypatch.setattr(stt, "stt_model_present", lambda: True)
    assert stt.stt_status()["reason"] == ""


def test_ffmpeg_cli_durumu_raporlaniyor():
    """Windows'ta False bekleniyor — VAD'ın fiilen kapalı olduğunu görebilmeliyiz."""
    st = stt.stt_status()
    assert "ffmpeg_cli" in st
    assert isinstance(st["ffmpeg_cli"], bool)


def test_ensure_wav_ffmpegsiz_cokmez(monkeypatch):
    """ffmpeg yoksa (Windows) ham bytes dönmeli, exception fırlatmamalı."""
    def _yok(cmd, *a, **kw):
        raise FileNotFoundError(2, "No such file or directory: 'ffmpeg'")

    monkeypatch.setattr(stt.subprocess, "run", _yok)
    ham = b"\x1a\x45\xdf\xa3sahte-webm-verisi"
    assert stt.ensure_wav(ham) == ham


def test_detect_speech_cozulemeyen_seste_konusma_varsayar(monkeypatch):
    """Güvenli fallback: ayrıştıramıyorsak sesi ATMA (yoksa kullanıcı duyulmaz)."""
    def _yok(cmd, *a, **kw):
        raise FileNotFoundError(2, "No such file or directory: 'ffmpeg'")

    monkeypatch.setattr(stt.subprocess, "run", _yok)
    assert stt.detect_speech(b"\x1a\x45\xdf\xa3sahte-webm-verisi") is True


@pytest.mark.asyncio
async def test_stt_status_ucu_teshis_donduruyor(client):
    r = await client.get("/api/stt/status")
    assert r.status_code == 200
    d = r.json()
    for alan in ("available", "model_present", "loaded", "reason", "ffmpeg_cli"):
        assert alan in d, f"teşhis alanı eksik: {alan}"


def test_status_model_indirilemediyse_sistem_kutuphanesi_demez(monkeypatch):
    """Ağsız ilk açılışta gerçek hata buydu; eskiden 'eksik sistem kütüphanesi' deniyordu."""
    monkeypatch.setattr(stt, "_model", None)
    monkeypatch.setattr(stt, "_stt_available", False)
    monkeypatch.setattr(stt, "_stt_last_error",
                        "LocalEntryNotFoundError: Got: ConnectError: [Errno 111] Connection refused\n"
                        "An error happened while trying to locate the files on the Hub")
    st = stt.stt_status()
    assert "indirilemedi" in st["reason"]
    assert "kütüphane" not in st["reason"]

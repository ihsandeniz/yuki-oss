"""Ses dönüştürme, müşteri makinesinde ffmpeg OLMADAN çalışmak ZORUNDA.

🔴 SAHA RAPORU — 2026-08-02, gerçek Windows 10 (müşteri makinesi):
    ensure_wav dönüştürme hatası ([WinError 2] Sistem belirtilen dosyayı bulamıyor)
    VAD/RMS ayrıştırma hatası (file does not start with RIFF id), konuşma varsayılıyor

`ensure_wav` TEK yol olarak `ffmpeg` CLI'ını çağırıyordu. Müşteri paketinde
ffmpeg.exe **yok** (`win-unpacked/ffmpeg.dll` Electron'un medya kütüphanesidir,
subprocess ile çağrılamaz) → dönüşüm patlıyor → ham webm geri dönüyor →
`_detect_speech_rms` onu ayrıştıramayıp **"konuşma varsayılıyor"** diyor
= sunucu tarafı VAD fiilen devre dışı.

ÖLÇÜLDÜ (ffmpeg PATH'ten tamamen kaldırılarak):
    girdi          HAM webm    WAV (yeni)   doğru
    konuşma        True        True         True
    SESSİZLİK      True ❌     False ✅     False

Çözüm ffmpeg.exe paketlemek DEĞİL (≈80 MB): PyAV zaten pakette (faster-whisper
onu getiriyor, iki bundle'da da 18.0.0) → dönüşüm Python içinde, boyut artışı SIFIR.

⚠️ Bu testler fixture'ı **PyAV ile kendisi üretir** → ffmpeg gerektirmez, yani
CI'da ve ffmpeg'siz makinelerde de gerçekten koşar (atlanmaz).
"""

import io
import shutil
import wave

import numpy as np
import pytest

from app.services import stt

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _uret(kodek: str, kap: str, genlik: int, saniye: float = 1.0, hz: int = 48000) -> bytes:
    """Tarayıcının ürettiğine benzer ses üret — ffmpeg CLI'sız, PyAV ile."""
    import av

    buf = io.BytesIO()
    c = av.open(buf, "w", format=kap)
    s = c.add_stream(kodek, rate=hz)
    s.layout = "mono"
    n = int(hz * saniye)
    t = np.arange(n, dtype=np.float64) / hz
    dalga = (np.sin(2 * np.pi * 440 * t) * genlik).astype(np.int16).reshape(1, -1)
    # Opus 20 ms'lik kareler ister
    adim = hz // 50
    for i in range(0, n - adim + 1, adim):
        kare = av.AudioFrame.from_ndarray(
            np.ascontiguousarray(dalga[:, i:i + adim]), format="s16", layout="mono"
        )
        kare.rate = hz
        for p in s.encode(kare):
            c.mux(p)
    for p in s.encode(None):
        c.mux(p)
    c.close()
    return buf.getvalue()


@pytest.fixture
def ffmpegsiz(monkeypatch):
    """ffmpeg'i erişilemez yap — müşteri Windows'unun koşulu.

    ⚠️ PATH'i boşaltmak yetmez ve yanıltır (ledger: test/izole-path-eksik-komut).
    `shutil.which` ve `subprocess.run` doğrudan kesiliyor ki ffmpeg yolu
    gerçekten kapansın; ayrıca kapandığı test içinde doğrulanıyor.
    """
    monkeypatch.setattr(shutil, "which", lambda ad, *a, **k: None)

    def _yok(*a, **k):
        raise FileNotFoundError(2, "Sistem belirtilen dosyayı bulamıyor")

    monkeypatch.setattr(stt.subprocess, "run", _yok)
    assert shutil.which("ffmpeg") is None
    return True


def _wav_oku(veri: bytes):
    with wave.open(io.BytesIO(veri)) as w:
        return w.getnchannels(), w.getframerate(), w.getsampwidth(), w.getnframes()


# ── Dönüşüm: ffmpeg olmadan ─────────────────────────────────────────

@pytest.mark.parametrize("kodek,kap", [("libopus", "webm"), ("aac", "mp4")])
def test_ffmpegsiz_wav_uretiliyor(ffmpegsiz, kodek, kap):
    """Asıl regresyon: WinError 2 yolunda artık WAV çıkmalı."""
    ham = _uret(kodek, kap, genlik=8000)
    cikti = stt.ensure_wav(ham)
    assert cikti[:4] == b"RIFF", f"{kap}: ffmpeg yokken WAV üretilemedi"
    kanal, hz, genislik, kare = _wav_oku(cikti)
    assert (kanal, hz, genislik) == (1, stt.WAV_HEDEF_HZ, 2)
    assert kare > 0


def test_wav_girdi_aynen_donuyor(ffmpegsiz):
    """Zaten WAV olan veri yeniden kodlanmamalı."""
    wav = stt.ensure_wav(_uret("libopus", "webm", genlik=8000))
    assert stt.ensure_wav(wav) == wav


def test_bos_girdi_cokmez(ffmpegsiz):
    assert stt.ensure_wav(b"") == b""


def test_bozuk_girdi_cokmez_ham_doner(ffmpegsiz):
    """Çözülemeyen veri istisna fırlatmamalı — ses hattı düşmemeli."""
    bozuk = b"\x00\x01\x02bunlar ses degil" * 20
    assert stt.ensure_wav(bozuk) == bozuk


# ── Asıl kazanç: sunucu tarafı VAD geri geliyor ─────────────────────

def test_sessizlik_ham_webmde_KONUSMA_sanılıyor(ffmpegsiz):
    """Kusurun kendisi — dönüştürülmemiş veri RMS katmanını kandırıyor."""
    sessiz = _uret("libopus", "webm", genlik=0)
    assert stt._detect_speech_rms(sessiz, stt.VAD_THRESHOLD) is True


def test_sessizlik_donusturulunce_dogru_bulunuyor(ffmpegsiz):
    """Düzeltmenin kazancı: aynı veri WAV'a çevrilince sessizlik anlaşılıyor."""
    sessiz = _uret("libopus", "webm", genlik=0)
    wav = stt.ensure_wav(sessiz)
    assert wav[:4] == b"RIFF"
    assert stt._detect_speech_rms(wav, stt.VAD_THRESHOLD) is False


def test_konusma_hala_konusma(ffmpegsiz):
    """Yanlış negatif üretmediğimizi de göster (yalnız mutlu yol yetmez)."""
    ses = _uret("libopus", "webm", genlik=12000)
    wav = stt.ensure_wav(ses)
    assert stt._detect_speech_rms(wav, stt.VAD_THRESHOLD) is True


def test_detect_speech_uctan_uca(ffmpegsiz, monkeypatch):
    """`detect_speech` kendi içinde ensure_wav çağırıyor — zincir bütün mü?

    ⚠️ Bu testi yazarken ilk sürümü kusurluydu: `detect_speech(ham)` ile
    `detect_speech(wav)` karşılaştırılmıştı, ama detect_speech ZATEN ensure_wav
    çağırdığı için iki kol da aynı yoldan geçiyordu — aynı şey iki kez ölçülmüştü.
    Farkı görmek için RMS katmanına DOĞRUDAN vermek gerekiyor (yukarıdaki testler).

    ⚠️ 2026-11-02: Silero kapatılıyor. Ortamda torch + Silero varsa saf ton
    (genlik=12000) "konuşma değil" çıkıyor — Silero haklı, test RMS yolunu
    varsayıyordu. Ürün kutusunda torch yok; burada ölçülen zincir ensure_wav → RMS.
    """
    monkeypatch.setattr(stt, "_get_silero_model", lambda: None)
    assert stt.detect_speech(_uret("libopus", "webm", genlik=12000)) is True
    assert stt.detect_speech(_uret("libopus", "webm", genlik=0)) is False

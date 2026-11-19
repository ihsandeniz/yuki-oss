"""Speech-to-Text — faster-whisper wrapper + VAD + wake-word + voice emotion.

Faz D:
  detect_speech()        : Enerji tabanlı VAD (sessiz ses → False, konuşma → True)
  check_wake_word()      : Wake-word kontrolü ("yuki" / "hey yuki"), WAKE_WORD_ENABLED=false
Faz H:
  analyze_voice_emotion(): librosa ile ses tonu analizi → kural tabanlı duygu sınıflaması
"""

from __future__ import annotations

import io
import logging
import os
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

from app.config import WHISPER_MODEL, WHISPER_BEAM_SIZE, WAKE_WORD_ENABLED, VAD_THRESHOLD, VAD_SILERO_THRESHOLD, WAKE_WORDS, get_lang_config
from app.mesajlar import M

# Whisper initial_prompt — dile göre tanıma sapması için ipucu sözcükleri
_STT_INITIAL_PROMPT = {
    "tr": (
        "Yuki, Claude, prompt, Python, kod, terminal, Kitty, Arch Linux, "
        "yapay zeka, asistan, script, bash, pip, git, dosya, dizin, "
        "OpenRouter, GPT, Whisper, model, API, backend, frontend"
    ),
    "ja": "ユキ、クロード、パイソン、ターミナル、アシスタント、コード、ファイル、AI",
}

logger = logging.getLogger(__name__)


WAV_HEDEF_HZ = 16000


def _wav_paketle(pcm: bytes, hz: int = WAV_HEDEF_HZ) -> bytes:
    """Ham PCM16 mono → WAV konteyneri (stdlib `wave`, ek bağımlılık yok)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)          # s16
        w.setframerate(hz)
        w.writeframes(pcm)
    return buf.getvalue()


def _wav_pyav(audio_bytes: bytes) -> bytes:
    """webm/opus · mp4/aac · ogg → WAV PCM16 mono 16kHz — TAMAMEN Python içinde.

    PyAV (`av`) faster-whisper'ın zaten getirdiği bir bağımlılık ve HER İKİ
    bundle'da da mevcut (linux + win, 18.0.0) → harici ikili gerekmez.
    """
    import av  # bundle'da var; yoksa çağıran tarafta yakalanır
    import numpy as np

    kap = av.open(io.BytesIO(audio_bytes))
    try:
        if not kap.streams.audio:
            raise ValueError("ses akışı yok")  # i18n-istisna: iç hata, yalnız log'a düşer (ensure_wav yutar)
        rs = av.AudioResampler(format="s16", layout="mono", rate=WAV_HEDEF_HZ)
        parcalar = []
        for kare in kap.decode(audio=0):
            for yeniden in rs.resample(kare):
                parcalar.append(yeniden.to_ndarray())
        for yeniden in rs.resample(None):   # resampler'ı boşalt (son kısmi kare)
            parcalar.append(yeniden.to_ndarray())
    finally:
        kap.close()

    if not parcalar:
        raise ValueError("çözülen ses boş")  # i18n-istisna: iç hata, yalnız log'a düşer (ensure_wav yutar)
    pcm = np.concatenate(parcalar, axis=1).astype("<i2")
    return _wav_paketle(pcm.tobytes())


def _wav_ffmpeg(audio_bytes: bytes) -> bytes:
    """Yedek yol: ffmpeg CLI. Geliştirme makinelerinde var, kullanıcı paketinde YOK."""
    suffix = ".mp4" if len(audio_bytes) > 8 and audio_bytes[4:8] == b"ftyp" else ".webm"
    inp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    out_path = inp.name + ".wav"
    try:
        inp.write(audio_bytes)
        inp.close()
        subprocess.run(
            ["ffmpeg", "-y", "-i", inp.name, "-ar", str(WAV_HEDEF_HZ), "-ac", "1",
             "-sample_fmt", "s16", "-f", "wav", out_path],
            capture_output=True, timeout=5, check=True,
        )
        with open(out_path, "rb") as f:
            veri = f.read()
        if not veri:
            raise ValueError("ffmpeg boş çıktı üretti")  # i18n-istisna: iç hata, yalnız log'a düşer (ensure_wav yutar)
        return veri
    finally:
        Path(inp.name).unlink(missing_ok=True)
        Path(out_path).unlink(missing_ok=True)


def ensure_wav(audio_bytes: bytes) -> bytes:
    """Ses verisini WAV PCM16 mono 16kHz formatına çevir.

    🔴 2026-08-02 — SAHA RAPORU (gerçek Windows 10, kullanıcı makinesi):
        ensure_wav dönüştürme hatası ([WinError 2] Sistem belirtilen dosyayı bulamıyor)
        VAD/RMS ayrıştırma hatası (file does not start with RIFF id), konuşma varsayılıyor

    Eski kod TEK yol olarak `ffmpeg` CLI'ını çağırıyordu. **Kullanıcı paketinde
    ffmpeg.exe YOK** (`win-unpacked/ffmpeg.dll` Electron'un medya kütüphanesidir,
    subprocess ile çağrılamaz) → WinError 2 → ham webm geri dönüyor → `detect_speech`
    onu ayrıştıramayıp **her sesi konuşma sayıyor** = sunucu tarafı VAD fiilen
    devre dışı.

    Çözüm ffmpeg.exe paketlemek DEĞİL (≈80 MB): **PyAV zaten pakette** —
    faster-whisper onu getiriyor, iki bundle'da da 18.0.0 kurulu. Dönüşüm artık
    Python içinde yapılıyor, boyut artışı SIFIR ve harici ikiliye bağımlılık yok.

    Sıra: PyAV (birincil) → ffmpeg CLI (geliştirme yedeği) → orijinal bytes.
    """
    if audio_bytes[:4] == b"RIFF":
        return audio_bytes
    if not audio_bytes:
        return audio_bytes

    try:
        return _wav_pyav(audio_bytes)
    except Exception as e:
        logger.debug("PyAV ile dönüştürülemedi (%s), ffmpeg CLI deneniyor.", e)

    try:
        return _wav_ffmpeg(audio_bytes)
    except Exception as e:
        logger.warning(
            "ensure_wav: ses WAV'a çevrilemedi (PyAV ve ffmpeg ikisi de başarısız: %s). "
            "Ham veri döndürülüyor — sunucu tarafı VAD bu kayıtta çalışmayacak.", e
        )
        return audio_bytes

_model = None
_stt_available = True   # native DLL (ctranslate2) yüklenemezse False'a düşer → bir daha deneme yok
_stt_last_error: str = ""   # neden yüklenemedi — kullanıcıya gösterilebilsin diye saklanır


def ffmpeg_cli_var() -> bool:
    """`ffmpeg` çalıştırılabiliri PATH'te mi?

    ⚠️ Windows paketinde YOK: `win-unpacked/ffmpeg.dll` Electron'un kendi medya
    kütüphanesidir, subprocess ile çağrılamaz.

    ✅ 2026-08-02'den beri BU BİR SORUN DEĞİL: `ensure_wav` dönüşümü PyAV ile
    Python içinde yapıyor, ffmpeg yalnız geliştirme yedeği. Fonksiyon teşhis
    amacıyla duruyor — "ffmpeg yok" artık "VAD kapalı" demek DEĞİLDİR.
    """
    import shutil
    return shutil.which("ffmpeg") is not None


def _get_model():
    """faster-whisper modelini lazy-load et.

    STT opsiyoneldir: bazı platformlarda native bağımlılık (ctranslate2.dll ve CUDA/cuDNN
    türevleri) yüklenemeyebilir. O durumda None döner ve çağıran taraf sesle-yazmayı atlar —
    exception fırlatıp backend'i çökertmez. Silero VAD'daki degrade deseniyle aynı.
    """
    global _model, _stt_available, _stt_last_error
    if _model is None:
        if not _stt_available:
            return None
        try:
            from faster_whisper import WhisperModel
            _model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
            _stt_last_error = ""
        except Exception as e:
            _stt_available = False
            # Sebebi SAKLA: eskiden yalnız log'a yazılıyordu, kullanıcı ekranında
            # "hiçbir şey olmuyor" görünüyordu. Windows'ta ctranslate2.dll
            # yüklenememesi tam olarak bu sessizliği üretiyor.
            _stt_last_error = f"{type(e).__name__}: {e}"
            logger.warning("STT (faster-whisper) yüklenemedi — sesle yazma devre dışı: %s", e)
            return None
    return _model


# ------------------------------------------------------------------ #
# İndir-gerektiğinde: model varlık kontrolü + durum + reset
# ------------------------------------------------------------------ #

def _whisper_cache_dirname() -> str:
    """WHISPER_MODEL için HF-cache klasör adı (models--Org--Repo)."""
    if "/" in WHISPER_MODEL:
        return "models--" + WHISPER_MODEL.replace("/", "--")
    return f"models--Systran--faster-whisper-{WHISPER_MODEL}"


def stt_model_present() -> bool:
    """Whisper modeli diskte mevcut mu? (yüklemeden/indirmeden kontrol — HF_HOME'a bakar)."""
    if _model is not None:
        return True
    hf_home = os.environ.get("HF_HOME") or os.environ.get("HUGGINGFACE_HUB_CACHE") or ""
    if not hf_home:
        return False
    base = Path(hf_home)
    dirname = _whisper_cache_dirname()
    # HUGGINGFACE_HUB_CACHE zaten .../hub olabilir; HF_HOME ise .../hub ekler → ikisini de dene
    for c in (base, base / "hub"):
        snap = c / dirname / "snapshots"
        try:
            if snap.is_dir() and any(snap.iterdir()):
                return True
        except OSError:
            continue
    return False


def reset_stt() -> None:
    """STT modül durumunu sıfırla — yeni indirilen model tam restart olmadan devreye girsin."""
    global _model, _stt_available
    _model = None
    _stt_available = True


# Model ilk açılışta Hugging Face'ten iner; ağ/erişim hatası "eksik sistem kütüphanesi" diye
# gösterilince kullanıcı yanlış şeyi arıyordu (ağsız makinede ölçüldü).
_INDIRME_IZLERI = ("LocalEntryNotFoundError", "ConnectError", "ConnectionError", "ConnectTimeout",
                   "HfHubHTTPError", "403 Forbidden", "Name or service not known",
                   "Temporary failure in name resolution", "internet connection")


def _indirme_hatasi(hata: str) -> bool:
    return any(iz in (hata or "") for iz in _INDIRME_IZLERI)


def stt_status() -> dict:
    """STT durum raporu (frontend indirme akışı + Windows teşhisi için).

    `reason` alanı 2026-08-01'de eklendi: geliştiricinin Windows kurulumunda "konuşma
    algılanmıyor" şikâyeti geldiğinde elimizde hiçbir teşhis verisi yoktu — ürün
    başarısızlığı sessizce yutuyordu.
    """
    mevcut = stt_model_present()
    if not _stt_available and _indirme_hatasi(_stt_last_error):
        reason = M("stt.model-indirilemedi", ayrinti=_stt_last_error)
    elif not _stt_available:
        reason = M("stt.motor-yuklenemedi", ayrinti=_stt_last_error or M("stt.bilinmiyor"))
    elif not mevcut:
        reason = M("stt.model-yok")
    else:
        reason = ""
    return {
        "available": _stt_available,        # native runtime (ctranslate2) yüklenebiliyor mu
        "model_present": mevcut,
        "loaded": _model is not None,
        "model_id": "whisper-small",         # models-manifest.json id'si ile eşleşir
        "last_error": _stt_last_error,
        "ffmpeg_cli": ffmpeg_cli_var(),      # False → sunucu tarafı VAD devre dışı (Windows)
        "reason": reason,
    }


# ------------------------------------------------------------------ #
# D1: VAD — Silero ONNX (birincil) + RMS enerji (fallback)
# ------------------------------------------------------------------ #

_silero_model = None
_silero_available = True


def _get_silero_model():
    """Silero VAD ONNX modelini lazy-load et."""
    global _silero_model, _silero_available
    if _silero_model is not None:
        return _silero_model
    if not _silero_available:
        return None
    try:
        from silero_vad import load_silero_vad
        _silero_model = load_silero_vad(onnx=True)
        logger.info("Silero ONNX modeli yüklendi.")
        return _silero_model
    except ModuleNotFoundError:
        # 🔴 2026-08-02: silero_vad ürün paketine BİLEREK girmiyor (torch ~2 GB).
        # RMS yedeği bu durum için yazıldı → bu bir arıza değil, tasarım.
        # Eskiden WARNING basıyordu ve kullanıcının paylaştığı hata günlüğünde
        # gerçek hataların arasına karışıp onları gölgeliyordu.
        logger.info("Silero VAD pakette yok (beklenen) — RMS sessizlik algılama kullanılacak.")
        _silero_available = False
        return None
    except Exception as e:
        logger.warning("Silero yüklenemedi (%s), RMS fallback kullanılacak.", e)
        _silero_available = False
        return None


def _detect_speech_silero(audio_bytes: bytes) -> bool | None:
    """Silero VAD ile konuşma tespiti. Başarısızsa None döner (fallback'e geç)."""
    model = _get_silero_model()
    if model is None:
        return None
    try:
        import numpy as np
        import torch

        with io.BytesIO(audio_bytes) as buf:
            with wave.open(buf) as wf:
                sr = wf.getframerate()
                n_frames = wf.getnframes()
                if n_frames == 0:
                    return False
                raw = wf.readframes(n_frames)

        # int16 → float32 normalize
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

        # Silero 16kHz bekler — gerekirse resample
        if sr != 16000:
            target_len = int(len(samples) * 16000 / sr)
            indices = np.linspace(0, len(samples) - 1, target_len).astype(int)
            samples = samples[indices]

        # 512 sample'lık chunk'larda prob hesapla, max al
        tensor = torch.from_numpy(samples)
        chunk_size = 512
        max_prob = 0.0
        model.reset_states()
        for i in range(0, len(tensor), chunk_size):
            chunk = tensor[i:i + chunk_size]
            if len(chunk) < chunk_size:
                # Kısa son chunk'ı pad et
                chunk = torch.nn.functional.pad(chunk, (0, chunk_size - len(chunk)))
            prob = model(chunk, 16000).item()
            max_prob = max(max_prob, prob)

        logger.debug("VAD/Silero max_prob=%.4f (threshold=%.2f)", max_prob, VAD_SILERO_THRESHOLD)
        return max_prob > VAD_SILERO_THRESHOLD

    except Exception as e:
        logger.warning("VAD/Silero hata (%s), fallback'e geçiliyor.", e)
        return None


def _detect_speech_rms(audio_bytes: bytes, threshold: float) -> bool:
    """RMS enerji tabanlı VAD (fallback)."""
    try:
        with io.BytesIO(audio_bytes) as buf:
            with wave.open(buf) as wf:
                n_frames = wf.getnframes()
                if n_frames == 0:
                    return False
                raw = wf.readframes(n_frames)
                n_samples = len(raw) // 2
                if n_samples == 0:
                    return False
                samples = struct.unpack(f"<{n_samples}h", raw[:n_samples * 2])
                rms = (sum(s * s for s in samples) / n_samples) ** 0.5
                normalized = rms / 32768.0
                logger.debug("VAD/RMS energy=%.4f threshold=%s", normalized, threshold)
                return normalized > threshold
    except Exception as e:
        logger.warning("VAD/RMS ayrıştırma hatası (%s), konuşma varsayılıyor.", e)
        return True


def detect_speech(audio_bytes: bytes, threshold: float | None = None) -> bool:
    """Ses verisinde konuşma var mı kontrol et.

    Önce Silero ONNX VAD dener; başarısızsa RMS enerji tabanlı fallback.
    Ayrıştırma başarısız olursa True döner (güvenli fallback).

    threshold: RMS fallback için normalize edilmiş eşik (0.0–1.0).
    """
    audio_bytes = ensure_wav(audio_bytes)
    # Silero VAD (birincil)
    result = _detect_speech_silero(audio_bytes)
    if result is not None:
        return result

    # RMS fallback
    th = threshold if threshold is not None else VAD_THRESHOLD
    return _detect_speech_rms(audio_bytes, th)


# ------------------------------------------------------------------ #
# D3: Wake-word — STT sonrası keyword kontrolü
# ------------------------------------------------------------------ #


def wake_word_acik() -> bool:
    """Uyandırma kelimesi filtresi şu an açık mı — CANLI okunur.

    🔴 2026-08-05: bu değer modül-tepesindeki `WAKE_WORD_ENABLED` sabitinden
    okunuyordu. O sabit import anında donuyor; ⚙ AYAR → Mikrofon → "Uyandırma
    Kelimesi" anahtarı `config.user.json`'a yazıp `cfg` global'ini tazeliyor ama
    **buraya hiç ulaşmıyordu** → kullanıcı ayarı açıyor, hiçbir şey değişmiyor,
    ancak yeniden başlatınca etkili oluyordu. Aynı sınıf hata BYOK anahtarında
    da vardı (`llm_router` import anında donmuş anahtarla istemci kuruyordu).
    """
    from app import config as _cfg
    return bool(getattr(_cfg, "WAKE_WORD_ENABLED", WAKE_WORD_ENABLED))


def _wake_words() -> list[str]:
    from app import config as _cfg
    return list(getattr(_cfg, "WAKE_WORDS", WAKE_WORDS))


def check_wake_word(text: str) -> bool:
    """Transkripsiyon metninde wake-word var mı kontrol et.

    Filtre kapalıysa (varsayılan) her zaman True → gelen her cümle yanıtlanır.
    Açıksa "yuki" / "hey yuki" / "ey yuki" aranır.

    ⚠️ Arama bilerek **alt-dize** (kelime sınırı değil): ses tanıma Türkçe ekleri
    kesik ya da kesme işaretsiz yazabiliyor ("Yuki'ye" → "yukiye"). Wake-word'de
    yanlış-pozitif (gereksiz yanıt) yanlış-negatifden (kullanıcıyı duymamak)
    daha ucuzdur.
    """
    if not wake_word_acik():
        return True

    lower = text.lower().strip()
    for ww in _wake_words():
        if ww in lower:
            logger.info("Wake-word algılandı: '%s'", ww)
            return True

    logger.debug("Wake-word algılanamadı: '%s'", text)
    return False


def strip_wake_word(text: str) -> str:
    """Transkripsiyon metninden wake-word'ü temizle.

    "Hey Yuki müziği durdur" → "müziği durdur"
    Wake-word yoksa veya devre dışıysa metin aynen döner.
    """
    if not wake_word_acik():
        return text

    import re
    result = text
    for ww in sorted(_wake_words(), key=len, reverse=True):
        # Büyük/küçük harf duyarsız, etrafındaki boşlukları da temizle
        result = re.sub(rf'(?i)\b{re.escape(ww)}\b[,\s]*', '', result, count=1)
    return result.strip() or text


# ------------------------------------------------------------------ #
# H2: Ses Duygu Analizi — kural tabanlı (LLM çağrısı yok)
# ------------------------------------------------------------------ #

_EMOTION_FALLBACK = {"emotion": "neutral", "energy": 0.5, "pitch": 150.0, "spectral_centroid": 0.0}


def analyze_voice_emotion(audio_bytes: bytes) -> dict:
    """WAV bytes → {"emotion": str, "energy": float, "pitch": float, "spectral_centroid": float}

    Çıkarılan özellikler (librosa):
    - RMS energy        : düşük → tired/calm, yüksek → excited/angry
    - Pitch (F0)        : düşük → tired/sad, yüksek → happy/excited
    - Spectral centroid : düşük → calm/sad, yüksek → anxious/excited

    Kural tabanlı sınıflama (genişletilmiş):
    - energy > 0.7 ve pitch > 200Hz                    → "excited"
    - energy < 0.25 ve pitch < 120Hz                   → "tired"
    - energy > 0.6 ve pitch < 150Hz                    → "angry"
    - energy < 0.35 ve centroid < 2000Hz               → "calm"
    - energy > 0.5 ve centroid > 3500Hz ve pitch > 180 → "anxious"
    - diğer                                             → "neutral"

    Hata durumunda → fallback neutral döner.
    """
    try:
        import io as _io
        import librosa
        import numpy as np

        audio_bytes = ensure_wav(audio_bytes)
        y, sr = librosa.load(_io.BytesIO(audio_bytes), sr=None, mono=True)
        if len(y) == 0:
            return _EMOTION_FALLBACK

        # RMS energy (normalize 0-1)
        rms = float(librosa.feature.rms(y=y).mean())
        max_rms = float(np.abs(y).max()) + 1e-9
        energy = min(1.0, rms / max_rms)

        # Pitch (F0 mean Hz)
        pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
        valid_pitches = pitches[magnitudes > magnitudes.mean()]
        pitch = float(valid_pitches.mean()) if len(valid_pitches) > 0 else 150.0

        # Spectral centroid (Hz) — ses "parlaklığı"
        centroid = float(librosa.feature.spectral_centroid(y=y, sr=sr).mean())

        # Kural tabanlı sınıflama (genişletilmiş)
        if energy > 0.7 and pitch > 200:
            emotion = "excited"
        elif energy < 0.25 and pitch < 120:
            emotion = "tired"
        elif energy > 0.6 and pitch < 150:
            emotion = "angry"
        elif energy < 0.35 and centroid < 2000:
            emotion = "calm"
        elif energy > 0.5 and centroid > 3500 and pitch > 180:
            emotion = "anxious"
        else:
            emotion = "neutral"

        logger.debug("VoiceEmotion energy=%.3f pitch=%.1fHz centroid=%.0fHz → %s", energy, pitch, centroid, emotion)
        return {"emotion": emotion, "energy": energy, "pitch": pitch, "spectral_centroid": centroid}

    except ModuleNotFoundError:
        # librosa ürün paketine BİLEREK girmiyor (silinen özellik bağımlılığı).
        # Ses duygu analizi yoksa "neutral" doğru cevaptır — arıza değil.
        logger.info("Ses duygu analizi pakette yok (beklenen) — neutral kullanılıyor.")
        return _EMOTION_FALLBACK
    except Exception as e:
        logger.warning("VoiceEmotion hata (%s), neutral döndürülüyor.", e)
        return _EMOTION_FALLBACK


# ------------------------------------------------------------------ #
# Transcribe
# ------------------------------------------------------------------ #


async def transcribe(audio_bytes: bytes, language: str | None = None) -> str:
    """Transcribe audio bytes to text. Accepts WAV/MP3/OGG/WebM.

    language=None → aktif asistan dilini (tr/ja) otomatik kullanır.
    """
    lang_cfg = get_lang_config()
    lang = language or lang_cfg["whisper"]
    model = _get_model()
    if model is None:
        # STT bu platformda kullanılamıyor (native DLL yok) → sessiz degrade: boş transkript.
        # Çağıranlar (voice.py / websocket.py) boş metni "konuşma algılanmadı" gibi ele alır.
        return ""

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        segments, info = model.transcribe(
            tmp_path,
            language=lang,
            beam_size=max(WHISPER_BEAM_SIZE, 3),
            condition_on_previous_text=False,
            temperature=0,
            no_speech_threshold=0.6,
            compression_ratio_threshold=2.4,
            vad_filter=True,
            initial_prompt=_STT_INITIAL_PROMPT.get(lang, _STT_INITIAL_PROMPT["tr"]),
        )
        text = " ".join(seg.text.strip() for seg in segments)
        # Hallucination filter: çok kısa çıktı genellikle uydurma
        if len(text.strip()) < 2:
            return ""
        return text
    finally:
        Path(tmp_path).unlink(missing_ok=True)

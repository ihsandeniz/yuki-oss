"""config_manager.py — Kullanıcı ayarlarını kalıcı sakla (config.user.json).

Tasarım:
  - config.py .env'den varsayılanları yükler; bu modül kullanıcı override'larını
    `backend/config.user.json`'a yazar.
  - config.py SONUNDA `apply_overrides()` benzeri overlay yapar (ALLOWED_KEYS ile
    sınırlı) → restart'ta tüm ayarlar uygulanır.
  - settings_api.py runtime'da set_value() çağırır + canlı uygulanabilen 3 ayar
    (llm/dil/persona) için kendi setter'larını kullanır; gerisi restart ister.

Güvenlik: yalnızca ALLOWED_KEYS içindeki anahtarlar yazılabilir/overlay edilir
(API key'ler, DATABASE_URL, AUTH_TOKEN gibi gizli/altyapı değerleri DIŞARIDA).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Ayar dosyası — YAZILABİLİR dizinde olmak ZORUNDA.
#
# 🐞 2026-07-31: burası `backend/config.user.json`e sabitlenmişti. Geliştirmede sorun
# yok ama SATILAN pakette `backend/` AppImage'ın squashfs'i = **salt okunur** →
# kullanıcının ⚙ AYAR'dan yaptığı HİÇBİR değişiklik kaydedilmiyordu
# (`[Errno 30] Read-only file system`, gerçek mount'ta ölçüldü). Sessiz değildi ama
# kimse denememişti. config.py'nin DATA_DIR deseni burada da uygulanır:
# YUKI_DATA_DIR (Electron'un userData'sı) → yazılabilir.
_SETTINGS_DIR = Path(os.getenv("YUKI_DATA_DIR") or Path(__file__).resolve().parents[1])
CONFIG_USER_PATH = Path(
    os.getenv("CONFIG_USER_PATH") or str(_SETTINGS_DIR / "config.user.json")
)

# UI'dan değiştirilebilen config.py global'leri (tip ipuçlarıyla doğrulama için).
# Buraya EKLENMEYEN hiçbir anahtar overlay edilmez/yazılmaz → gizli değerler korunur.
ALLOWED_KEYS: dict[str, type] = {
    # LLM / Zeka
    "USE_LOCAL_LLM": bool,
    "PROMPT_CACHE_ENABLED": bool,
    "SUMMARIZE_ENABLED": bool,
    "LLM_MODEL_FAST": str,
    "LLM_MODEL_STRONG": str,
    "VISION_MODEL": str,
    # Ses & TTS
    "USE_FISH_TTS": bool,
    "USE_ELEVENLABS_TTS": bool,
    "EDGE_VOICE_RATE": str,
    "EDGE_VOICE_PITCH": str,
    # 🔴 2026-09-18 (FAZ 0): asistan dili buraya EKLENMEMİŞTİ. Kullanıcı dili
    # değiştiriyor, backend yeniden başlayınca `.env`/`tr`'ye dönüyordu — yani
    # "dil seçimi" aslında oturumluktu. Yazma yolu: `config.set_language()` (tek kapı — bak oraya).
    "ASSISTANT_LANGUAGE": str,
    # Arayüz dili (tr/en) — konuşma dilinden AYRI eksen (2026-10-04). Yazma yolu:
    # `config.set_arayuz_dili()`; genel ayar ucu reddeder (`settings_api.AYRI_KAPILI`).
    "ARAYUZ_DILI": str,
    # Karakter başına Edge TTS sesi — JSON harita: {"yuki": "tr-TR-AhmetNeural", …}
    # Boş/eksik anahtar = "dil varsayılanını kullan". 2026-09-18 (FAZ 0, A6):
    # seçici arayüzde vardı ama seçim yalnız localStorage'a yazılıyordu, okuyan yoktu.
    "PERSONA_VOICES": str,
    # Mikrofon / VAD / STT
    "WAKE_WORD_ENABLED": bool,
    "VAD_THRESHOLD": float,
    "VAD_SILERO_THRESHOLD": float,
    "WHISPER_MODEL": str,
    "WHISPER_BEAM_SIZE": int,
    # Hafıza
    "MEMORY_RECENT_LIMIT": int,
    "MEMORY_SEARCH_LIMIT": int,
    "MEMORY_MIN_SIMILARITY": float,
    # Algı & Gizlilik
    "BROWSER_ENABLED": bool,
    "AMBIENT_ENABLED": bool,
    "AMBIENT_MODE": str,
    "AMBIENT_INTERVAL": int,
    "EYE_TRACKING_ENABLED": bool,
    "EYE_TRACKING_FPS": int,
    "EYE_TRACKING_CAMERA": int,
    "DBUS_ENABLED": bool,
    "MEDIA_CONTROL_ENABLED": bool,
    # Zamanlayıcı
    "SCHEDULER_ENABLED": bool,
    # Mod başlatıcı
    "MODE_LAUNCHER_ENABLED": bool,
    # Masaüstü Yuki (services/masaustu_yuki.py)
    "MASAUSTU_YUKI": bool,
    "MASAUSTU_VRM": str,
    # Fitnes (PLAN › FİTNES) — varsayılan kapalı, HQ › Sistem anahtarıyla açılır (g4, 2026-11-12).
    # Atölye BURADA DEĞİL: yalnız `.env`.
    "FITNES": bool,
    # Sesli konuşmada dolgu sesi (services/dolgu_sesi.py) — varsayılan kapalı.
    "DOLGU_SESI": bool,
    # Companion ekibi (2026-08-14, R5 FAZ 2) — meclisin model-isteği maliyeti.
    # Ücretsiz kotadaki kullanıcı 2/2'ye çeker, kredili anahtarı olan 4/4 kullanır.
    "COUNCIL_MAX_TASKS": int,
    "WORKER_MAX_STEPS": int,
    # Yerel ağa açma (2026-10-01). 🔴 Panel 4'te GÖRÜNMEZ ve `POST /api/settings/AG_ACIK` ile YAZILAMAZ:
    # tek yazma kapısı `PUT /api/devices/ag` — uygulama kilidi şartını orası uygular (settings_api reddeder).
    "AG_ACIK": bool,
    # Cihaz ajanının riskli eylemleri (2026-11-01) — varsayılan KAPALI. 🔴 Genel uçtan YAZILAMAZ:
    # tek yazma kapısı `PUT /api/devices/izinler`, açmak `AUTH_TOKEN` ister (`services/cihaz_yetki.py`).
    "CIHAZ_IZIN_DOSYA_YAZ": bool,
    "CIHAZ_IZIN_DOSYA_SIL": bool,
    "CIHAZ_IZIN_SUREC_KAPAT": bool,
}

_cache: dict[str, Any] | None = None


def _coerce(key: str, value: Any) -> Any:
    """Değeri ALLOWED_KEYS'teki tipe çevir (UI'dan string gelebilir)."""
    typ = ALLOWED_KEYS.get(key)
    if typ is None:
        return value
    try:
        if typ is bool:
            if isinstance(value, str):
                return value.strip().lower() in ("true", "1", "yes", "on", "evet")
            return bool(value)
        if typ is int:
            return int(value)
        if typ is float:
            return float(value)
        if typ is str:
            return str(value)
    except (ValueError, TypeError):
        pass
    return value


def load() -> dict[str, Any]:
    """config.user.json → {KEY: value}. Yalnızca ALLOWED_KEYS döner. mtime cache yok
    (dosya küçük); her çağrıda okunur ki API kaydından sonra tutarlı olsun."""
    global _cache
    if not CONFIG_USER_PATH.exists():
        _cache = {}
        return {}
    try:
        with open(CONFIG_USER_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        out: dict[str, Any] = {}
        for k, v in (data or {}).items():
            if k in ALLOWED_KEYS:
                out[k] = _coerce(k, v)
        _cache = out
        return out
    except Exception as e:
        log.error("config.user.json okunamadı (%s): %s", CONFIG_USER_PATH, e)
        return {}


def get(key: str, default: Any = None) -> Any:
    return load().get(key, default)


def set_value(key: str, value: Any) -> tuple[bool, str]:
    """Tek ayarı config.user.json'a yaz (atomic + tek yedek). (ok, mesaj)."""
    if key not in ALLOWED_KEYS:
        from app.mesajlar import M
        return False, M("ayar.izinsiz-anahtar", anahtar=key)
    coerced = _coerce(key, value)
    try:
        data: dict[str, Any] = {}
        if CONFIG_USER_PATH.exists():
            try:
                with open(CONFIG_USER_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
            except Exception:
                # bozuk dosya → yedekle, sıfırdan başla
                shutil.copy2(CONFIG_USER_PATH, str(CONFIG_USER_PATH) + ".corrupt")
                data = {}
        # tek yedek (rolling)
        if CONFIG_USER_PATH.exists():
            shutil.copy2(CONFIG_USER_PATH, str(CONFIG_USER_PATH) + ".backup")
        data[key] = coerced
        tmp = str(CONFIG_USER_PATH) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_USER_PATH)
        global _cache
        _cache = None
        log.info("Ayar kaydedildi: %s = %r", key, coerced)
        return True, "ok"
    except Exception as e:
        log.error("set_value(%s) başarısız: %s", key, e)
        return False, str(e)


def sil(key: str) -> tuple[bool, str]:
    """Tek ayarın panel kaydını kaldır → .env / config.py varsayılanı (HQ "varsayılana dön").
    Kayıt yoksa da başarılı sayılır. (ok, mesaj)."""
    if key not in ALLOWED_KEYS:
        from app.mesajlar import M
        return False, M("ayar.izinsiz-anahtar", anahtar=key)
    global _cache
    try:
        if not CONFIG_USER_PATH.exists():
            return True, "ok"
        with open(CONFIG_USER_PATH, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        if key not in data:
            return True, "ok"
        shutil.copy2(CONFIG_USER_PATH, str(CONFIG_USER_PATH) + ".backup")
        data.pop(key, None)
        tmp = str(CONFIG_USER_PATH) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_USER_PATH)
        _cache = None
        log.info("Ayar varsayılana döndü: %s", key)
        return True, "ok"
    except Exception as e:
        log.error("sil(%s) başarısız: %s", key, e)
        return False, str(e)


# Sıfırlamanın DOKUNMADIĞI kayıtlar (iki dil ekseni de — 2026-10-04). 🔴 2026-09-27: önizleme "dil korunur" diyordu ama
# `reset()` dosyanın tamamını siliyordu → yeniden başlatınca dil `.env`'e dönüyor,
# karakter sesi seçimleri (PERSONA_VOICES) kayboluyordu. İkisi de ayar değil kişisel
# seçim; önizleme ve reset artık bu TEK listeden okur.
SIFIRLAMADA_KORUNAN = frozenset({"ASSISTANT_LANGUAGE", "ARAYUZ_DILI", "PERSONA_VOICES"})


def reset() -> bool:
    """Panel kayıtlarını sil → ayarlar .env varsayılanlarına döner (restart sonrası).
    `SIFIRLAMADA_KORUNAN` kayıtları kalır."""
    global _cache
    try:
        if CONFIG_USER_PATH.exists():
            shutil.copy2(CONFIG_USER_PATH, str(CONFIG_USER_PATH) + ".backup")
            with open(CONFIG_USER_PATH, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            kalan = {k: v for k, v in data.items() if k in SIFIRLAMADA_KORUNAN}
            if kalan:
                tmp = str(CONFIG_USER_PATH) + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(kalan, f, indent=2, ensure_ascii=False)
                os.replace(tmp, CONFIG_USER_PATH)
            else:
                CONFIG_USER_PATH.unlink()
        _cache = None
        log.info("config.user.json sıfırlandı")
        return True
    except Exception as e:
        log.error("reset başarısız: %s", e)
        return False

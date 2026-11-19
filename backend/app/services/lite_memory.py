"""Yuki Lite Memory — pgvector'süz kalıcı hafıza (paketli/bedava sürüm).

İki katman:
1. Sohbet geçmişi kalıcılığı: llm._histories → DATA_DIR/chat_history.json.
   Uygulama kapanıp açılınca karakter başına son MAX_HISTORY mesaj geri yüklenir.
2. Profil özeti (orta seviye hafıza): her PROFILE_UPDATE_EVERY kullanıcı mesajında
   LLM, mevcut özet + son geçmişten tek paragraflık "kullanıcı hakkında bilinenler"
   özetini günceller → DATA_DIR/user_profile.json. Sistem prompt'una enjekte edilir.

MEMORY_ENABLED=True (pgvector) ise profil katmanı devre dışı — tam semantik hafıza
kullanılır; geçmiş kalıcılığı her durumda çalışır. LLM çağrısı llm.quick_ask ile
yapılır (BYOK); anahtar yoksa sessizce atlanır (fail-open).
"""

import json
import logging
import os
from pathlib import Path

from app.config import DATA_DIR

logger = logging.getLogger("yuki.lite_memory")

_HISTORY_FILE = DATA_DIR / "chat_history.json"
_PROFILE_FILE = DATA_DIR / "user_profile.json"

# Kaç kullanıcı mesajında bir profil özeti güncellensin
PROFILE_UPDATE_EVERY = 10


# ------------------------------------------------------------------ #
# Dosya yardımcıları
# ------------------------------------------------------------------ #


def _read(path: Path) -> dict:
    """Dosyayı sözlük olarak oku. Bozuksa (yarım JSON · geçersiz UTF-8 · sözlük değil)
    önce `.bozuk-<zaman>` kopyası alınır, sonra `{}` döner.

    🔴 Eskiden kopyasız `{}` dönüyordu: ardından gelen ilk `save_history` dosyayı yalnız o
    anki karakterle yeniden yazıyor, okunamayan geçmişin TAMAMI sessizce gidiyordu.
    Geçersiz UTF-8 (`UnicodeDecodeError`) ise hiç yakalanmıyor, mesaj kaydını düşürüyordu.
    """
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        sebep: Exception = ValueError(f"sözlük değil: {type(data).__name__}")
    except OSError as e:
        logger.warning("lite_memory okuma hatası (%s): %s", path.name, e)
        return {}
    except ValueError as e:          # JSONDecodeError + UnicodeDecodeError
        sebep = e
    _bozugu_sakla(path, sebep)
    return {}


def _bozugu_sakla(path: Path, sebep: Exception) -> None:
    import shutil
    import time
    yedek = path.with_name(f"{path.name}.bozuk-{time.strftime('%Y%m%d-%H%M%S')}")
    try:
        if not yedek.exists():
            shutil.copy2(path, yedek)
        logger.error("lite_memory: %s okunamadı (%s) — kopyası %s; yeni kayıt boş başlıyor",
                     path.name, sebep, yedek.name)
    except OSError as e:
        logger.error("lite_memory: bozuk %s yedeklenemedi (%s)", path.name, e)


def _write_atomic(path: Path, data: dict) -> None:
    # Atomik yazma: temp dosyaya yaz + os.replace (aynı FS'te atomik) → yarım yazma/bozulma olmaz.
    try:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("lite_memory yazma hatası (%s): %s", path.name, e)


# ------------------------------------------------------------------ #
# 1) Sohbet geçmişi kalıcılığı
# ------------------------------------------------------------------ #


def load_history(character_key: str) -> list[dict]:
    """Karakterin diske yazılmış geçmişini döndür (yoksa boş liste)."""
    raw = _read(_HISTORY_FILE).get(character_key, [])
    if not isinstance(raw, list):
        return []
    return [
        {"role": m["role"], "content": m["content"]}
        for m in raw
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
    ]


def save_history(character_key: str, history: list[dict]) -> None:
    data = _read(_HISTORY_FILE)
    data[character_key] = history
    _write_atomic(_HISTORY_FILE, data)


def clear_history(character_key: str) -> None:
    data = _read(_HISTORY_FILE)
    if character_key in data:
        del data[character_key]
        _write_atomic(_HISTORY_FILE, data)


# ------------------------------------------------------------------ #
# 2) Profil özeti (orta seviye hafıza)
# ------------------------------------------------------------------ #


def get_profile(character_key: str) -> str:
    entry = _read(_PROFILE_FILE).get(character_key, {})
    return entry.get("summary", "") if isinstance(entry, dict) else ""


def set_profile(character_key: str, summary: str) -> None:
    data = _read(_PROFILE_FILE)
    entry = data.get(character_key)
    if not isinstance(entry, dict):
        entry = {}
    entry["summary"] = summary.strip()
    data[character_key] = entry
    _write_atomic(_PROFILE_FILE, data)


def note_user_message(character_key: str) -> bool:
    """Kullanıcı mesajı sayacını artır; PROFILE_UPDATE_EVERY'e ulaşınca True döner (özet zamanı)."""
    data = _read(_PROFILE_FILE)
    entry = data.get(character_key)
    if not isinstance(entry, dict):
        entry = {}
    count = int(entry.get("msg_count", 0)) + 1
    due = count >= PROFILE_UPDATE_EVERY
    entry["msg_count"] = 0 if due else count
    data[character_key] = entry
    _write_atomic(_PROFILE_FILE, data)
    return due


def build_profile_prompt(prev_summary: str, history: list[dict]) -> str:
    """quick_ask'e verilecek özet-güncelleme promptu."""
    lines = []
    for m in history:
        who = "Kullanıcı" if m["role"] == "user" else "Yuki"
        lines.append(f"{who}: {m['content'][:400]}")
    convo = "\n".join(lines[-24:])
    prev = prev_summary.strip() or "(henüz yok)"
    from app.config import yanit_dili
    return (
        "Aşağıda kullanıcı hakkında mevcut kalıcı özet ve son konuşma var. "
        "Özeti güncelle: kullanıcının adı, tercihleri, ilgi alanları, devam eden işleri gibi "
        "KALICI bilgileri koru/ekle; geçici gündelik detayları alma. "
        f"En fazla 120 kelime, tek paragraf; dil: {yanit_dili()}. SADECE özeti döndür.\n\n"
        f"## Mevcut özet\n{prev}\n\n## Son konuşma\n{convo}"
    )

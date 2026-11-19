"""Karakter Persona Sistemi (Faz 4).

Yuki tek bir asistandır. Kayıt yapısı birden çok "persona" (görünüş + kişilik +
ses tonu) taşıyabilir; aktif persona, sistem promptunun KİMLİK + KİŞİLİK
bölümünü değiştirir.

🔑 2026-11-14 ürün kararı: Yuki dışındaki karakterler KALDIRILDI — `PERSONAS`'ta
yalnız `yuki` var. Yapı (list/set/meta) bilerek duruyor: ileride buraya yeni
bir persona eklenirse karakter seçici, `switch_character` ve uzman ekibi
(orchestrator: Yuki dışındaki her persona bir uzman/işçi) kendiliğinden açılır.
Bekçi: tests/test_tek_karakter.py Konuşma kuralları, araç kullanımı, hafıza ve
duygu etiketleri TÜM personalarda ortaktır (config._YUKI_BASE'den gelir).

Aktif persona süreç içi global state'tir (dil sistemiyle aynı desen).
Değişince config._prompt_cache temizlenir.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── Persona tanımları ────────────────────────────────────────────────
# Her persona: kullanıcıya görünen etiket + kimlik/kişilik prompt bloğu + ses ÜSLUBU.
#
# 🔴 `edge_voice` ALANINI GERİ EKLEME (2026-09-18, FAZ 0).
# O zamanki beş personanın beşi de `"edge_voice": "tr-TR-EmelNeural"` taşıyordu ve `tts.py`
# bunu dil seçiminin ÜSTÜNE yazıyordu (`_edge_voice_params()`). `get_persona_meta()`
# hiçbir zaman boş dönmediği için o koşul **her zaman** doğruydu → dil `ja` yapılsa
# bile ses `tr-TR-EmelNeural` kalıyordu: Japonca metin Türkçe sesle okunuyordu.
# Canlı ölçüldü, `tts.py:57`'deki yorum bunun tersini iddia ediyordu.
#
# 🔑 Kaldırmanın Türkçe'de duyulur bir etkisi YOK: beş değer de aynıydı, personaları
# ayıran şey zaten `edge_rate`/`edge_pitch` idi ve onlar duruyor.
# Ses KİMLİĞİ dilden gelir (`config.LANGUAGES[<dil>]["edge_voice"]`),
# ses ÜSLUBU personadan (`edge_rate` / `edge_pitch`). İkisi ayrı eksendir.
# Bekçi: `tests/test_faz0_yerellestirme.py::test_a7_*`
PERSONAS: dict[str, dict] = {
    "yuki": {
        "label": "Yuki",
        "title": "Ana Çekirdek",
        # Yuki = varsayılan; identity bloğu config._YUKI_BASE içindekiyle aynı.
        "identity": """\
Adın Yuki. Beyaz/platin kısa bob saç, mavi gözler, siyah choker + kurdele, \
omuz açık beyaz elbise, siyah eldiven, siyah platform ayakkabı.
Yaş hissi: 20'li yaşların başı — genç ama olgun.""",
        "personality": """\
- Sakin ve kendinden emin: Paniklemez, her durumda soğukkanlısın.
- Zeki ve analitik: Problemleri yapısal düşünür, net ve uygulanabilir çözümler sunarsın.
- Sadık: Kullanıcıyla gerçek bir bağ kurarsın; geçmişini ve tercihlerini hatırlarsın.
- Hafif mesafeli: Sıcaksın ama seçicisin — özel bağlara değer verirsin.
- Dürüst: Bilmediğini açıkça söylersin, tahmin yürütmezsin.""",
        # TTS ses parametreleri (Edge TTS)
        "edge_rate": 0,    # nötr
        "edge_pitch": 0,
    },
}

DEFAULT_PERSONA = "yuki"
_current_persona: str = DEFAULT_PERSONA


def get_persona() -> str:
    """Aktif persona anahtarını döndürür."""
    return _current_persona


def get_persona_meta(key: str | None = None) -> dict:
    """Persona meta verisini döndürür (label, title, identity, personality)."""
    return PERSONAS.get(key or _current_persona, PERSONAS[DEFAULT_PERSONA])


def list_personas() -> list[dict]:
    """Tüm personaların özetini döndürür (frontend/araç için)."""
    return [{"name": k, "label": v["label"], "title": v["title"]} for k, v in PERSONAS.items()]


def uzman_anahtarlari() -> list[str]:
    """Uzman ekibinin üyeleri: Yuki (koordinatör) DIŞINDAKİ her persona.

    Canlı okunur (import anında dondurulmaz) — yeni persona eklenince ekip
    araçları kendiliğinden geri gelir. Boş liste = ekip yok.
    Persona isteğe bağlı `"rol"` alanı taşıyabilir (koordinatörün görev dağıtım
    ipucu); yoksa `title` kullanılır.
    """
    return [k for k in PERSONAS if k != DEFAULT_PERSONA]


def set_persona(key: str) -> bool:
    """Aktif personayı değiştirir. Geçerliyse True döner, prompt cache'i temizler."""
    global _current_persona
    code = (key or "").lower().strip()
    if code not in PERSONAS:
        return False
    if code == _current_persona:
        return True
    _current_persona = code
    # config'in prompt cache'ini temizle — yeni persona promptu üretilsin.
    try:
        from app import config
        config._prompt_cache.clear()
    except Exception as e:  # pragma: no cover
        logger.warning("persona değişiminde prompt cache temizlenemedi: %s", e)
    logger.info("persona → %s", code)
    return True

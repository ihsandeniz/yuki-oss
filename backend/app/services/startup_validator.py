"""Startup validation — kritik ve opsiyonel env var kontrolü.

Lifespan başında çağrılır. Kritik eksiklik → RuntimeError, opsiyonel → warning.
"""

from __future__ import annotations

import logging

from app.config import (
    OPENROUTER_API_KEY,
    USE_LOCAL_LLM,
    ELEVENLABS_API_KEY,
    DATABASE_URL,
    MEMORY_BACKEND,
    MEMORY_ENABLED,
    BROWSER_ENABLED,
    AUTH_TOKEN,
)
from app.mesajlar import M

logger = logging.getLogger(__name__)


def validate_startup() -> list[str]:
    """Kritik ve opsiyonel env var'ları kontrol et.

    Kritik eksiklik varsa RuntimeError fırlatır.
    Opsiyonel eksiklikler warning listesi olarak döner.
    """
    warnings: list[str] = []

    # LLM API anahtarı — BYOK ürün: anahtar yoksa app YİNE açılır (kullanıcı
    # ⚙ AYAR → ANAHTAR sihirbazından girer). Fail-fast yerine warning; yoksa
    # sihirbaza hiç ulaşılamazdı. Sohbet, anahtar girilene kadar çalışmaz.
    # Yerel sağlayıcı (Ollama) seçiliyse anahtar zaten gerekmez — uyarı vermek
    # kullanıcıyı kaçındığı bulut anahtarına yönlendirirdi (2026-08-08).
    from app.config import LLM_PROVIDER as _LLM_PROVIDER
    from app.services import llm_providers as _lp
    _yerel_secili = USE_LOCAL_LLM or _lp.yerel_mi(_LLM_PROVIDER) or _LLM_PROVIDER == "chatgpt"
    # Anahtar SEÇİLİ sağlayıcınınkine bakılır: Anthropic/OpenAI anahtarı girilmişken
    # "OPENROUTER_API_KEY yok" demek kullanıcıyı ihtiyacı olmayan bir anahtara yollardı.
    _secili = _LLM_PROVIDER or _lp.VARSAYILAN
    _sag = _lp.kayit(_secili)
    if not _yerel_secili:
        if _sag is None or _sag.kimlik == _lp.VARSAYILAN:
            if not OPENROUTER_API_KEY:
                warnings.append(M("acilis.anahtar-yok"))
        elif not _lp.anahtar(_sag.kimlik):
            warnings.append(M("llm.secim-anahtar-yok", ad=_sag.ad))

    # Opsiyonel: TTS
    # 🔴 2026-08-02 saha raporu: bu satır kullanıcının hata günlüğünde WARNING olarak
    #    duruyordu. Oysa ElevenLabs **isteğe bağlı, kullanıcının kendi getireceği**
    #    bir premium seçenek; ürün Edge TTS ile eksiksiz konuşuyor. Yani HER kullanıcıda
    #    görünen, hiçbir şeyin bozuk olmadığını anlatan bir "uyarı"ydı.
    if not ELEVENLABS_API_KEY:
        logger.info("ElevenLabs anahtarı yok (isteğe bağlı) — Edge TTS kullanılacak.")

    # Opsiyonel: Hafıza — uyarı BACKEND'e göre. Üründe varsayılan `sqlite`
    # (gömülü, kurulum yok) → DATABASE_URL zaten gerekmez; eskiden bu dalda da
    # "DATABASE_URL ayarlanmamış" yazıp hafıza kapalıymış gibi görünüyordu.
    if MEMORY_BACKEND == "sqlite":
        pass  # gömülü sqlite-vec: ek yapılandırma gerekmez, uyarı da gerekmez
    elif not DATABASE_URL:
        warnings.append(M("acilis.hafiza-kapali"))

    # Opsiyonel: Browser
    if BROWSER_ENABLED:
        try:
            import playwright  # noqa: F401
        except ImportError:
            warnings.append(M("acilis.playwright-yok"))

    # Opsiyonel: AUTH_TOKEN
    #
    # 🔴 2026-08-02 saha raporu (Windows 10, kullanıcı): her açılışta hata günlüğüne
    #    "AUTH_TOKEN boş — auth DEVRE DIŞI ... KRİTİK" düşüyordu. Masaüstü kullanıcısı
    #    için bu **normal ve doğru** yapılandırma: sunucu 127.0.0.1'e bağlı, dışarıya
    #    hiç açık değil. Kullanıcıyı düzeltemeyeceği (ve düzeltmesi gerekmeyen) bir şey
    #    için "KRİTİK" diye korkutmak, gerçek hataları da gölgeliyordu.
    #    Uyarı artık YALNIZCA sunucu gerçekten dışarı açıkken veriliyor.
    if not AUTH_TOKEN:
        from app.config import HOST
        disa_acik = HOST not in ("127.0.0.1", "localhost", "::1")
        if disa_acik:
            warnings.append(M("acilis.auth-acik", host=HOST))
        else:
            logger.info(
                "AUTH_TOKEN boş — masaüstü kullanımında normal (sunucu yalnız %s'e "
                "bağlı, dışarıdan erişilemez).", HOST
            )

    return warnings

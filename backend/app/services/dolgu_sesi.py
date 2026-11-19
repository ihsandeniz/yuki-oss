"""Dolgu sesi: model geç cevap verince Yuki'nin kısa bir "hmm" demesi.

Varsayılan KAPALI. Ayarlar:
  DOLGU_SESI=1          açar — tek kaynak `app.config.DOLGU_SESI` (`.env` ya da HQ › Ses anahtarı, canlı)
  DOLGU_GECIKME_MS=1200 ilk gerçek ses bu sürede gitmezse dolgu çalar (0,3-5 sn arası)
  DOLGU_METNI=Hmm.      seslendirilecek kısa metin

Ses hattına tek noktadan bağlanır: `async with dolgu_sesi.tur(ws): …` turun LLM+TTS bölümünü
sarar. Blok süresince `ws.send_json` gözlenir; `dolgu` işaretsiz ilk `audio`/`audio_chunk`
gidince zamanlayıcı iptal olur. Blok bitince zamanlayıcı durur, `send_json` eski hâline döner.

🔴 Dolgu cevabı BEKLETMEZ: ses önbellekte yoksa o tur dolgu çalınmaz; sentez arka planda bir kez
yapılır, sonraki turlar kullanır. Sentez hatası turu bozmaz (Yuki dolgusuz konuşur).
Gönderilen mesaj normal ses mesajıdır: {"type": "audio", "data", "text": "", "dolgu": true}.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import os
from typing import AsyncIterator, Callable

logger = logging.getLogger(__name__)

_onbellek: dict[str, bytes] = {}
_isitma: asyncio.Task | None = None
_SES_TIPLERI = ("audio", "audio_chunk")


def acik() -> bool:
    """Tek kaynak `app.config.DOLGU_SESI` (ortam + HQ ayarı); her turda okunur → anahtar canlı."""
    from app import config as _config
    return getattr(_config, "DOLGU_SESI", False) is True


def gecikme_sn() -> float:
    try:
        ms = float(os.getenv("DOLGU_GECIKME_MS", "1200"))
    except ValueError:
        ms = 1200.0
    return min(5.0, max(0.3, ms / 1000.0))


def metin() -> str:
    return (os.getenv("DOLGU_METNI") or "").strip() or "Hmm."


def _varsayilan_sentez(m: str):
    from app.services.tts import synthesize_streaming
    return synthesize_streaming(m)


def _isit(sentezle: Callable[[str], AsyncIterator[bytes]]) -> None:
    """Önbellek boşsa arka planda tek sentez görevi başlat (zaten koşuyorsa dokunma)."""
    global _isitma
    if _isitma is not None and not _isitma.done():
        return
    m = metin()

    async def _kos():
        try:
            parcalar = [p async for p in sentezle(m)]
            if parcalar:
                _onbellek[m] = b"".join(parcalar)
        except Exception as e:
            logger.warning("Dolgu sesi hazırlanamadı (%s); dolgusuz devam", e)

    _isitma = asyncio.create_task(_kos())


def isit(sentezle: Callable[[str], AsyncIterator[bytes]] | None = None) -> None:
    """Bağlantı açılışında çağrılır: dolgu açıksa ve önbellek boşsa sesi arka planda hazırla →
    ilk sesli tur da dolgulu olabilir. Kapalıyken hiçbir şey yapmaz, hata bağlantıyı bozmaz."""
    try:
        if acik() and _onbellek.get(metin()) is None:
            _isit(sentezle or _varsayilan_sentez)
    except Exception as e:  # noqa: BLE001
        logger.debug("Dolgu ısınması başlatılamadı: %s", e)


@contextlib.asynccontextmanager
async def tur(ws, sentezle: Callable[[str], AsyncIterator[bytes]] | None = None):
    """Bir konuşma turunu sarar; açıksa ve cevap gecikirse bir kez dolgu gönderir."""
    if not acik():
        yield
        return
    ses = _onbellek.get(metin())
    if ses is None:
        _isit(sentezle or _varsayilan_sentez)
        yield
        return

    asil = ws.send_json
    ornekte_vardi = "send_json" in getattr(ws, "__dict__", {})
    ses_gitti = asyncio.Event()

    async def _gozleyen(mesaj, *a, **k):
        if isinstance(mesaj, dict) and mesaj.get("type") in _SES_TIPLERI and not mesaj.get("dolgu"):
            ses_gitti.set()
        return await asil(mesaj, *a, **k)

    async def _zamanlayici():
        try:
            await asyncio.wait_for(ses_gitti.wait(), timeout=gecikme_sn())
            return                                   # cevap zamanında geldi
        except asyncio.TimeoutError:
            pass
        try:
            await asil({"type": "audio", "data": base64.b64encode(ses).decode("ascii"),
                        "text": "", "dolgu": True})
        except Exception as e:                       # bağlantı koptuysa asıl tur zaten bitecek
            logger.debug("Dolgu gönderilemedi: %s", e)

    ws.send_json = _gozleyen
    gorev = asyncio.create_task(_zamanlayici())
    try:
        yield
    finally:
        gorev.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await gorev
        # Sınıf yöntemiyse örnek özniteliğini sil (sınıfınki geri gelir); örnekte zaten
        # atanmış bir işlev idiyse onu geri koy.
        if ornekte_vardi:
            ws.send_json = asil
        else:
            del ws.send_json

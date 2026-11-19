"""API hata yanıtları — kullanıcıya ham teknik metin GÖSTERİLMEZ.

Sorun (2026-08-04'te ölçüldü): lisans/anahtar panelleri yalnız **mutlu yolu** ve
`ok:false` yolunu insanca anlatıyordu. İki yol açıktaydı:

- **500** → FastAPI düz metin `Internal Server Error` döner. Frontend `r.json()`
  yapıyor, bu patlıyor, `catch` bloğu `String(e)`'yi basıyor → kullanıcı
  *"SyntaxError: Unexpected token 'I', \"Internal S\"... is not valid JSON"* görüyor.
- **429** → slowapi `{"error": "Rate limit exceeded: 10 per 1 minute"}` döner.
  Frontend `d.ok` yok diye bunu **geçersiz lisans** sanıp ham İngilizce metni basıyor.
  Bu yalnız çirkin değil **yanlış teşhis**: kullanıcı sağlam anahtarını çöpe atar.
  (ElevenLabs 401 dersinin birebir aynısı: kota ≠ geçersiz anahtar.)

Sözleşme: her hata yanıtı `{"ok": false, "error": "<insanca metin>", "kod": "<makine>"}`.
`kod` frontend'in tonu seçmesi için (uyarı mı, hata mı); metin kullanıcı için.
Teknik ayrıntı yanıta DEĞİL, hata günlüğüne gider (🩺 SAĞLIK → 📋 KOPYALA).

── 2026-09-18 (FAZ 3) ──────────────────────────────────────────────────────
Metinler artık gömülü DEĞİL, `app.mesajlar` kataloğundan geliyor. Bu dosya
i18n'in "iki global işleyici" ayağıydı; katalog geldiğinde ilk bağlanan da o
oldu, çünkü **her uçtan** çıkabilen tek iki metin bunlar.
"""
from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.mesajlar import M, Mc

log = logging.getLogger(__name__)

KOD_HIZ_SINIRI = "hiz_siniri"
KOD_BEKLENMEYEN = "beklenmeyen"


def _saniye_ayikla(detay: str) -> int | None:
    """"10 per 1 minute" → 60. Anlaşılmazsa None (metin genel kalır)."""
    birimler = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
    parcalar = str(detay).split()
    for i, p in enumerate(parcalar):
        birim = p.rstrip("s").lower()
        if birim in birimler:
            sayi = 1
            if i > 0 and parcalar[i - 1].isdigit():
                sayi = int(parcalar[i - 1])
            return sayi * birimler[birim]
    return None


def hiz_siniri_yaniti(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """429 — "çok hızlı denedin", ASLA "geçersiz anahtar" değil."""
    saniye = _saniye_ayikla(getattr(exc, "detail", ""))
    # `Mc` çoğulu dile bırakır: TR'de "5 dakika", EN'de "5 minutes" — sayıyı
    # metne f-string ile yapıştırmak İngilizce'de "5 minute" üretirdi.
    if saniye and saniye >= 60:
        ne_kadar = Mc("hata.sure-dakika", saniye // 60)
    elif saniye:
        ne_kadar = Mc("hata.sure-saniye", saniye)
    else:
        ne_kadar = M("hata.sure-kisa")
    yanit = JSONResponse(
        status_code=429,
        content={
            "ok": False,
            "kod": KOD_HIZ_SINIRI,
            "error": M("hata.hiz-siniri", ne_kadar=ne_kadar),
        },
    )
    # slowapi'nin X-RateLimit-* başlıkları korunur (istemci ne zaman deneyeceğini bilsin)
    try:
        yanit = request.app.state.limiter._inject_headers(
            yanit, request.state.view_rate_limit
        )
    except Exception:  # noqa: BLE001 — başlık kozmetik, yanıtı düşürmesin
        pass
    if saniye:
        yanit.headers.setdefault("Retry-After", str(saniye))
    return yanit


async def beklenmeyen_hata_yaniti(request: Request, exc: Exception) -> JSONResponse:
    """500 — düz metin yerine JSON; teknik ayrıntı günlüğe, kullanıcıya TR cümle.

    `logger.exception` → `GunlukHandler` bunu WARNING+ olarak hata günlüğüne
    yazar, yani kullanıcı 📋 KOPYALA ile bize gerçek sebebi verebilir.
    """
    log.exception("İşlenmeyen hata: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "kod": KOD_BEKLENMEYEN,
            "error": M("hata.beklenmeyen"),
        },
    )

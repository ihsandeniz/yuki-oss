"""API yanlış-anahtar kilidi — `/api/*` ve WebSocket'e anahtar tahmin etmeye karşı ikinci kapı.

`login_guard` yalnız giriş ekranını (parola · yüz) korur. Bu modül, API'ye doğrudan
yanlış Bearer, `?token=` ya da WS token'ı deneyen istemciyi durdurur.

Kural: bir istemci `API_GUARD_WINDOW_MINUTES` içinde `API_GUARD_MAX_WRONG` **farklı**
yanlış anahtar denerse `API_GUARD_LOCK_MINUTES` boyunca tüm API'den 429 alır
(doğru anahtarla gelse bile — kilit sırasında karşılaştırma yapılmaz).

Neden FARKLI anahtar sayılıyor: parola değişince telefondaki eski sekme aynı eski
anahtarı onlarca istekte tekrar yollar; bunu saymak sahibi kendi cihazından
kilitlerdi. Tahmin eden ise her denemede başka anahtar dener — o sayılır.
Anahtarın kendisi saklanmaz, yalnız kısa özeti.

İstemci kimliği (`istemci`): ters vekiller (`tailscale serve`, cloudflared) upstream'e
LOOPBACK'ten bağlanır — `client.host` herkes için 127.0.0.1 olur. Gerçek adres o
durumda vekilin bastığı başlığın TÜRÜNDEN alınır (değeri değil — uydurulabilir); başlığa
YALNIZ bağlantı loopback'ten geliyorsa bakılır (LAN'dan uydurulan başlık işe yaramaz). Vekilsiz loopback =
gerçekten bu makine → `None`, kilit uygulanmaz.

Durum bellekte tutulur: yeniden başlatmayı saldırgan tetikleyemez, kalıcılık gerekmiyor.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from threading import Lock
from typing import Callable, Iterable

from app import config

logger = logging.getLogger(__name__)

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_TAVAN = 5000  # izlenen istemci sayısı tavanı — bellek şişmesin

_LOCK = Lock()
_yanlislar: dict[str, dict[str, float]] = {}  # istemci → {anahtar özeti: son görülme}
_kilit: dict[str, float] = {}                 # istemci → kilit bitişi

OK, YANLIS, KILITLI = "ok", "yanlis", "kilitli"


def istemci(conn) -> str | None:
    """İsteğin gerçek kaynağı; `None` = vekilsiz yerel bağlantı (kilitlenmez).

    `conn` Starlette `Request` ya da `WebSocket` (ikisinde de `.client` · `.headers`).
    """
    host = (conn.client.host if conn.client else "") or ""
    if host not in _LOOPBACK:
        return host or "-"
    # Başlığın DEĞERİ kovaya girmez, yalnız vekil TÜRÜ: loopback'ten gelen her istek başlık
    # uydurabilir (bu makinedeki bir program, DNS rebinding'le gelen bir sayfa). Değer kovaya
    # girseydi her istekte başka değer = her istekte yeni kova = yanlış-anahtar sayacı hiç
    # dolmazdı. Tür başına tek kova: tünel denemeleri yine öbür vekildeki cihazı kilitlemez.
    if (conn.headers.get("cf-connecting-ip") or "").strip():
        return "tunel"
    if (conn.headers.get("x-forwarded-for") or "").split(",")[0].strip():
        return "vekil"
    if (conn.headers.get("tailscale-user-login") or "").strip():
        return "tailnet"
    return None


def _ozet(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8", "replace")).hexdigest()[:16]


def kalan(kimlik: str | None) -> float:
    """Kilitliyse kalan saniye, değilse 0."""
    if kimlik is None or config.API_GUARD_MAX_WRONG <= 0:
        return 0.0
    with _LOCK:
        t = _kilit.get(kimlik)
        if not t:
            return 0.0
        left = t - time.time()
        if left <= 0:
            _kilit.pop(kimlik, None)
            _yanlislar.pop(kimlik, None)
            return 0.0
        return left


def yanlis(kimlik: str | None, token: str) -> float:
    """Yanlış anahtarı kaydet. Sınır dolduysa kilitler; kilit süresini döner (yoksa 0)."""
    if kimlik is None or config.API_GUARD_MAX_WRONG <= 0 or not token:
        return 0.0
    now = time.time()
    pencere = config.API_GUARD_WINDOW_MINUTES * 60
    with _LOCK:
        if len(_yanlislar) >= _TAVAN and kimlik not in _yanlislar:
            # En eski istemcileri at — kilitli olanlar `_kilit`'te kalır.
            for k in sorted(_yanlislar, key=lambda k: max(_yanlislar[k].values(), default=0))[: _TAVAN // 10]:
                _yanlislar.pop(k, None)
        goruldu = {h: t for h, t in _yanlislar.get(kimlik, {}).items() if now - t <= pencere}
        goruldu[_ozet(token)] = now
        _yanlislar[kimlik] = goruldu
        if len(goruldu) >= config.API_GUARD_MAX_WRONG:
            secs = max(1, config.API_GUARD_LOCK_MINUTES * 60)
            _kilit[kimlik] = now + secs
            logger.warning("API kilitlendi: %s (%d farklı yanlış anahtar, %d sn)",
                           kimlik, len(goruldu), secs)
            return float(secs)
    return 0.0


def basari(kimlik: str | None) -> None:
    if kimlik is None:
        return
    with _LOCK:
        _yanlislar.pop(kimlik, None)


def dene(conn, adaylar: Iterable[str], kabul: Callable[[str], bool]) -> tuple[str, float]:
    """Tek giriş noktası: (`OK` | `YANLIS` | `KILITLI`, kalan kilit saniyesi).

    `adaylar`: istemcinin sunduğu anahtarlar (Bearer başlığı, `?token=`); biri
    `kabul` ederse yeterli. Kilitliyse hiçbiri karşılaştırılmaz. Boş anahtar
    yanlış sayılır ama sayaca yazılmaz (anahtarsız istek tahmin değildir).
    """
    kimlik = istemci(conn)
    left = kalan(kimlik)
    if left > 0:
        return KILITLI, left
    adaylar = [a for a in adaylar if a]
    if any(kabul(a) for a in adaylar):
        basari(kimlik)
        return OK, 0.0
    secs = 0.0
    for a in adaylar:
        secs = yanlis(kimlik, a) or secs
    return (KILITLI, secs) if secs else (YANLIS, 0.0)


def ws_gecer(ws, token: str, beklenen: str) -> bool:
    """WebSocket el sıkışması için: anahtar doğru mu (yanlışsa sayılır, kilitliyse reddedilir)."""
    durum, _ = dene(ws, [token], lambda t: secrets.compare_digest(t, beklenen))
    return durum == OK


def sifirla() -> None:
    """Testler için."""
    with _LOCK:
        _yanlislar.clear()
        _kilit.clear()

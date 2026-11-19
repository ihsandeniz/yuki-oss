"""Motoru kendi içinden ZARİFÇE kapatma (2026-10-08).

## Neden var
Windows'ta bir süreci dışarıdan kibarca kapatmanın yolu yok: SIGTERM yok, motor
`CREATE_NO_WINDOW` ile açıldığı için konsolu da yok (Ctrl-Break ulaşmaz). Bugüne kadar
kapanış `taskkill /T /F` idi → lifespan kapanışı (zamanlayıcı, MCP, açık dosyalar) hiç
koşmuyordu. Bu modül motora "kendini kapat" deme yolunu açar: uvicorn'un kendi
`should_exit` bayrağı — Linux'ta SIGTERM'in yaptığının aynısı.

Kim çağırır: Electron (`stopBackend`, Windows) ve yuki-bekci (`--kapanis`, Windows) →
`POST /api/motor/kapan` (`api/motor_api.py`). Python'un kendi ebeveyn bekçisi de Windows'ta
`os._exit` yerine önce bunu dener.

Zarif kapanış takılırsa (açık WebSocket, uzun iş) `ZORLA_SN` sonra `os._exit` — çağıranlar da
kendi taraflarında süre tutup zorla kapatır; bu yalnız motorun kendi emniyeti.
"""
from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable

log = logging.getLogger(__name__)

# Bekleyenlerin süresi buna bağlı: Electron `kibarKapat` ve bekçi `--bekle` = ZORLA_SN + pay
# (electron/bekci.js::MOTOR_ZORLA_SN — `bekci.test.js` bu satırı okur; değiştirirsen oradaki kopyayı da değiştir).
ZORLA_SN = 15.0

_sunucu = None  # run.py kurar: uvicorn.Server. reload modunda (geliştirme) kurulmaz.


def kur(sunucu) -> None:
    global _sunucu
    _sunucu = sunucu


def destekleniyor() -> bool:
    return _sunucu is not None


def iste(*, zorla_sn: float = ZORLA_SN, cik: Callable[[int], None] = os._exit) -> bool:
    """Zarif kapanışı başlat. Sunucu kurulmamışsa False (çağıran kendi yolunu seçer)."""
    if _sunucu is None:
        return False
    if getattr(_sunucu, "should_exit", False):
        return True  # zaten kapanıyor; ikinci zamanlayıcı kurma
    log.warning("motor kapanış isteği alındı — zarif kapanış (en çok %.0f sn)", zorla_sn)
    _sunucu.should_exit = True
    zorla = threading.Timer(zorla_sn, lambda: cik(0))
    zorla.daemon = True
    zorla.start()
    return True

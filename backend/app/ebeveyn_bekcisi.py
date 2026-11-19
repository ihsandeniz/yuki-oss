"""Motor, onu başlatan Yuki penceresi ölünce kendini kapatır.

🔴 Neden var (ölçüldü 2026-10-03, Electron 44 + gerçek motor, xvfb — `scratchpad/sinyal-kapanis-canli.py`):
Electron motoru `detached: true` ile KENDİ süreç grubunda başlatır (reload çocuklarıyla
grup-kill için). Bu yüzden motor Electron'la birlikte ölmez; yalnız `before-quit` →
`stopBackend()` kapatır. O yol Electron ZARİFÇE kapanınca koşar:

    SIGTERM / SIGINT / SIGHUP (gerçek ana süreç)   → before-quit koşar → 8791 boş   ✅
    SIGKILL                                         → hiçbir JS koşmaz  → 8791 DOLU  ❌
    görüntü sunucusu gider (oturum kapanışı)        → Electron çöker    → 8791 DOLU  ❌

İkinci sınıfı Electron tarafında hiçbir kanca yakalayamaz — o anda JS koşmuyor. Öksüz motor
yalnız bellek yemez: sonraki açılışta `startBackend` 8791'i dolu görüp onu YENİDEN KULLANIR,
delta güncellemeden sonra bu ESKİ KODUN çalışması demektir. Çözüm motorun kendisinde: ebeveyni
öldüyse kendini kapatsın.

- Linux/macOS: ebeveyn ölünce çocuk başka sürece (init/subreaper) devredilir → `os.getppid()`
  değişir. Ucuz ve PID yeniden kullanımına bağışık.
- Windows: `getppid` ebeveyn ölse de eski değeri döndürür → psutil ile süreç + başlama zamanı
  (aynı PID'i alan yeni bir süreç ebeveyn sanılmasın). ⚠️ Windows'ta ölçülmedi.

Bekçi yalnız açılışta ebeveyn GERÇEKTEN `YUKI_EBEVEYN_PID` ise kurulur: arada bir sarmalayıcı
varsa (ya da motor elle başlatıldıysa) yanlışlıkla kendini öldürmesin.
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time
from collections.abc import Callable

log = logging.getLogger(__name__)

YOKLAMA_SN = 2.0
ZORLA_SN = 15.0  # zarif kapanış takılırsa (açık WebSocket, uzun iş) bu kadar sonra zorla


def _windows_yoklayici(pid: int) -> Callable[[], bool] | None:
    """Windows: ebeveyn hâlâ yaşıyor mu? — psutil, başlama zamanıyla. Kurulamazsa None."""
    try:
        import psutil
        baslangic = psutil.Process(pid).create_time()
    except Exception:
        return None

    def yasiyor() -> bool:
        try:
            return psutil.Process(pid).create_time() == baslangic
        except Exception:
            return False

    return yasiyor


def yoklayici_kur(
    environ: dict | os._Environ = os.environ,
    *,
    platform: str = sys.platform,
    getppid: Callable[[], int] = os.getppid,
    windows_yoklayici: Callable[[int], Callable[[], bool] | None] = _windows_yoklayici,
) -> Callable[[], bool] | None:
    """`ebeveyn yaşıyor mu` yoklayıcısı; bekçi kurulmayacaksa None."""
    ham = (environ.get("YUKI_EBEVEYN_PID") or "").strip()
    if not ham.isdigit():
        return None  # Electron dışında (elle / testte) başlatıldı
    pid = int(ham)
    if platform == "win32":
        return windows_yoklayici(pid)
    if getppid() != pid:
        log.warning("ebeveyn bekçisi kurulmadı: ebeveyn %s, beklenen %s (arada sarmalayıcı var)", getppid(), pid)
        return None
    return lambda: getppid() == pid


def _kendini_kapat() -> None:
    log.warning("Yuki penceresi kapanmış (ebeveyn süreç yok) — motor kapanıyor")
    zorla = threading.Timer(ZORLA_SN, lambda: os._exit(0))
    zorla.daemon = True
    zorla.start()
    if sys.platform == "win32":
        # Windows'ta kendine SIGTERM = TerminateProcess → önce uvicorn'un zarif kapanışı;
        # sunucu kurulmamışsa (reload modu) dolambaçsız çık.
        from app import motor_kapanis
        if not motor_kapanis.iste():
            os._exit(0)
        return
    os.kill(os.getpid(), signal.SIGTERM)  # uvicorn'un zarif kapanışı (lifespan shutdown koşar)


def baslat(
    environ: dict | os._Environ = os.environ,
    *,
    yoklayici: Callable[[], bool] | None = None,
    kapat: Callable[[], None] = _kendini_kapat,
    uyu: Callable[[float], None] = time.sleep,
    aralik: float = YOKLAMA_SN,
) -> threading.Thread | None:
    """Bekçiyi arka planda başlat. Kurulmadıysa None."""
    yasiyor = yoklayici if yoklayici is not None else yoklayici_kur(environ)
    if yasiyor is None:
        return None

    def dongu() -> None:
        while yasiyor():
            uyu(aralik)
        kapat()

    t = threading.Thread(target=dongu, name="ebeveyn-bekcisi", daemon=True)
    t.start()
    log.info("ebeveyn bekçisi kuruldu (pid %s)", environ.get("YUKI_EBEVEYN_PID"))
    return t

"""Masaüstü Yuki — tek örnek kilidi.

NEDEN VAR: masaüstü Yuki artık iki yerden açılabiliyor — elle (`./run.sh`) ve Yuki'nin kendisinden
(backend `services/masaustu_yuki.py`: HQ › AYARLAR anahtarı, sohbette "masaüstüne gel"). İkisi aynı anda
koşarsa ekranda iki Yuki olur ve ikisi de aynı konum dosyasına yazar. Kilit sürecin İÇİNDE tutulur:
hangi yoldan açılırsa açılsın ikinci örnek açılmaz. Süreç ölünce çekirdek kilidi kendisi bırakır
(bayat kilit yok); PID dosyası yalnız bilgi içindir, doğruluk kilitten okunur.

Dosyalar `$XDG_RUNTIME_DIR` altında (oturum bitince silinir): `yuki-masaustu.kilit` · `yuki-masaustu.pid`.
Backend aynı yolları okur — adları değiştirirsen `backend/app/services/masaustu_yuki.py`'yi de değiştir.
"""
from __future__ import annotations

import fcntl
import os
from pathlib import Path

KILIT_ADI = "yuki-masaustu.kilit"
PID_ADI = "yuki-masaustu.pid"


def calisma_dizini() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")


def _pid_oku(yol: Path) -> int | None:
    try:
        return int(yol.read_text().strip())
    except (OSError, ValueError):
        return None


def al(dizin: Path | None = None):
    """Kilidi al. Başarılıysa açık dosya döner (süreç boyunca tutulmalı), yoksa (None, sahibin_pid'i)."""
    d = dizin or calisma_dizini()
    d.mkdir(parents=True, exist_ok=True)
    f = open(d / KILIT_ADI, "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None, _pid_oku(d / PID_ADI)
    pid_yol = d / PID_ADI
    gecici = pid_yol.with_suffix(".pid.yeni")
    gecici.write_text(str(os.getpid()))
    gecici.replace(pid_yol)
    return f, os.getpid()


def birak(f, dizin: Path | None = None) -> None:
    """Temiz çıkışta PID dosyasını sil (yalnız bizimse) ve kilidi bırak."""
    if f is None:
        return
    pid_yol = (dizin or calisma_dizini()) / PID_ADI
    if _pid_oku(pid_yol) == os.getpid():
        try:
            pid_yol.unlink()
        except OSError:
            pass
    try:
        fcntl.flock(f, fcntl.LOCK_UN)
    finally:
        f.close()


def tutuluyor_mu(dizin: Path | None = None) -> tuple[bool, int | None]:
    """Başka bir süreç kilidi tutuyor mu? (tutuluyor, pid). Kilidi denemek için alır ve hemen bırakır."""
    d = dizin or calisma_dizini()
    yol = d / KILIT_ADI
    if not yol.exists():
        return False, None
    with open(yol, "a+") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True, _pid_oku(d / PID_ADI)
        fcntl.flock(f, fcntl.LOCK_UN)
    return False, None

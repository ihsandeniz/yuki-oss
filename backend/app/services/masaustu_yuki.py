"""Masaüstü Yuki'yi Yuki'nin kendisinden aç / kapat.

NEDEN VAR: masaüstü Yuki (`masaustu/`, WebKit + gtk-layer-shell ya da X11 penceresi) ayrı bir süreçtir;
tek durum `MASAUSTU_YUKI` ayarıdır (varsayılan KAPALI).
  · HQ › AYARLAR › Sistem › "Masaüstü Yuki" anahtarı → settings_api bu modülün `ayarla()`sını çağırır.
  · Sohbette "masaüstüne gel / git" → `masaustu_yuki` aracı (dispatcher, tek motor) → aynı `ayarla()`.
  · Ayar açıksa backend açılınca masaüstü de gelir (`acilista`); backend kapanınca kendi açtığı/devraldığı
    masaüstünü kapatır (`kapanista`) ama AYARA DOKUNMAZ.
  · Kullanıcı masaüstü Yuki'yi kendisi kapatırsa (sağ tık, çıkış 0) ayar da kapanır. Çöküş (çıkış ≠ 0) ayarı
    değiştirmez, `son_hata`ya yazılır; kendiliğinden yeniden açılmaz.

İKİ KAPALI DURUM (hata değil, açılmaz):
  · `model_yok`: model kullanıcının KENDİ VRM dosyasıdır (`MASAUSTU_VRM` ayarı / env); depoda model yoktur.
  · `desteklenmiyor`: Linux dışı (macOS, Windows), grafik oturumu yok ya da pencere yüzeyi yok (katman kabuğu
    desteklemeyen GNOME Wayland'de XWayland da yoksa host çıkış 3 verir).

Tek örnek kilidi süreç içinde (`masaustu/tek_ornek.py`): kilit burada yalnız OKUNUR (dosya adları o modülle aynı).
PID, `/proc/<pid>/cmdline`'da `masaustu.py` geçmiyorsa sinyal gönderilmez (PID yeniden kullanımı).

Süreç `start_new_session` ile açılır. Sistem Python'u kullanılır (`gi` + WebKit2 venv'de yok):
`MASAUSTU_PYTHON` ile değiştirilebilir.
"""
from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

KOK = Path(__file__).resolve().parents[3]                  # backend/app/services → proje kökü
BETIK = KOK / "masaustu" / "masaustu.py"
PYTHON = os.getenv("MASAUSTU_PYTHON") or ("/usr/bin/python3" if Path("/usr/bin/python3").exists() else (shutil.which("python3") or ""))
KILIT_ADI = "yuki-masaustu.kilit"                          # = masaustu/tek_ornek.py
PID_ADI = "yuki-masaustu.pid"
LOG_ADI = "yuki-masaustu.log"
ACILIS_GECIKME_SN = 2.0
ERKEN_OLUM_SN = 1.5        # kilidi alıp hemen ölen süreç (ör. katman kabuğu yok → çıkış 3) "açıldı" sayılmasın
_ORTAMDAN_AT = ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")  # venv'in ayarları sistem Python'unu bozar
CIKIS_DESTEKLENMIYOR = (2, 3)   # masaustu.py: 2 GTK/WebKit yok · 3 yüzey yok
CIKIS_MODEL_YOK = 6

_kilit = threading.RLock()
_proc: subprocess.Popen | None = None
_durdurulan: set[int] = set()   # bizim kapattığımız PID'ler — izleyici bunları "kullanıcı kapattı" saymaz
_sahibiz = False          # bu backend açtı ya da devraldı → kapanışta kapatır
son_hata: str | None = None


# ───────────────────────────── durum ─────────────────────────────

def calisma_dizini() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")


def _pid_oku() -> int | None:
    try:
        return int((calisma_dizini() / PID_ADI).read_text().strip())
    except (OSError, ValueError):
        return None


def _tutuluyor() -> tuple[bool, int | None]:
    yol = calisma_dizini() / KILIT_ADI
    if not yol.exists():
        return False, None
    try:
        with open(yol, "a+") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return True, _pid_oku()
            fcntl.flock(f, fcntl.LOCK_UN)
    except OSError:
        return False, None
    return False, None


def _bizim_surec(pid: int) -> bool:
    try:
        return b"masaustu.py" in Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return False


def _ayar() -> bool:
    from app import config as cfg
    return bool(getattr(cfg, "MASAUSTU_YUKI", False))


def model_yolu() -> Path | None:
    """Kullanıcının VRM dosyası: `MASAUSTU_VRM` ayarı → env. Dosya yoksa ya da `.vrm` değilse None."""
    from app import config as cfg
    ham = str(getattr(cfg, "MASAUSTU_VRM", "") or os.environ.get("MASAUSTU_VRM", "")).strip()
    if not ham:
        return None
    yol = Path(ham).expanduser()
    return yol if yol.is_file() and yol.suffix.lower() == ".vrm" else None


def destek_sorunu() -> str | None:
    """Bu makinede masaüstü Yuki hiç açılabilir mi? Sorun varsa nedeni (düz Türkçe), yoksa None. Süreç açmaz."""
    if not sys.platform.startswith("linux"):
        return f"{sys.platform} masaüstünde desteklenmiyor (yalnız Linux)"
    if not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        return "grafik oturumu yok (WAYLAND_DISPLAY/DISPLAY boş)"
    if not PYTHON or not Path(PYTHON).exists():
        return "sistem Python'u yok (MASAUSTU_PYTHON)"
    return None


def durum_adi() -> str:
    """acik · kapali · model_yok · desteklenmiyor — arayüz ve araç bunu okur."""
    if _tutuluyor()[0]:
        return "acik"
    if destek_sorunu():
        return "desteklenmiyor"
    return "model_yok" if model_yolu() is None else "kapali"


def durum() -> dict:
    calisiyor, pid = _tutuluyor()
    return {"ayar": _ayar(), "calisiyor": calisiyor, "pid": pid, "son_hata": son_hata, "durum": durum_adi(),
            "destek_sorunu": destek_sorunu()}


def _log_kuyrugu(n: int = 3) -> str:
    try:
        satirlar = (calisma_dizini() / LOG_ADI).read_text(errors="replace").strip().splitlines()
    except OSError:
        return ""
    import re
    return re.sub(r"token=[^&\s]*", "token=***", " | ".join(satirlar[-n:]))[:300]


def _hata(metin: str, durum: str = "hata") -> dict:
    global son_hata
    son_hata = metin
    logger.warning("[masaustu_yuki] %s", metin)
    return {"ok": False, "hata": metin, "durum": durum}


# ───────────────────────────── başlat / durdur ─────────────────────────────

def _ortam(model: Path) -> dict:
    from app import config as cfg
    env = {k: v for k, v in os.environ.items() if k not in _ORTAMDAN_AT}
    env["YUKI_MASAUSTU_VRM"] = str(model)
    env.setdefault("YUKI_BACKEND", f"http://127.0.0.1:{getattr(cfg, 'PORT', 8001)}")
    return env


def baslat(bekle: float = 5.0) -> dict:
    """Açık değilse aç. Kilidi alana ya da süreç ölene kadar en çok `bekle` sn bekler.
    Model ya da masaüstü desteği yoksa süreç AÇILMAZ: `{"ok": False, "durum": "model_yok"|"desteklenmiyor"}`."""
    global _proc, _sahibiz, son_hata
    with _kilit:
        calisiyor, pid = _tutuluyor()
        if calisiyor:
            _sahibiz = True
            return {"ok": True, "zaten": True, "pid": pid}
        sorun = destek_sorunu()
        if sorun:
            return _hata(f"bu masaüstünde desteklenmiyor: {sorun}", "desteklenmiyor")
        model = model_yolu()
        if model is None:
            return _hata("model yok — MASAUSTU_VRM ayarına kendi .vrm dosyanın yolunu yaz", "model_yok")
        if not BETIK.exists():
            return _hata(f"masaüstü betiği yok: {BETIK}")
        try:
            log = open(calisma_dizini() / LOG_ADI, "ab")
        except OSError as e:
            return _hata(f"log açılamadı: {e}")
        try:
            proc = subprocess.Popen([PYTHON, str(BETIK)], cwd=str(BETIK.parent), env=_ortam(model),
                                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
        except OSError as e:
            return _hata(f"başlatılamadı: {e}")
        finally:
            log.close()
        _proc = proc
        t0 = time.monotonic()
        while time.monotonic() - t0 < bekle and proc.poll() is None and not _tutuluyor()[0]:
            time.sleep(0.1)
        t1 = time.monotonic()
        while time.monotonic() - t1 < ERKEN_OLUM_SN and proc.poll() is None:
            time.sleep(0.1)
        if proc.poll() is not None:
            _proc = None
            if proc.returncode == 5:          # tek örnek: arada biri açtı
                _sahibiz = True
                return {"ok": True, "zaten": True, "pid": _pid_oku()}
            if proc.returncode in CIKIS_DESTEKLENMIYOR:
                return _hata(f"bu masaüstünde desteklenmiyor {_log_kuyrugu()}".strip(), "desteklenmiyor")
            if proc.returncode == CIKIS_MODEL_YOK:
                return _hata("model yok — .vrm dosyası okunamadı", "model_yok")
            return _hata(f"açılır açılmaz kapandı (çıkış {proc.returncode}) {_log_kuyrugu()}".strip())
        _sahibiz, son_hata = True, None
        threading.Thread(target=_izle, args=(proc,), name="masaustu-izle", daemon=True).start()
        logger.info("[masaustu_yuki] açıldı pid=%s", proc.pid)
        return {"ok": True, "zaten": False, "pid": proc.pid}


def _izle(proc: subprocess.Popen) -> None:
    """Bizim açtığımız süreç kapanınca: kullanıcı kapattıysa (çıkış 0) ayarı da kapat."""
    global _proc, son_hata
    kod = proc.wait()
    with _kilit:
        if _proc is proc:
            _proc = None
        if proc.pid in _durdurulan:
            _durdurulan.discard(proc.pid)
            return
        if kod == 0:
            logger.info("[masaustu_yuki] kullanıcı kapattı → ayar kapalı")
            _ayari_yaz(False)
        else:
            son_hata = f"beklenmedik kapanış (çıkış {kod}) {_log_kuyrugu()}".strip()
            logger.warning("[masaustu_yuki] %s", son_hata)


def durdur(bekle: float = 4.0) -> dict:
    """Açıksa kapat (SIGTERM → bekle → SIGKILL). Ayara dokunmaz."""
    global _sahibiz
    with _kilit:
        calisiyor, pid = _tutuluyor()
        if not calisiyor:
            _sahibiz = False
            return {"ok": True, "zaten": True}
        if not pid or not _bizim_surec(pid):
            return _hata(f"kilit tutuluyor ama süreç doğrulanamadı (pid {pid}) — sinyal gönderilmedi")
        _durdurulan.add(pid)
        try:
            os.kill(pid, signal.SIGTERM)
            t0 = time.monotonic()
            while time.monotonic() - t0 < bekle and _tutuluyor()[0]:
                time.sleep(0.1)
            if _tutuluyor()[0] and _bizim_surec(pid):
                os.kill(pid, signal.SIGKILL)
                time.sleep(0.2)
        except ProcessLookupError:
            pass
        _sahibiz = False
        kapandi = not _tutuluyor()[0]
        logger.info("[masaustu_yuki] kapatıldı pid=%s (%s)", pid, "tamam" if kapandi else "HÂLÂ AÇIK")
        return {"ok": kapandi, "zaten": False, "pid": pid} if kapandi else _hata(f"kapanmadı (pid {pid})")


# ───────────────────────────── ayar = tek durum ─────────────────────────────

def _ayari_yaz(acik: bool) -> None:
    from app import config as cfg
    from app import config_manager
    config_manager.set_value("MASAUSTU_YUKI", bool(acik))
    setattr(cfg, "MASAUSTU_YUKI", bool(acik))


def ayarla(acik: bool) -> dict:
    """Anahtar ve sohbet aracı buradan geçer: açmak açılış başarılıysa ayarı yazar, kapatmak hep yazar."""
    with _kilit:
        if acik:
            r = baslat()
            if not r.get("ok"):
                return r                     # açılamadıysa ayar açık görünmesin
        else:
            r = durdur()
        _ayari_yaz(acik)
        return r


def arac(islem: str = "durum") -> str:
    """Sohbet aracı `masaustu_yuki` — LLM'e düz Türkçe sonuç."""
    islem = (islem or "durum").strip().lower()
    if islem in ("ac", "aç", "gel", "open", "on"):
        r = ayarla(True)
        if r.get("durum") == "desteklenmiyor":
            return f"Masaüstüne gelemiyorum: {r.get('hata')}"
        if r.get("durum") == "model_yok":
            return "Masaüstüne gelemiyorum: model yok — ayarlardan kendi VRM dosyanın yolunu vermen gerek."
        if not r.get("ok"):
            return f"Masaüstüne gelemedim: {r.get('hata')}"
        return ("Zaten masaüstündeyim." if r.get("zaten") else "Masaüstüne geldim.") + \
            " Yuki her açıldığında masaüstüne de gelirim (HQ › AYARLAR › Sistem'den kapatılır)."
    if islem in ("kapat", "git", "close", "off"):
        r = ayarla(False)
        if not r.get("ok"):
            return f"Masaüstünden çekilemedim: {r.get('hata')}"
        return "Zaten masaüstünde değildim." if r.get("zaten") else "Masaüstünden çekildim."
    d = durum()
    if d["durum"] in ("desteklenmiyor", "model_yok"):
        return ("Masaüstü Yuki bu masaüstünde desteklenmiyor." if d["durum"] == "desteklenmiyor"
                else "Masaüstü Yuki kapalı: model yok (MASAUSTU_VRM ayarı boş).")
    return (f"Masaüstü Yuki {'açık' if d['calisiyor'] else 'kapalı'}; açılışta gelme ayarı "
            f"{'açık' if d['ayar'] else 'kapalı'}." + (f" Son hata: {d['son_hata']}" if d["son_hata"] else ""))


# ───────────────────────────── backend yaşam döngüsü ─────────────────────────────

async def acilista(gecikme: float = ACILIS_GECIKME_SN) -> None:
    """Ayar açıksa masaüstünü aç (WS'in ayağa kalkması için kısa gecikme; masaüstü zaten yeniden dener)."""
    if not _ayar():
        return
    await asyncio.sleep(gecikme)
    r = await asyncio.to_thread(baslat)
    if not r.get("ok"):
        logger.warning("[masaustu_yuki] açılışta açılamadı: %s", r.get("hata"))


async def kapanista() -> None:
    """Yalnız bu backend'in açtığı/devraldığı örneği kapatır; ayar değişmez (sonraki açılışta yine gelir).
    Sahip değilsek (ör. test kipi ikinci örnek, ya da elle run.sh) dokunmaz."""
    if not _sahibiz:
        return
    await asyncio.to_thread(durdur)

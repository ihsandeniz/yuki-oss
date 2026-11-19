"""Kamera görüşü ve ses kimliği için açık rıza kaydı.

İki özellik de iki kapıdan geçer:
  1. Bayrak (`GORUS`, `SES_KIMLIK`): kurulumu yapan açar. Varsayılan KAPALI; kapalıyken uçlar 404.
  2. Rıza (bu modül): bayrak açık olsa bile kullanıcı rıza ekranını onaylamadan kamera
     açılmaz, ses örneği alınmaz. Rıza bu bilgisayardan verilir (uç loopback ister).

Rıza metni değişirse `SURUM` artırılır; eski sürümle verilmiş rıza geçersiz sayılır ve
ekran yeniden sorar. Rıza geri çekilince bağlı özellik o anda kapanır (ses kimliğinde
kayıtlı ses izi de silinir: `ses_kimlik.riza_geri_cekildi`).

Kayıt dosyası: `<veri dizini>/biyometrik_riza.json` (izin 600). Yalnız tarih ve sürüm tutar;
görüntü ya da ses tutmaz.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

OZELLIKLER = ("gorus", "ses_kimlik")

# Rıza metninin sürümü. Ön yüzdeki metin (frontend/js/gorus-panel.js `RIZA_METNI`) değişirse
# ikisini birlikte artır; sunucu eski sürümle gelen onayı reddeder.
SURUM = {"gorus": 1, "ses_kimlik": 1}

_kilit = threading.Lock()


def _veri_dizini() -> Path:
    yol = os.getenv("YUKI_DATA_DIR", "").strip()
    if yol:
        return Path(yol)
    from app.config import DATA_DIR
    return Path(DATA_DIR)


def dosya_yolu() -> Path:
    return _veri_dizini() / "biyometrik_riza.json"


def _oku() -> dict:
    try:
        veri = json.loads(dosya_yolu().read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {}
    return veri if isinstance(veri, dict) else {}


def _yaz(veri: dict) -> None:
    yol = dosya_yolu()
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".tmp")
    fd = os.open(gecici, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False)
    os.replace(gecici, yol)
    try:
        os.chmod(yol, 0o600)
    except OSError:
        pass


def _ozellik_denetle(ozellik: str) -> None:
    if ozellik not in OZELLIKLER:
        raise ValueError(f"bilinmeyen özellik: {ozellik}")


def var_mi(ozellik: str) -> bool:
    """Geçerli (güncel sürümle verilmiş) rıza var mı? Okunamayan kayıt = rıza yok."""
    _ozellik_denetle(ozellik)
    kayit = _oku().get(ozellik)
    return isinstance(kayit, dict) and kayit.get("surum") == SURUM[ozellik] and bool(kayit.get("verildi"))


def ver(ozellik: str, surum: int) -> dict:
    """Rızayı kaydeder. Gelen sürüm güncel metnin sürümü değilse ValueError."""
    _ozellik_denetle(ozellik)
    if surum != SURUM[ozellik]:
        raise ValueError("rıza metni güncel değil; ekranı yenileyip yeniden okuyun")
    with _kilit:
        veri = _oku()
        veri[ozellik] = {"surum": SURUM[ozellik],
                         "verildi": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        _yaz(veri)
        return dict(veri[ozellik])


def geri_cek(ozellik: str) -> bool:
    """Rızayı siler. Önceden rıza varsa True."""
    _ozellik_denetle(ozellik)
    with _kilit:
        veri = _oku()
        vardi = ozellik in veri
        veri.pop(ozellik, None)
        _yaz(veri)
        return vardi


def ozet(ozellik: str) -> dict:
    _ozellik_denetle(ozellik)
    kayit = _oku().get(ozellik) if var_mi(ozellik) else None
    return {"verildi": bool(kayit), "tarih": (kayit or {}).get("verildi"), "surum": SURUM[ozellik]}

"""Cihaz ajanının riskli eylemleri — varsayılan KAPALI (karar 2026-11-01).

Bağlı bir cihazda dosya yazmak (`writefile`), dosya silmek (`deletefile`) ve program kapatmak
(`killproc`) geri alınamaz iş yapar. Açık kaynak kurulumda bu üçü **kapalı gelir**; kullanıcı
HQ › Cihazlar'dan tek tek açar (`PUT /api/devices/izinler`).

## 🔴 Kapı — iki yerde, tek kural: erişim anahtarı yoksa açılmaz

1. **Açma ucu**: istek `.env`'deki `AUTH_TOKEN` ile aynı anahtarı taşımalı. `AUTH_TOKEN` boşsa hiçbir
   anahtar geçmez — `compare_digest("", "")` doğru döner, o yüzden boşluk AYRICA reddedilir.
2. **Komut ucu** (`POST /api/devices/{id}/command`): ayar açık olsa da `AUTH_TOKEN` sonradan
   boşaltıldıysa eylem reddedilir (fail-closed). Ayar okunamazsa kapalı sayılır.

Kapatmak her zaman serbesttir, anahtar istemez.
"""
from __future__ import annotations

import secrets

from app import config as cfg
from app import config_manager

#: eylem → config.user.json anahtarı
RISKLI_EYLEMLER: dict[str, str] = {
    "writefile":  "CIHAZ_IZIN_DOSYA_YAZ",
    "deletefile": "CIHAZ_IZIN_DOSYA_SIL",
    "killproc":   "CIHAZ_IZIN_SUREC_KAPAT",
}


def anahtar_kurulu() -> bool:
    return bool(getattr(cfg, "AUTH_TOKEN", ""))


def anahtar_dogru(anahtar: str | None) -> bool:
    """Boş `AUTH_TOKEN` ya da boş anahtar → False (boş = boş eşleşmesi kabul edilmez)."""
    beklenen = getattr(cfg, "AUTH_TOKEN", "")
    if not beklenen or not anahtar:
        return False
    return secrets.compare_digest(str(anahtar), beklenen)


def ayar_acik(eylem: str) -> bool:
    ad = RISKLI_EYLEMLER.get(eylem)
    if not ad:
        return False
    try:
        return config_manager.get(ad, False) is True
    except Exception:
        return False


def izinli(eylem: str) -> bool:
    """Komut ucunun sorusu: bu eylem şu an gönderilebilir mi?"""
    if eylem not in RISKLI_EYLEMLER:
        return True
    return ayar_acik(eylem) and anahtar_kurulu()


def durum() -> dict:
    return {
        "anahtar_kurulu": anahtar_kurulu(),
        "izinler": {e: izinli(e) for e in RISKLI_EYLEMLER},
    }


def yaz(eylem: str, acik: bool) -> tuple[bool, str]:
    return config_manager.set_value(RISKLI_EYLEMLER[eylem], bool(acik))

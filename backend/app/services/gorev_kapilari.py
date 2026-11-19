"""Harness H3 kapıları — gündüz penceresi · günlük bütçe · kota bekleme (HARNESS-TASARIM § 6, § 7).

Bu modül KARAR vermez, ölçer: saat pencerede mi, koşan görevin kalan tahmini ne, ayar ne.
Kapıları iş sırası (`gorev_kuyrugu._ilerlet`) ve nöbetçi (`gorev_nobetci`, gece durdurma)
uygular. Kapsam yalnız harness: kuyruğun başlattığı iş. Kullanıcının elle başlattığı/sürdürdüğü
görev pencereye ve bütçe kapısına takılmaz (o an masada, kararı kendisi veriyor) — ama
harcadığı token/süre günlük bütçeye sayılır (aynı sağlayıcı kotası).

Ayar sırası: `app.config` özniteliği (panel yazarsa) > ortam değişkeni > varsayılan.
Okunamayan değer varsayılana düşer (yanlış yazılmış ayar kapıyı AÇMAZ).
Varsayılan rakamlar: 6 görev/gün · 2 M token/gün · pencere 08:30-23:30.
"""

from __future__ import annotations

import logging
import os
import re
import time

logger = logging.getLogger(__name__)

PENCERE = "08:30-23:30"           # YUKI_ATOLYE_PENCERE (HK4)
GUNLUK_TOKEN = 2_000_000          # YUKI_ATOLYE_GUNLUK_TOKEN (HK4)
GUNLUK_GOREV = 6                  # YUKI_ATOLYE_GUNLUK_GOREV (HK4) — kuyruğun başlattığı iş sayısı
GUNLUK_SURE_DK = 180              # YUKI_ATOLYE_GUNLUK_SURE_DK — tasarımda rakam yok, varsayılan (H3.md)
KOTA_BEKLEME_DK = 60              # YUKI_ATOLYE_KOTA_BEKLEME_DK (tasarım § 6)
GECE_PAYI = 15 * 60               # sn — pencere sonunda kalan tahmini bu kadarsa iş sürer
_SAAT = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")


def _ayar(ad: str, varsayilan):
    try:
        from app import config
        v = getattr(config, ad, None)
    except Exception:                       # pragma: no cover — config yüklenemedi
        v = None
    if v is None or v == "":
        v = os.environ.get(ad)
    if v is None or v == "":
        return varsayilan
    try:
        v = type(varsayilan)(v)
    except (TypeError, ValueError):
        logger.warning("[kapi] %s=%r okunamadı → varsayılan %r", ad, v, varsayilan)
        return varsayilan
    if isinstance(v, (int, float)) and v <= 0:
        logger.warning("[kapi] %s=%r pozitif değil → varsayılan %r", ad, v, varsayilan)
        return varsayilan
    return v


def pencere() -> tuple[int, int]:
    """(başlangıç, bitiş) gün içi dakika. Bitiş 24:00'e kadar; gece yarısını aşan ya da boş
    pencere tanınmaz → varsayılan."""
    for metin in (_ayar("YUKI_ATOLYE_PENCERE", PENCERE), PENCERE):
        m = _SAAT.match(str(metin).strip())
        if m:
            a, b = int(m[1]) * 60 + int(m[2]), int(m[3]) * 60 + int(m[4])
            if int(m[2]) < 60 and int(m[4]) < 60 and 0 <= a < b <= 24 * 60:
                return a, b
        logger.warning("[kapi] YUKI_ATOLYE_PENCERE=%r tanınmadı → %s", metin, PENCERE)
    raise AssertionError("varsayılan pencere bozuk")  # pragma: no cover


def _gun_dakikasi(ts: float) -> float:
    t = time.localtime(ts)
    return t.tm_hour * 60 + t.tm_min + t.tm_sec / 60


def pencerede_mi(ts: float) -> bool:
    bas, bit = pencere()
    return bas <= _gun_dakikasi(ts) < bit


def pencere_disi_sn(ts: float) -> float:
    """Son pencere bitişinden bu yana geçen sn; pencere içindeyse 0."""
    bas, bit = pencere()
    dk = _gun_dakikasi(ts)
    if bas <= dk < bit:
        return 0.0
    return ((dk - bit) if dk >= bit else (24 * 60 - bit + dk)) * 60


def kalan_tahmini(d: dict) -> float:
    """Koşan görevin bitmesine kalan tahmini sn: adım ortalaması × kalan adım, süre
    tavanıyla sınırlı. Adım yoksa kalan süre tavanı (ölçü yok → en kötüsü)."""
    tav = d.get("tavanlar") or {}
    adim = int(d.get("adim") or 0)
    gecen = float(d.get("sure_sn") or 0)
    kalan_sure = max(0.0, float(tav.get("sure_sn") or 0) - gecen)
    if adim <= 0:
        return kalan_sure
    kalan_adim = max(0, int(tav.get("adim") or 0) - adim)
    return min(gecen / adim * kalan_adim, kalan_sure)


def gun(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def gunluk_tavanlar() -> dict:
    return {"token": _ayar("YUKI_ATOLYE_GUNLUK_TOKEN", GUNLUK_TOKEN),
            "gorev": _ayar("YUKI_ATOLYE_GUNLUK_GOREV", GUNLUK_GOREV),
            "sure_sn": _ayar("YUKI_ATOLYE_GUNLUK_SURE_DK", GUNLUK_SURE_DK) * 60}


def kota_bekleme_sn() -> float:
    return float(_ayar("YUKI_ATOLYE_KOTA_BEKLEME_DK", KOTA_BEKLEME_DK)) * 60

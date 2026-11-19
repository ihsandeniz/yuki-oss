"""Sağlık ölçeri — kaydedilmiş sensör skoru (HQ › Bilgisayarım › SAĞLIK ÖLÇERİ).

Her sensör `iyi | uyari | kotu | olculemedi` durumlarından birini üretir.

🔑 **⚪ ölçülemedi ≠ ❌ kötü.** Ölçüm aracının kendi kusuru (dosya okunamadı, özellik
kurulmamış) ölçtüğü şeyin arızası gibi görünürse panel yalancı olur. Bu yüzden
ölçülemeyen sensör skor paydasından DÜŞER, cezalandırılmaz; çıktıda ayrı sayılır.
⚠️ Skor yükselince de `kapsam`a bak: ölçemeyen sensör sessizce skoru yukarı iter.

Sensör değerleri makine verisidir (sayı + birim); ekran metni arayüzde çevrilir.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_VERI_KOKU = Path(os.getenv("YUKI_DATA_DIR") or Path(__file__).resolve().parents[2])
KAYIT_DIZINI = _VERI_KOKU / "data" / "saglik"
SAKLANAN_KAYIT = 30           # günlük kayıt; bundan eskisi silinir
BAYAT_SAAT = 36               # günlük ölçüm varsayımı: 24 sa + 12 sa pay
YEDEK_TAZE_SAAT = 48          # zamanlanmış yedek bundan eskiyse uyarı
DISK_BOS_UYARI_YUZDE = 15
DISK_BOS_KOTU_YUZDE = 5
HATA_UYARI_24S = 1
HATA_KOTU_24S = 20

PUAN = {"iyi": 100, "uyari": 60, "kotu": 0}


class Sensor:
    """Tek ölçüm. `deger` sayı ya da None, `birim` arayüzün biçimlediği etiket."""

    def __init__(self, ad: str):
        self.ad = ad
        self.durum, self.deger, self.birim, self.neden = "olculemedi", None, None, ""

    def _ayarla(self, durum, deger, birim, neden=""):
        self.durum, self.deger, self.birim, self.neden = durum, deger, birim, neden
        return self

    def iyi(self, deger=None, birim=None): return self._ayarla("iyi", deger, birim)
    def uyari(self, deger=None, birim=None, neden=""): return self._ayarla("uyari", deger, birim, neden)
    def kotu(self, deger=None, birim=None, neden=""): return self._ayarla("kotu", deger, birim, neden)
    def yok(self, neden): return self._ayarla("olculemedi", None, None, neden)

    def sozluk(self) -> dict:
        return {"ad": self.ad, "durum": self.durum, "deger": self.deger,
                "birim": self.birim, "neden": self.neden}


# ── Sensörler ───────────────────────────────────────────────────────────────

def s_veri_klasoru() -> Sensor:
    """Yuki'nin verisini yazdığı klasör yazılabilir mi."""
    s = Sensor("veri_klasoru")
    if not _VERI_KOKU.exists():
        return s.yok("klasor-yok")
    if not os.access(_VERI_KOKU, os.W_OK):
        return s.kotu(neden="yazilamiyor")
    return s.iyi()


def s_disk() -> Sensor:
    """Veri klasörünün bulunduğu diskte boş yer (yüzde)."""
    s = Sensor("disk")
    try:
        k = shutil.disk_usage(_VERI_KOKU)
    except OSError:
        return s.yok("okunamadi")
    if not k.total:
        return s.yok("okunamadi")
    bos = round(k.free * 100 / k.total)
    if bos < DISK_BOS_KOTU_YUZDE:
        return s.kotu(bos, "yuzde", "disk-dolu")
    if bos < DISK_BOS_UYARI_YUZDE:
        return s.uyari(bos, "yuzde", "disk-az")
    return s.iyi(bos, "yuzde")


def s_hafiza() -> Sensor:
    """Gömülü hafıza veritabanı dosyası var mı (boyutu MB)."""
    from app import config
    s = Sensor("hafiza")
    if getattr(config, "MEMORY_BACKEND", "sqlite") != "sqlite":
        return s.yok("harici-veritabani")
    yol = Path(config.MEMORY_DB_PATH)
    if not yol.exists():
        return s.yok("henuz-yok")        # ilk kullanımdan önce normal — arıza değil
    try:
        return s.iyi(round(yol.stat().st_size / 1024 / 1024, 1), "mb")
    except OSError:
        return s.yok("okunamadi")


def s_yedek() -> Sensor:
    """Son yedekleme turu. Yedekleme kurulmamışsa ⚪ — kurmamak arıza değil."""
    from app.services import yedekleme
    s = Sensor("yedek")
    ayar = yedekleme.ayarlar()
    son = ayar.get("son_tur")
    if not isinstance(son, dict):
        return s.yok("kurulmamis")
    if son.get("hata"):
        return s.kotu(neden="son-tur-hata")
    try:
        basladi = datetime.fromisoformat(str(son.get("basladi")))
        if basladi.tzinfo is None:
            basladi = basladi.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return s.yok("zaman-okunamadi")
    yas_sa = round((datetime.now(timezone.utc) - basladi).total_seconds() / 3600)
    if ayar.get("zamanlama") and yas_sa > YEDEK_TAZE_SAAT:
        return s.uyari(yas_sa, "saat", "yedek-bayat")
    return s.iyi(yas_sa, "saat")


def s_hata_gunlugu() -> Sensor:
    """Son 24 saatte günlüğe düşen hata sayısı."""
    from app.services import error_log
    s = Sensor("hata_gunlugu")
    try:
        adet = int(error_log.ozet().get("son_24s") or 0)
    except Exception:  # noqa: BLE001
        return s.yok("okunamadi")
    if adet >= HATA_KOTU_24S:
        return s.kotu(adet, "adet", "cok-hata")
    if adet >= HATA_UYARI_24S:
        return s.uyari(adet, "adet", "hata-var")
    return s.iyi(adet, "adet")


SENSORLER: list[Callable[[], Sensor]] = [s_veri_klasoru, s_disk, s_hafiza, s_yedek, s_hata_gunlugu]


def olc() -> list[Sensor]:
    cikti = []
    for fn in SENSORLER:
        try:
            cikti.append(fn())
        except Exception as e:  # noqa: BLE001 — çöken sensör ⚪ olur, ❌ değil
            logger.warning("saglik sensörü çöktü (%s): %s", fn.__name__, type(e).__name__)
            cikti.append(Sensor(fn.__name__.removeprefix("s_")).yok("cokmus"))
    return cikti


def skorla(sensorler) -> tuple[int | None, int, int]:
    """(skor, ölçülen, toplam). Ölçülemeyen sensör paydadan düşer; hiçbiri ölçülemezse skor None."""
    olculen = [s for s in sensorler if s.durum != "olculemedi"]
    if not olculen:
        return None, 0, len(sensorler)
    return round(sum(PUAN[s.durum] for s in olculen) / len(olculen)), len(olculen), len(sensorler)


# ── Kayıt ───────────────────────────────────────────────────────────────────

def olc_ve_kaydet(dizin: Path | None = None) -> dict:
    """Ölç, günün dosyasına yaz (aynı gün üzerine), eski kayıtları buda."""
    dizin = dizin or KAYIT_DIZINI
    sensorler = olc()
    skor, olculen, toplam = skorla(sensorler)
    kayit = {"skor": skor, "kapsam": f"{olculen}/{toplam}",
             "sensorler": [s.sozluk() for s in sensorler],
             "damga": datetime.now().isoformat(timespec="seconds")}
    dizin.mkdir(parents=True, exist_ok=True)
    hedef = dizin / f"{datetime.now():%Y-%m-%d}.json"
    gecici = hedef.with_suffix(".json.tmp")
    gecici.write_text(json.dumps(kayit, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(gecici, hedef)
    for eski in sorted(dizin.glob("*.json"))[:-SAKLANAN_KAYIT]:
        try:
            eski.unlink()
        except OSError:
            pass
    return kayit


def son_kayit(dizin: Path | None = None) -> dict:
    """Son kaydı + yaşını döndürür. Ölçüm KOŞTURMAZ.

    Kayıt yoksa 404 değil `durum: "kayit-yok"` (ilk gün beklenen durumdur);
    bozuksa `kayit-bozuk` — yarım dosya "skor 0" gibi yalancı kırmızı olmamalı.
    """
    dizin = dizin or KAYIT_DIZINI
    try:
        kayitlar = sorted(dizin.glob("*.json"))
    except OSError:
        kayitlar = []
    if not kayitlar:
        return {"durum": "kayit-yok"}
    son = kayitlar[-1]
    try:
        veri = json.loads(son.read_text(encoding="utf-8"))
        if not isinstance(veri, dict):
            raise ValueError("nesne değil")
        yas_sn = max(0, int(time.time() - son.stat().st_mtime))
    except (OSError, ValueError):
        return {"durum": "kayit-bozuk", "kayit_dosyasi": son.name}
    veri["durum"] = "iyi"
    veri["kayit_dosyasi"] = son.name
    veri["yas_saat"] = round(yas_sn / 3600, 1)
    veri["bayat"] = yas_sn > BAYAT_SAAT * 3600
    return veri

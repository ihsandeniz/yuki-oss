"""Güvenli dosya işlemleri — çöpe at · taşı · geri al. Varsayılan KAPALI.

Dosya gezgini (`app/api/dosya_api.py`) salt okunurdur ve öyle kalır. Yazma yalnız bu modülde
ve ancak kullanıcı açarsa yaşar.

## Kurallar
1. **Kapalı gelir.** Açmak kurulumun erişim anahtarını (`.env` `AUTH_TOKEN`) ister — cihaz
   ajanının riskli eylemleriyle aynı kapı (`cihaz_yetki.anahtar_dogru`). Kapatmak serbest.
   Ayar okunamazsa ya da `AUTH_TOKEN` sonradan boşaltılırsa kapalı sayılır (fail-closed).
   Ayar `config_manager`'da değil, kendi dosyasında (`<veri>/dosya/guvenli/ayar.json`) —
   genel `POST /api/settings/{key}` ucu onu yazamaz.
2. **Kalıcı silme yok.** "Sil" = çöp klasörüne taşı (`<veri>/dosya/guvenli/cop/<işlem>/`).
   Çöpü boşaltan kod da yok; kullanıcı çöpü kendi dosya yöneticisinden boşaltır.
3. **Her yıkıcı işlem onaylı.** `hazirla` hiçbir dosyaya dokunmaz, özet + tek kullanımlık onay
   kodu döner (ONAY_OMUR sn). `uygula` yalnız o kodla çalışır.
4. **Üstüne yazma yok.** Hedefte aynı ad varsa işlem reddedilir; geri alırken eski yer dolmuşsa da.
5. **Ya hep ya hiç.** Çok öğeli işlemde biri düşerse yapılanlar geri sarılır.
6. **Yol kapıları okumayla aynı** (`dosya_api._guvenli`: resolve · kök · gizli · hassas) + kökün
   kendisine işlem yapılmaz + klasör kendi içine taşınmaz.
"""
from __future__ import annotations

import json
import logging
import secrets
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from app.config import DATA_DIR
from app.services import cihaz_yetki

logger = logging.getLogger(__name__)

VERI_DIZINI = DATA_DIR / "dosya" / "guvenli"
ONAY_OMUR = 120.0
AZAMI_OGE = 50
GUNLUK_AZAMI = 200
TURLER = ("cop", "tasi")

_BEKLEYEN: dict[str, dict[str, Any]] = {}
_KILIT = threading.Lock()


class IslemHatasi(Exception):
    def __init__(self, kod: int, mesaj: str):
        super().__init__(mesaj)
        self.kod = kod
        self.mesaj = mesaj


# ── Ayar ─────────────────────────────────────────────────────────── #

def _ayar_yolu() -> Path:
    return VERI_DIZINI / "ayar.json"


def ayar_acik() -> bool:
    try:
        return json.loads(_ayar_yolu().read_text("utf-8")).get("acik") is True
    except Exception:
        return False


def acik() -> bool:
    """İşlem uçlarının sorusu: ayar açık VE erişim anahtarı kurulu mu?"""
    return ayar_acik() and cihaz_yetki.anahtar_kurulu()


def ayarla(ac: bool, anahtar: str | None) -> None:
    if ac:
        if not cihaz_yetki.anahtar_kurulu():
            raise IslemHatasi(409, "Önce .env'de AUTH_TOKEN (erişim anahtarı) tanımlanmalı.")
        if not cihaz_yetki.anahtar_dogru(anahtar):
            raise IslemHatasi(403, "Erişim anahtarı yanlış.")
    VERI_DIZINI.mkdir(parents=True, exist_ok=True)
    _ayar_yolu().write_text(json.dumps({"acik": bool(ac)}), "utf-8")


# ── Günlük ───────────────────────────────────────────────────────── #

def _gunluk_yolu() -> Path:
    return VERI_DIZINI / "gunluk.json"


def gunluk() -> list[dict[str, Any]]:
    """En yeni önce."""
    try:
        d = json.loads(_gunluk_yolu().read_text("utf-8"))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _gunluk_yaz(liste: list[dict[str, Any]]) -> None:
    VERI_DIZINI.mkdir(parents=True, exist_ok=True)
    gecici = _gunluk_yolu().with_suffix(".tmp")
    gecici.write_text(json.dumps(liste[:GUNLUK_AZAMI], ensure_ascii=False, indent=1), "utf-8")
    gecici.replace(_gunluk_yolu())


# ── Hazırla / uygula ─────────────────────────────────────────────── #

def _icinde(p: Path, ata: Path) -> bool:
    try:
        p.relative_to(ata)
        return True
    except ValueError:
        return False


def hazirla(tur: str, yollar: list[tuple[Path, Path]], hedef: Path | None) -> dict[str, Any]:
    """`yollar`: kapıdan geçmiş (gerçek yol, kök) çiftleri. Diske dokunmaz."""
    if tur not in TURLER:
        raise IslemHatasi(422, "Bilinmeyen işlem.")
    if not yollar or len(yollar) > AZAMI_OGE:
        raise IslemHatasi(422, f"1 ile {AZAMI_OGE} arası öğe seçilmeli.")
    kaynaklar: list[Path] = []
    for gercek, kok in yollar:
        if gercek == kok:
            raise IslemHatasi(403, "Kök klasörün kendisine işlem yapılmaz.")
        if gercek not in kaynaklar:
            kaynaklar.append(gercek)
    if tur == "tasi":
        if hedef is None:
            raise IslemHatasi(422, "Taşıma için hedef klasör gerekli.")
        if not hedef.is_dir():
            raise IslemHatasi(400, "Hedef bir klasör değil.")
        for k in kaynaklar:
            if k.parent == hedef:
                raise IslemHatasi(400, f"'{k.name}' zaten bu klasörde.")
            if k.is_dir() and _icinde(hedef, k):
                raise IslemHatasi(400, f"'{k.name}' kendi içine taşınamaz.")
            if (hedef / k.name).exists() or (hedef / k.name).is_symlink():
                raise IslemHatasi(409, f"Hedefte '{k.name}' zaten var — üstüne yazılmaz.")
        adlar = [k.name for k in kaynaklar]
        if len(set(adlar)) != len(adlar):
            raise IslemHatasi(409, "Aynı adlı iki öğe aynı klasöre taşınamaz.")
    kod = secrets.token_urlsafe(24)
    with _KILIT:
        simdi = time.time()
        for k in [k for k, v in _BEKLEYEN.items() if v["son"] < simdi]:
            _BEKLEYEN.pop(k, None)
        _BEKLEYEN[kod] = {"tur": tur, "kaynaklar": [str(k) for k in kaynaklar],
                          "hedef": str(hedef) if hedef else None, "son": simdi + ONAY_OMUR}
    return {"onay": kod, "sure": int(ONAY_OMUR),
            "ozet": {"tur": tur, "sayi": len(kaynaklar), "adlar": [k.name for k in kaynaklar][:10],
                     "hedef": str(hedef) if hedef else None,
                     "klasor_var": any(k.is_dir() for k in kaynaklar)}}


def _tasi(kaynak: Path, hedef: Path) -> None:
    if hedef.exists() or hedef.is_symlink():
        raise IslemHatasi(409, f"'{hedef.name}' zaten var — üstüne yazılmaz.")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(kaynak), str(hedef))


def _sirayla(ciftler: list[tuple[Path, Path]]) -> None:
    """Ya hep ya hiç: biri düşerse yapılanları ters sırayla geri taşı."""
    yapilan: list[tuple[Path, Path]] = []
    try:
        for a, b in ciftler:
            if not (a.exists() or a.is_symlink()):
                raise IslemHatasi(404, f"'{a.name}' artık yok.")
            _tasi(a, b)
            yapilan.append((a, b))
    except Exception as e:
        for a, b in reversed(yapilan):
            try:
                shutil.move(str(b), str(a))
            except Exception:
                logger.exception("geri sarma başarısız: %s", b)
        if isinstance(e, IslemHatasi):
            raise
        logger.exception("güvenli dosya işlemi düştü")
        raise IslemHatasi(500, "İşlem yapılamadı; yapılanlar geri sarıldı.")


def uygula(kod: str) -> dict[str, Any]:
    with _KILIT:
        b = _BEKLEYEN.pop(kod or "", None)
    if not b or b["son"] < time.time():
        raise IslemHatasi(410, "Onayın süresi doldu ya da kullanıldı — yeniden dene.")
    islem = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    if b["tur"] == "cop":
        kutu = VERI_DIZINI / "cop" / islem
        ciftler = [(Path(k), kutu / f"{i}-{Path(k).name}") for i, k in enumerate(b["kaynaklar"])]
    else:
        ciftler = [(Path(k), Path(b["hedef"]) / Path(k).name) for k in b["kaynaklar"]]
    _sirayla(ciftler)
    kayit = {"id": islem, "tur": b["tur"], "zaman": time.time(), "geri_alindi": False,
             "hedef": b["hedef"], "ogeler": [{"once": str(a), "sonra": str(c)} for a, c in ciftler]}
    with _KILIT:
        _gunluk_yaz([kayit] + gunluk())
    return {"islem": islem, "sayi": len(ciftler)}


def geri_al(islem: str) -> dict[str, Any]:
    with _KILIT:
        liste = gunluk()
        kayit = next((k for k in liste if k.get("id") == islem), None)
        if kayit is None:
            raise IslemHatasi(404, "İşlem bulunamadı.")
        if kayit.get("geri_alindi"):
            raise IslemHatasi(409, "Bu işlem zaten geri alındı.")
        for o in kayit["ogeler"]:
            if Path(o["once"]).exists():
                raise IslemHatasi(409, f"'{Path(o['once']).name}' eski yerinde yeni bir öğe var — üstüne yazılmaz.")
        _sirayla([(Path(o["sonra"]), Path(o["once"])) for o in kayit["ogeler"]])
        kayit["geri_alindi"] = True
        _gunluk_yaz(liste)
    return {"islem": islem, "sayi": len(kayit["ogeler"])}

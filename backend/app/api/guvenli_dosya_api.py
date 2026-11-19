"""Güvenli dosya API — çöpe at · taşı · geri al. Varsayılan KAPALI (kurallar: services/guvenli_dosya.py).

Kapalıyken yalnız `GET /durum` ve `PUT /ayar` yanıt verir; işlem uçları 404 döner, dosya
gezgini salt okunur kalır. Kimlikler dosya gezgininin kimlikleridir (`dosya_api._coz`) ve her
yol okuma ile AYNI dört kapıdan geçer (`dosya_api._guvenli`).

Akış: `POST /hazirla` (diske dokunmaz, özet + onay kodu) → kullanıcı onaylar →
`POST /uygula {onay}` → günlüğe yazılır → `POST /geri-al/{işlem}`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api import dosya_api as d
from app.api import galeri_api as g
from app.services import guvenli_dosya as gd

router = APIRouter(prefix="/api/guvenli-dosya", tags=["guvenli-dosya"])


class Ayar(BaseModel):
    acik: bool
    anahtar: str | None = None


class Hazirla(BaseModel):
    kaynak: Literal["dosya", "galeri"] = "dosya"
    tur: Literal["cop", "tasi"]
    ogeler: list[str] = Field(min_length=1, max_length=gd.AZAMI_OGE)
    hedef: str | None = None
    gizli: bool = False


class Uygula(BaseModel):
    onay: str = Field(min_length=1, max_length=200)


def _kapi() -> None:
    if not gd.acik():
        raise HTTPException(404, "Güvenli dosya işlemleri kapalı.")


def _hata(e: gd.IslemHatasi) -> HTTPException:
    return HTTPException(e.kod, e.mesaj)


def _galeri_yollari(body: Hazirla) -> tuple[list[tuple[Path, Path]], Path | None]:
    """Galeri kimlikleri: galerinin KENDİ beş kapısı (yol uygun · kök · medya · imza · resolve).
    Galeride yalnız medya DOSYASI işlenir (klasör çöpe atılmaz); hedef bir galeri klasörü olmalı."""
    kokler = g._kok_yollari()

    def kok_bul(p: Path) -> Path:
        adaylar = [k for k in kokler if g._kok_altinda(p, [k])]
        if not adaylar:
            raise HTTPException(403, "Bu yol galeri klasörlerinin dışında.")
        return max(adaylar, key=lambda k: len(str(k)))

    yollar = []
    for k in body.ogeler:
        gercek = g._guvenli_dosya(g._coz(k))
        yollar.append((gercek, kok_bul(gercek)))
    hedef = g._guvenli_klasor(g._coz(body.hedef)) if body.hedef is not None else None
    return yollar, hedef


def _onbellekleri_bosalt() -> None:
    d._LISTE_ONBELLEK.clear()
    g._TUM_ONBELLEK = (0.0, (), [])


@router.get("/durum")
async def durum():
    return {"acik": gd.acik(), "anahtar_kurulu": gd.cihaz_yetki.anahtar_kurulu()}


@router.put("/ayar")
async def ayar(body: Ayar):
    try:
        gd.ayarla(body.acik, body.anahtar)
    except gd.IslemHatasi as e:
        raise _hata(e)
    return {"ok": True, "acik": gd.acik()}


@router.post("/hazirla")
def hazirla(body: Hazirla):
    _kapi()
    if body.kaynak == "galeri":
        yollar, hedef = _galeri_yollari(body)
    else:
        yollar = [d._guvenli(d._coz(k), body.gizli) for k in body.ogeler]
        hedef = None
        if body.hedef is not None:
            hedef, _ = d._guvenli(d._coz(body.hedef), body.gizli)
    try:
        return {"ok": True, **gd.hazirla(body.tur, yollar, hedef)}
    except gd.IslemHatasi as e:
        raise _hata(e)


@router.post("/uygula")
def uygula(body: Uygula):
    _kapi()
    try:
        r = gd.uygula(body.onay)
    except gd.IslemHatasi as e:
        raise _hata(e)
    _onbellekleri_bosalt()
    return {"ok": True, **r}


@router.get("/gunluk")
async def gunluk():
    _kapi()
    return {"ok": True, "islemler": [
        {"id": k["id"], "tur": k["tur"], "zaman": k["zaman"], "geri_alindi": k["geri_alindi"],
         "sayi": len(k["ogeler"]), "adlar": [Path(o["once"]).name for o in k["ogeler"]][:10]}
        for k in gd.gunluk()[:50]]}


@router.post("/geri-al/{islem}")
def geri_al(islem: str):
    _kapi()
    try:
        r = gd.geri_al(islem)
    except gd.IslemHatasi as e:
        raise _hata(e)
    _onbellekleri_bosalt()
    return {"ok": True, **r}

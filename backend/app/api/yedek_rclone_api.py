"""rclone yedek denetimi uçları — prefix `/api/yedekleme/rclone`.

Yedek sekmesindeki BULUTTA (uzak gezgini), AYARLAR (uzak adı/yol/performans) ve
"Kontrol et" / "Kuru çalıştır" düğmeleri. Mantık `services/rclone_yedek.py`'de.
Kapı: Drive yedeklemesiyle aynı (`require_yedekleme`) — ayrı bir satılan özellik değil,
yedeğin denetim yüzü.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.yedekleme import require_yedekleme
from app.limiter import limiter
from app.services import rclone_yedek as _r

router = APIRouter(prefix="/api/yedekleme/rclone", tags=["yedekleme"],
                   dependencies=[Depends(require_yedekleme)])


class AyarGovdesi(BaseModel):
    uzak: str | None = None
    yol: str | None = None
    bant: str | None = None
    aktarim: int | None = None
    denetleyici: int | None = None
    haric: list[str] | None = None


@router.get("/durum")
@limiter.limit("60/minute")
async def durum(request: Request):
    return await _r.durum()


@router.post("/ayar")
@limiter.limit("30/minute")
async def ayar(request: Request, govde: AyarGovdesi):
    try:
        _r.ayar_kaydet(govde.model_dump(exclude_none=True), await _r.uzaklar())
    except _r.AyarHatasi as e:
        raise HTTPException(400, {"kod": e.kod})
    return await _r.durum()


@router.get("/gozat")
@limiter.limit("60/minute")
async def gozat(request: Request, yol: str | None = Query(None)):
    try:
        return await _r.gozat(yol)
    except _r.AyarHatasi as e:
        raise HTTPException(400, {"kod": e.kod})


@router.post("/kontrol")
@limiter.limit("10/minute")
async def kontrol(request: Request):
    return await _r.is_baslat("kontrol")


@router.get("/kontrol/sonuc")
@limiter.limit("120/minute")
async def kontrol_sonuc(request: Request):
    return _r.is_durumu("kontrol")


@router.post("/kuru")
@limiter.limit("10/minute")
async def kuru(request: Request):
    return await _r.is_baslat("kuru")


@router.get("/kuru/sonuc")
@limiter.limit("120/minute")
async def kuru_sonuc(request: Request):
    return _r.is_durumu("kuru")

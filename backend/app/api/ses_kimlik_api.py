"""Ses kimliği uçları — durum, rıza, kayıt, deneme, silme.

Kapılar: bayrak `SES_KIMLIK` kapalıysa (varsayılan) her uç 404. Rıza vermek, kayıt ve deneme
yalnız bu bilgisayardan (loopback, 403). Kayıt ve deneme rıza ister (409). Rızayı geri çekmek
ve kaydı silmek her yerden serbest (güvenli yön); rıza geri çekilince ses izi de silinir.

Ses dosyaları yalnız istek süresince bellekte durur; diske yalnız ortalama gömme yazılır.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.services import biyometrik_riza, ses_kimlik
from app.services.ag_ayari import loopback_istemci

EN_COK_KLIP = 6
EN_COK_BAYT = 5 * 1024 * 1024


def ses_kimlik_kapisi() -> None:
    if not ses_kimlik.bayrak_acik():
        raise HTTPException(status_code=404, detail="Not Found")


def _yerel(request: Request) -> None:
    if not loopback_istemci(request.client.host if request.client else None):
        raise HTTPException(status_code=403, detail="Ses kimliği yalnız bu bilgisayardan ayarlanabilir")


def _riza_sart() -> None:
    if not biyometrik_riza.var_mi("ses_kimlik"):
        raise HTTPException(status_code=409, detail="Ses kimliği için rıza verilmedi")


router = APIRouter(prefix="/api/ses-kimlik", tags=["ses-kimlik"], dependencies=[Depends(ses_kimlik_kapisi)])


class RizaGovde(BaseModel):
    kabul: bool = False
    surum: int = 0


def _durum() -> dict:
    return {"acik": True, "riza": biyometrik_riza.ozet("ses_kimlik"),
            "model": {"var": ses_kimlik.model_yolu().is_file(), "yol": str(ses_kimlik.model_yolu()),
                      "indir": ses_kimlik.MODEL_URL},
            "kayit": ses_kimlik.kayit_ozeti(), "esikler": ses_kimlik.esikler()}


async def _oku(f: UploadFile) -> bytes:
    veri = await f.read(EN_COK_BAYT + 1)
    if len(veri) > EN_COK_BAYT:
        raise HTTPException(status_code=413, detail="Ses dosyası çok büyük (en çok 5 MB)")
    return veri


@router.get("/durum")
async def durum() -> dict:
    return _durum()


@router.post("/riza", dependencies=[Depends(_yerel)])
async def riza_ver(g: RizaGovde) -> dict:
    if not g.kabul:
        raise HTTPException(status_code=400, detail="Rıza için açık onay gerekir")
    try:
        biyometrik_riza.ver("ses_kimlik", g.surum)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return _durum()


@router.delete("/riza")
async def riza_geri_cek() -> dict:
    biyometrik_riza.geri_cek("ses_kimlik")
    ses_kimlik.riza_geri_cekildi()
    return _durum()


@router.post("/kayit", dependencies=[Depends(_yerel), Depends(_riza_sart)])
async def kayit(sesler: list[UploadFile] = File(...)) -> dict:
    if len(sesler) > EN_COK_KLIP:
        raise HTTPException(status_code=413, detail=f"En çok {EN_COK_KLIP} kayıt gönderilebilir")
    veriler = [await _oku(f) for f in sesler]
    try:
        sonuc = await asyncio.to_thread(ses_kimlik.kaydet, veriler)
    except ses_kimlik.ModelYok as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except ses_kimlik.RizaYok as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    finally:
        veriler.clear()
    return {"sonuc": sonuc, **_durum()}


@router.delete("/kayit")
async def kayit_sil() -> dict:
    ses_kimlik.sil()
    return _durum()


@router.post("/dene", dependencies=[Depends(_yerel), Depends(_riza_sart)])
async def dene(ses: UploadFile = File(...)) -> dict:
    if not ses_kimlik.kayit_ozeti().get("var"):
        raise HTTPException(status_code=409, detail="Önce sesinizi kaydedin")
    veri = await _oku(ses)
    r = await asyncio.to_thread(ses_kimlik.dogrula, veri)
    del veri
    if r is None:
        raise HTTPException(status_code=409, detail="Ses kimliği şu an kullanılamıyor (model ya da kayıt eksik)")
    return {"skor": r.skor, "sure_sn": r.sure_sn, "esik": r.esik(), "kabul": r.kabul()}

"""Kamera görüşü uçları — durum, rıza, "Yuki bak", `/ws/gorus` kare akışı.

Kapılar (sırayla):
  1. Bayrak `GORUS` kapalıysa (varsayılan) her HTTP ucu 404, WS 4404 — kayıtsız uçla aynı.
     Bayrak istek anında okunur: önce `app.config.GORUS` (G4 ekler), yoksa ortam.
  2. Rıza vermek, bakmak ve kamera akışı YALNIZ bu bilgisayardan (loopback). Telefondan /
     ağdan gelen istek 403, WS 4403: görüntü makineden çıkmasın, rıza başkası adına verilmesin.
  3. WS: erişim anahtarı (`AUTH_TOKEN`, `api_guard.ws_gecer`) → 4401; köken → 4003.
  4. Rıza yoksa (ya da eski metin sürümüyle verildiyse) kamera 4409, bakış 409.
     Rıza geri çekilince açık kamera bağlantısı sıradaki karede 4409 ile kapanır.

Kare akışı: istemci (frontend/js/gorus.js) saniyede ≤1 JPEG'i ikili çerçeve yollar. Kare
yalnız bekleyen bir "Yuki bak" isteği varsa ona verilir (`gorus_bak.kare_geldi`); yoksa
hiçbir yerde tutulmaz. Saniyede ≤1 kare işlenir (yüz sayımı → varlık olayları → selam/mola
cümlesi `soyle`); arada gelen kareye yalnız `{"tip":"tamam"}` döner. Her kareye tek cevap
(istemci cevapsız yeni kare yollamaz).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.services import biyometrik_riza, gorus_bak, gorus_kare
from app.services.gorus_ses import GorusSeslendirici
from app.services.gorus_varlik import VarlikIzleyici
from app.services.ag_ayari import loopback_istemci

logger = logging.getLogger(__name__)

MIN_ARALIK_SN = 0.9
_ACIK = ("1", "true", "yes", "on")


def bayrak_acik() -> bool:
    from app import config
    deger = getattr(config, "GORUS", None)
    if deger is not None:
        return bool(deger)
    return os.getenv("GORUS", "false").strip().lower() in _ACIK


def gorus_kapisi() -> None:
    if not bayrak_acik():
        raise HTTPException(status_code=404, detail="Not Found")


def _auth_token() -> str:
    from app.config import AUTH_TOKEN
    return AUTH_TOKEN or ""


def _yerel(request: Request) -> None:
    if not loopback_istemci(request.client.host if request.client else None):
        raise HTTPException(status_code=403, detail="Kamera görüşü yalnız bu bilgisayardan kullanılabilir")


def _riza_sart() -> None:
    if not biyometrik_riza.var_mi("gorus"):
        raise HTTPException(status_code=409, detail="Kamera görüşü için rıza verilmedi")


router = APIRouter(tags=["gorus"])
_http = APIRouter(prefix="/api/gorus", dependencies=[Depends(gorus_kapisi)])


class RizaGovde(BaseModel):
    kabul: bool = False
    surum: int = 0


class BakGovde(BaseModel):
    soru: str = ""


@_http.get("/durum")
async def durum() -> dict:
    return {"acik": True, "riza": biyometrik_riza.ozet("gorus"),
            "model": await gorus_bak.model_durumu(), "kamera_bagli": gorus_bak.istemci_sayisi() > 0}


@_http.post("/riza", dependencies=[Depends(_yerel)])
async def riza_ver(g: RizaGovde) -> dict:
    if not g.kabul:
        raise HTTPException(status_code=400, detail="Rıza için açık onay gerekir")
    try:
        biyometrik_riza.ver("gorus", g.surum)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return {"riza": biyometrik_riza.ozet("gorus")}


@_http.delete("/riza")
async def riza_geri_cek() -> dict:
    # Geri çekmek her yerden serbest (kapatmak güvenli yön); açık kamera sıradaki karede kapanır.
    biyometrik_riza.geri_cek("gorus")
    return {"riza": biyometrik_riza.ozet("gorus")}


@_http.post("/bak", dependencies=[Depends(_yerel), Depends(_riza_sart)])
async def bak(g: BakGovde) -> dict:
    return await gorus_bak.bak(g.soru)


router.include_router(_http)


async def _ws_kapilari(ws: WebSocket) -> tuple[int, str] | None:
    if not bayrak_acik():
        return 4404, "gorus kapali"
    if not loopback_istemci(ws.client.host if ws.client else None):
        return 4403, "yalniz bu bilgisayar"
    token = _auth_token()
    if token:
        from app.services import api_guard
        if not api_guard.ws_gecer(ws, ws.query_params.get("token", ""), token):
            return 4401, "Unauthorized"
    # Kilit kuruluysa yerel soket de kilit oturum token'ı ister — HTTP ve öbür WS'lerle aynı kural
    # (denetim 2026-11-16, API-F001: kilitliyken kamera akışı token'sız açılıyordu).
    from app.services import ag_ayari
    if not ag_ayari.ws_izinli(ws):
        return 4401, "Unauthorized"
    from app.api.websocket import _check_ws_origin
    if not _check_ws_origin(ws):
        return 4003, "Origin not allowed"
    if not biyometrik_riza.var_mi("gorus"):
        return 4409, "riza yok"
    return None


@router.websocket("/ws/gorus")
async def ws_gorus(ws: WebSocket) -> None:
    red = await _ws_kapilari(ws)
    # Kabul edip sebebiyle kapat: el sıkışma reddi tarayıcıya 1006 görünür, kod okunmaz.
    # Kare kabul edilmeden önce kapanır; hiçbir kapı geçilmeden kare işlenmez.
    await ws.accept()
    if red:
        await ws.close(code=red[0], reason=red[1])
        return
    gorus_bak.istemci_baglandi()
    izleyici = VarlikIzleyici()
    son = 0.0
    try:
        while True:
            m = await ws.receive()
            if m.get("type") == "websocket.disconnect":
                break
            veri = m.get("bytes")
            if veri is None:
                continue
            if not bayrak_acik() or not biyometrik_riza.var_mi("gorus"):
                await ws.close(code=4409, reason="riza geri cekildi")
                break
            if not gorus_bak.kare_gecerli(veri):
                await ws.send_json({"tip": "hata", "neden": "kare"})
                continue
            gorus_bak.kare_geldi(veri)        # bekleyen "Yuki bak" yoksa no-op (kare tutulmaz)
            simdi = time.monotonic()
            if simdi - son < MIN_ARALIK_SN:
                del veri
                # Her kareye cevap: istemci cevap gelmeden yeni kare yollamaz (geri basınç).
                await ws.send_json({"tip": "tamam"})
                continue
            son = simdi
            await ws.send_json(await _kare_isle(veri, izleyici))
            del veri
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        gorus_bak.istemci_ayrildi()


async def _kare_isle(veri: bytes, izleyici: VarlikIzleyici) -> dict:
    """Yüz say → varlık olayları → (gelişte) tanıma → söylenecek cümle."""
    try:
        yuz, ms = await asyncio.to_thread(gorus_kare.yuz_say, veri)
    except gorus_kare.KareHatasi as e:
        return {"tip": "hata", "neden": str(e)}
    olaylar = izleyici.kare(yuz, time.monotonic())
    ad = None
    if "tanima_iste" in olaylar:
        olaylar.remove("tanima_iste")
        ad = await gorus_kare.tani(veri)
        olaylar += izleyici.tanima_sonucu(ad, time.monotonic())
    soyle = None
    for o in olaylar:
        cumle = _seslendirici.cumle({"olay": o, "ad": ad})
        soyle = soyle or cumle
    return {"tip": "durum", "durum": izleyici.durum, "yuz": yuz, "ms": round(ms, 1),
            "olaylar": olaylar, "soyle": soyle}


_seslendirici = GorusSeslendirici()

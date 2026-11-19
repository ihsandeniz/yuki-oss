"""Sağlık ölçeri ucu — HQ › Bilgisayarım › SAĞLIK ÖLÇERİ.

GET  /api/saglik      son kaydı + yaşını OKUR (ölçüm koşturmaz; panel sık yeniler).
POST /api/saglik/olc  hafif sensörleri şimdi ölçer ve günün kaydına yazar.

Kayıt yoksa 404 değil `durum: "kayit-yok"` döner: ilk gün beklenen durumdur,
404 arayüzde "uç bozuk" gibi görünürdü.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request

from app.limiter import limiter
from app.services import saglik_olcer

router = APIRouter(prefix="/api/saglik", tags=["saglik"])


@router.get("")
@limiter.limit("60/minute")
async def saglik_son(request: Request):
    return await asyncio.to_thread(saglik_olcer.son_kayit)


@router.post("/olc")
@limiter.limit("6/minute")
async def saglik_olc(request: Request):
    await asyncio.to_thread(saglik_olcer.olc_ve_kaydet)
    return await asyncio.to_thread(saglik_olcer.son_kayit)

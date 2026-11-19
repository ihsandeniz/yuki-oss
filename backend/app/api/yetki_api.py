"""Yetki özeti — ön yüz düğme/sekme göstermek için okur.

GET /api/yetki → {tools, features, characters, all_characters}
Açık kaynak sürümde kademe yok: her araç, özellik ve karakter açık (bkz. services/yetki.py).
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.limiter import limiter
from app.services import yetki

router = APIRouter(prefix="/api/yetki", tags=["yetki"])


@router.get("")
@limiter.limit("100/minute")
async def get_yetki(request: Request):  # noqa: ARG001 — limiter Request ister
    return yetki.ozet()

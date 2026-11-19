"""İndirilen Python kütüphanelerini **çalışırken** devreye alma.

🔑 NEDEN VAR ( Dalga 2 FAZ 4): `app/pydeps.py` `sys.path`'i tazeleyebiliyor
ve bunun yeniden başlatma gerektirmediği ölçüldü — ama onu **çağıran uç yoktu**.
Kullanıcı yüz tanıma kütüphanesini indiriyor, indirme başarıyla bitiyor, özellik
yine "kütüphane inmemiş" diyordu. Mekanizmanın varlığı, devreye girdiği anlamına
gelmiyor; eksik olan tek şey bu dosyaydı.

Akış:
    model-manager.js indirmeyi bitirir → `POST /api/pydeps/reload`
    → `pydeps.tazele()` diski tarar, yeni ağacı `sys.path`'e SONA ekler
    → `insightface_havuzu.unut()` bayat örneği düşürür
    → yanıt: özellik artık kullanılabilir mi

🔒 Bu uç **token ister** (`_SKIP_PATHS`'te değil) ve **yol parametresi almaz**.
Dizin `pydeps.kesfet()` içinde türetilir; dışarıdan yol kabul eden bir sürüm,
`sys.path`'e keyfi dizin ekleten bir uzaktan kod çalıştırma kapısı olurdu.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app import pydeps
from app.limiter import limiter
from app.mesajlar import M

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pydeps", tags=["pydeps"])

#: Uçta bildirilecek yetenekler: ad → gereken modüller.
#: Yeni bir "sonradan inen" özellik eklenince buraya bir satır düşer.
YETENEKLER: dict[str, tuple[str, ...]] = {
    "face_recognition": ("insightface", "onnx"),
}


def _yetenekler() -> dict:
    return {
        ad: dict(zip(("available", "unavailable_reason"), pydeps.kullanilabilir(*moduller)))
        for ad, moduller in YETENEKLER.items()
    }


@router.get("/status")
@limiter.limit("60/minute")
async def status(request: Request):
    """Hangi ağaçlar bağlı, hangi özellik kullanılabilir — **veri olarak**.

    📏 Ledger: yetenek sorusu 4xx/5xx ile sorulmaz. Burası kütüphane inmemişken
    de 200 döner; "yok" ile "bozuk" arayüzde ayırt edilebilsin.
    """
    return {"bound": pydeps.durum(), "discovered": pydeps.kesfet(),
            "capabilities": _yetenekler()}


@router.post("/reload")
@limiter.limit("12/minute")
async def reload(request: Request):
    """İndirme bittikten sonra kütüphaneyi devreye al (yeniden başlatma gerekmez)."""
    sonuc = pydeps.tazele()
    yetenekler = _yetenekler()
    if sonuc["eklenen"]:
        logger.info("pydeps tazelendi: %s", ", ".join(sonuc["eklenen"]))
    return {
        "ok": True,
        "newly_bound": sonuc["eklenen"],
        "already_bound": sonuc["zaten_bagliydi"],
        "bound": sonuc["durum"],
        "capabilities": yetenekler,
        # Dürüst geri bildirim: hiçbir şey eklenmediyse ve özellik hâlâ yoksa
        # kullanıcıya "tamam" demek yanlış olur — indirme eksik bitmiş olabilir.
        "note": None if any(y["available"] for y in yetenekler.values())
        else M("pydeps.bulunamadi"),
    }

"""Kurulum sihirbazı + hata günlüğü API'si.

🔴 2026-08-01: ürün temiz bir Windows'ta çalışmadığında elimizde hiçbir teşhis verisi
yoktu. Bu uçlar "neyin bozuk olduğunu ürünün kendisi söylesin" için var.
"""

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.limiter import limiter

router = APIRouter(prefix="/api", tags=["kurulum"])


@router.get("/self-check")
@limiter.limit("20/minute")
async def self_check(request: Request):
    """Ortamı denetle: neyin çalıştığı, neyin çalışmadığı, nasıl düzeltileceği."""
    from app.services.self_check import calistir
    return await calistir()


class OnarimIstegi(BaseModel):
    kimlik: str


@router.post("/self-check/repair")
@limiter.limit("10/minute")
async def self_check_repair(request: Request, body: OnarimIstegi):
    """Otomatik onarılabilir bir bulguyu düzelt (yalnız güvenli işler)."""
    from app.services.self_check import onar
    return await onar(body.kimlik)


@router.post("/self-check/install")
@limiter.limit("3/minute")
async def self_check_install(request: Request, body: OnarimIstegi):
    """Kullanıcının makinesine bir şey KURAN aksiyon — /repair'den bilerek ayrı uç.

    Yalnız kullanıcı SAĞLIK panelinde ne olacağı yazan düğmeye bilerek bastığında
    çağrılır; Windows ayrıca yönetici onayı (UAC) sorar. Aynı uca konsaydı toplu
    onarım akışına sessizce karışabilirdi. Sıkı limit: kurulum tekrarlanacak iş değil.
    """
    from app.services.self_check import kur
    return await kur(body.kimlik)


@router.get("/errors/recent")
@limiter.limit("30/minute")
async def errors_recent(request: Request, adet: int = 50):
    """Son hatalar — en yeni önce."""
    from app.services.error_log import son_kayitlar, ozet
    adet = max(1, min(adet, 200))
    return {"ozet": ozet(), "kayitlar": son_kayitlar(adet)}


@router.get("/errors/export", response_class=PlainTextResponse)
@limiter.limit("10/minute")
async def errors_export(request: Request, adet: int = 100):
    """Tek tıkla paylaşılabilir düz metin (anahtarlar maskeli)."""
    from app.services.error_log import disari_aktar
    return disari_aktar(max(1, min(adet, 200)))


@router.delete("/errors")
@limiter.limit("5/minute")
async def errors_clear(request: Request):
    """Günlüğü sil. Silinemezse `ok:false` — eskiden her durumda `ok:true` dönüyordu."""
    import logging
    from app.mesajlar import M
    from app.services.error_log import temizle_gunluk
    try:
        return {"ok": True, "silinen": temizle_gunluk()}
    except Exception as e:
        logging.getLogger(__name__).debug("hata günlüğü silinemedi: %s", e)
        return {"ok": False, "silinen": 0, "error": M("saglik.gunluk-silinemedi")}

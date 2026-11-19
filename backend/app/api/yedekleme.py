"""Drive yedekleme uçları ( FAZ 4) — prefix `/api/yedekleme`.

Kademe: **Pro**. Kapı router düzeyinde (`require_yedekleme`) — `todo.py`'nin dersi:
uç uç yazılan kapıda bir uç atlanır ve kimse fark etmez.

🔑 **Neden `planner`'ın kapısı yeniden kullanılmadı:** yedekleme ayrı bir satılan
özelliktir; `planner` kapısına asılsaydı, ileride biri PLAN ekranını Free'ye
indirdiğinde yedekleme de sessizce Free'ye düşerdi. Kademe tablosunda kendi satırı
var (`drive_backup`).
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.limiter import limiter
from app.mesajlar import M
from app.services import yedekleme as _y

logger = logging.getLogger(__name__)


def require_yedekleme() -> None:
    try:
        from app.services import yetki
        izin = yetki.feature_allowed("drive_backup")
    except Exception:
        izin = False          # hata → kapalı (üst kademe sızmasın)
    if not izin:
        raise HTTPException(
            status_code=403,
            detail=M("yedek.pro-ozelligi"),
        )


router = APIRouter(prefix="/api/yedekleme", tags=["yedekleme"],
                   dependencies=[Depends(require_yedekleme)])

#: Koşan turun görevi — ikinci bir "şimdi yedekle" isteğinde yeni tur başlatmamak
#: için tutulur. `tur_calistir` ayrıca kendi kilidini de kontrol eder (iki kapı:
#: biri istek düzeyinde, biri motor düzeyinde — zamanlayıcı istek katmanından geçmez).
_gorev: asyncio.Task | None = None


class AyarGovdesi(BaseModel):
    acik: bool | None = None
    yuki_verisi: bool | None = None
    zamanlama: str | None = None
    tek_dosya_tavani_mb: int | None = None
    tur_bayt_tavani_mb: int | None = None
    istisnalar: list[str] | None = None


class KaynakGovdesi(BaseModel):
    yol: str


@router.get("/durum")
@limiter.limit("60/minute")
async def durum(request: Request):
    return _y.durum()


@router.post("/ayar")
@limiter.limit("30/minute")
async def ayar_kaydet(request: Request, govde: AyarGovdesi):
    ayar = _y.ayarlar()
    yeni = govde.model_dump(exclude_none=True)

    if "zamanlama" in yeni:
        z = (yeni["zamanlama"] or "").strip()
        # Boş string = "yalnız elle". Ayrı bir alan açmak yerine None'a çevriliyor.
        if z and not _saat_gecerli(z):
            raise HTTPException(400, M("yedek.zamanlama-bicim"))
        yeni["zamanlama"] = z or None

    for alan in ("tek_dosya_tavani_mb", "tur_bayt_tavani_mb"):
        if alan in yeni and int(yeni[alan]) < 1:
            raise HTTPException(400, M("yedek.en-az-bir", alan=alan))

    ayar.update(yeni)
    _y.ayar_yaz(ayar)

    # Zamanlama değiştiyse iş hemen yeniden kurulur — yoksa değişiklik ancak bir
    # sonraki açılışta etkili olur ve kullanıcı "kaydettim, çalışmadı" der.
    try:
        from app.services import scheduler
        scheduler.yedekleme_isini_kur()
    except Exception as e:  # noqa: BLE001
        logger.warning("yedekleme zamanlaması kurulamadı: %s", e)

    return _y.durum()


@router.post("/kaynak")
@limiter.limit("30/minute")
async def kaynak_ekle(request: Request, govde: KaynakGovdesi):
    try:
        kaynak = _y.kaynak_ekle(govde.yol)
    except _y.YedeklemeHatasi as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "kaynak": kaynak, "durum": _y.durum()}


@router.delete("/kaynak/{kaynak_id}")
@limiter.limit("30/minute")
async def kaynak_sil(request: Request, kaynak_id: str):
    if not _y.kaynak_sil(kaynak_id):
        raise HTTPException(404, M("yedek.kaynak-yok"))
    return {"ok": True, "durum": _y.durum()}


@router.post("/calistir")
@limiter.limit("10/minute")
async def calistir(request: Request):
    """Turu başlatır ve **hemen döner** — istek boyunca beklemez.

    🔴 Beklemek kusur olurdu: 10 GB'lık bir klasörün turu dakikalarca sürer, HTTP
    isteği vekil/tarayıcı zaman aşımına düşer ve kullanıcı turun başarısız olduğunu
    sanar — oysa arka planda sürmektedir. İlerleme `/durum`dan okunur.
    """
    global _gorev
    if _y.calisiyor_mu() or (_gorev and not _gorev.done()):
        raise HTTPException(409, M("yedek.tur-suruyor"))
    ayar = _y.ayarlar()
    if not ayar.get("acik", False):
        raise HTTPException(400, M("yedek.kapali"))
    _gorev = asyncio.create_task(_y.tur_calistir("elle"))
    return {"ok": True, "baslatildi": True}


@router.get("/drive-kullanim")
@limiter.limit("10/minute")
async def drive_kullanim(request: Request):
    """Drive alanı — 'dolu' hatasını yaşamadan önce gösterebilmek için."""
    from app.services import google_client as g
    try:
        return await g.kullanim()
    except g.GoogleBagliDegil:
        raise HTTPException(400, M("yedek.google-bagli-degil"))
    except g.GoogleYetkiDustu as e:
        # 401 DEĞİL: 401 uygulamanın kendi oturum kilidi demektir (authFetch/panel o kodla
        # "oturum kilitli" der). Google bağlantısının düşmesi ayrı bir durum → 409.
        raise HTTPException(409, str(e))


def _saat_gecerli(s: str) -> bool:
    parcalar = s.split(":")
    if len(parcalar) != 2:
        return False
    try:
        sa, dk = int(parcalar[0]), int(parcalar[1])
    except ValueError:
        return False
    return 0 <= sa <= 23 and 0 <= dk <= 59

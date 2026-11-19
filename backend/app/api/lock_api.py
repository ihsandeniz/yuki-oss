"""Uygulama kilidi uçları — açılış parolası.

Çekirdek ve tasarım gerekçeleri: `app/services/app_lock.py`.

## Uçların ikiye ayrılması

**Açık uçlar** (`/status`, `/unlock`) kilitliyken de cevap verir — kilit ekranı
bunları çağırmak zorundadır, token almak için çağırıyor zaten. `main.py`'deki
`_KILIT_SERBEST` kümesinde tam eşleşmeyle listelenirler.

**Korumalı uçlar** (`/set`, `/disable`, `/lock`) kilidin arkasındadır. `/set` ve
`/disable` ayrıca **mevcut parolayı** ister: oturumu ele geçirmiş biri (açık
bırakılmış makine başına oturan kişi) parolayı sessizce değiştirip kalıcı erişim
kuramasın. Bu, "oturum ≠ parola bilgisi" ayrımıdır.

## Deneme kilidi

Parola denemeleri `login_guard`'ın **PASSWORD** yoluna yazılır. O yol dolunca
yalnız parola kapanır, yüz açık kalır (ve tersi) — kullanıcı asla tamamen
kilitlenmez. Bu mimari `login_guard.py`'de zaten kuruluydu; parola yolu bugüne
kadar boştu, burada bağlanıyor.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.limiter import limiter
from app.mesajlar import M, Mc
from app.services import app_lock, login_guard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lock", tags=["lock"])


def _istemci_ip(request: Request) -> str:
    """Deneme sayacının anahtarı — `X-Forwarded-For`'un DEĞERİ BİLEREK okunmuyor.

    Başlığı okusaydık istemci kendi IP'sini uydurup deneme sayacını her istekte
    sıfırlayabilirdi; kilit tamamen anlamsız olurdu. ⚠️ `request.client.host` tek
    başına da yetmiyordu: uvicorn `proxy_headers` açıkken onu bu başlıktan yeniden
    yazar (denetim 2026-11-16, SEC-F002). Başlıklı istekler tek kovaya düşer → ag_ayari.
    """
    from app.services.ag_ayari import deneme_anahtari
    return deneme_anahtari(request)


class ParolaGiris(BaseModel):
    parola: str = Field(..., min_length=1, max_length=app_lock.MAX_UZUNLUK)


class ParolaKur(BaseModel):
    yeni: str = Field(..., min_length=app_lock.MIN_UZUNLUK,
                      max_length=app_lock.MAX_UZUNLUK)
    # Kilit zaten kuruluysa ZORUNLU; ilk kurulumda boş bırakılır.
    mevcut: str | None = Field(default=None, max_length=app_lock.MAX_UZUNLUK)


# ══════════════════════════════════════════════════════════════════════════
#  Açık uçlar — kilit ekranı
# ══════════════════════════════════════════════════════════════════════════

@router.get("/status")
@limiter.limit("60/minute")
async def status(request: Request):
    """Kilit kurulu mu, hangi yollar açık? **Parola hakkında hiçbir şey dönmez.**"""
    from app.config import FACE_AUTH_ENABLED
    from app.services import face_multi_auth

    yuzle_girilebilir = False
    if FACE_AUTH_ENABLED:
        try:
            yetenek = face_multi_auth.yetenek()
            yuzle_girilebilir = bool(yetenek.get("available")) and \
                face_multi_auth.owner_enrolled()
        except Exception as e:
            # Yüz tarafı çökse bile parola yolu cevap vermeli — kilit ekranı
            # tamamen ölmesin.
            logger.warning("Kilit durumu: yüz yeteneği okunamadı: %s", e)

    return {
        **app_lock.durum(),
        "yuzle_girilebilir": yuzle_girilebilir,
        "guard": login_guard.state(_istemci_ip(request)),
    }


@router.post("/unlock")
@limiter.limit("10/minute")
async def unlock(request: Request, giris: ParolaGiris):
    """Parolayla kilidi aç → oturum token'ı.

    Rate limit (10/dk) `login_guard`'ın YERİNE geçmez, tamamlar: limit tek IP'nin
    hızını keser, guard ise N hatadan sonra yolu tümden kapatır.
    """
    if not app_lock.kurulu():
        # Kapı yoksa açılmaz. 404 değil 409: "böyle bir uç yok" değil, "bu
        # işlemin ön koşulu yok" demek istiyoruz.
        raise HTTPException(status_code=409, detail=M("kilit.kurulu-degil"))

    ip = _istemci_ip(request)
    kalan = login_guard.locked_for(login_guard.PASSWORD, ip)
    if kalan > 0:
        raise HTTPException(
            status_code=429,
            detail=login_guard.lock_message(
                login_guard.PASSWORD, kalan,
                login_guard.locked_for(login_guard.FACE, ip) == 0),
            headers={"Retry-After": str(int(kalan))},
        )

    if app_lock.parola_dogrula(giris.parola):
        login_guard.record_success(login_guard.PASSWORD, ip)
        return {"ok": True, "token": app_lock.oturum_ac()}

    basarisiz = login_guard.record_fail(login_guard.PASSWORD, ip)
    if basarisiz["locked"]:
        raise HTTPException(
            status_code=429,
            detail=login_guard.lock_message(
                login_guard.PASSWORD, basarisiz["lock_seconds"],
                login_guard.locked_for(login_guard.FACE, ip) == 0),
            headers={"Retry-After": str(int(basarisiz["lock_seconds"]))},
        )

    kalan_hak = basarisiz["remaining"]
    ek = f" {Mc('kilit.kalan-hak', kalan_hak)}" if kalan_hak is not None else ""
    raise HTTPException(status_code=401, detail=M("kilit.parola-yanlis") + ek)


# ══════════════════════════════════════════════════════════════════════════
#  Korumalı uçlar — Ayarlar → Güvenlik
# ══════════════════════════════════════════════════════════════════════════

@router.post("/set")
@limiter.limit("10/minute")
async def parola_kur(request: Request, giris: ParolaKur):
    """Parolayı kur ya da değiştir.

    Kilit zaten kuruluysa `mevcut` ZORUNLU — açık bir oturumun tek başına
    parolayı değiştirebilmesi, makine başında bırakılan bir oturumu kalıcı
    erişime çevirirdi.
    """
    ip = _istemci_ip(request)

    if app_lock.kurulu():
        kalan = login_guard.locked_for(login_guard.PASSWORD, ip)
        if kalan > 0:
            raise HTTPException(
                status_code=429,
                detail=login_guard.lock_message(login_guard.PASSWORD, kalan, False),
                headers={"Retry-After": str(int(kalan))},
            )
        if not giris.mevcut or not app_lock.parola_dogrula(giris.mevcut):
            login_guard.record_fail(login_guard.PASSWORD, ip)
            raise HTTPException(status_code=401, detail=M("kilit.mevcut-parola-yanlis"))
        login_guard.record_success(login_guard.PASSWORD, ip)

    try:
        app_lock.parola_kur(giris.yeni)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except OSError as e:
        logger.error("Parola kaydedilemedi: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=M("kilit.kaydedilemedi"))

    logger.info("Uygulama kilidi kuruldu/değiştirildi.")
    # Çağıranın oturumu bilerek AÇIK bırakılıyor: parolasını değiştiren kullanıcı
    # kendi ekranından atılmaz. Diğer oturumlar da düşmez — masaüstünde tek
    # kullanıcı var, "her yerden çıkış" burada karşılığı olmayan bir kavram.
    return {"ok": True, "kurulu": True}


@router.post("/disable")
@limiter.limit("10/minute")
async def kilidi_kaldir(request: Request, giris: ParolaGiris):
    """Kilidi tamamen kaldır. Mevcut parola ZORUNLU."""
    if not app_lock.kurulu():
        return {"ok": True, "kurulu": False}

    ip = _istemci_ip(request)
    kalan = login_guard.locked_for(login_guard.PASSWORD, ip)
    if kalan > 0:
        raise HTTPException(
            status_code=429,
            detail=login_guard.lock_message(login_guard.PASSWORD, kalan, False),
            headers={"Retry-After": str(int(kalan))},
        )
    if not app_lock.parola_dogrula(giris.parola):
        login_guard.record_fail(login_guard.PASSWORD, ip)
        raise HTTPException(status_code=401, detail=M("kilit.parola-yanlis"))

    login_guard.record_success(login_guard.PASSWORD, ip)
    app_lock.parola_kaldir()
    logger.info("Uygulama kilidi kaldırıldı.")
    return {"ok": True, "kurulu": False}


@router.post("/lock")
@limiter.limit("30/minute")
async def simdi_kilitle(request: Request):
    """Şimdi kilitle — açık oturumları düşür, kilit ekranına dön.

    Parola sormaz: kilitlemek bir yetki değil, kullanıcının kendi ekranını
    kapatmasıdır. Kilit kurulu değilse yapacak bir şey yoktur.
    """
    if not app_lock.kurulu():
        raise HTTPException(status_code=409, detail=M("kilit.kurulu-degil"))
    app_lock.tum_oturumlari_kapat()
    return {"ok": True}

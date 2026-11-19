"""ChatGPT ile resmî giriş uçları — "Continue with ChatGPT" düğmesinin arka yüzü.

GET  /api/chatgpt/durum     giriş var mı, plan kullanımı açık mı, ChatGPT aktif sağlayıcı mı (sır YOK)
POST /api/chatgpt/giris     tarayıcıyı açar, geri dönüşü arka planda bekler (300 sn); /durum'dan izlenir
POST /api/chatgpt/sec       giriş varsa ChatGPT'yi etkin sağlayıcı yapar (kalıcı)
POST /api/chatgpt/cikis     refresh token'ı iptal eder, yerel token'ı siler
GET  /api/chatgpt/modeller  hesaba açık modeller

API anahtarı (BYOK) yolu `/api/llm/*` altında olduğu gibi açıktır; bu uçlar onu etkilemez.
Token log'a ve cevaba girmez.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import webbrowser

from fastapi import APIRouter, Request

from app.limiter import limiter
from app.mesajlar import M
from app.services.chatgpt_plan import kimlik

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chatgpt", tags=["chatgpt"])

SAGLAYICI = "chatgpt"

_kilit = threading.Lock()
_giris = {"durum": "bos", "hata": "", "url": ""}   # bos | bekliyor | tamam | hata


def _giris_isi() -> None:
    from app.services.chatgpt_plan import giris as _g

    def _ac(url: str) -> bool:
        # Tarayıcı açılamazsa kullanıcı adresi elle açabilsin diye yalnız bu durumda saklanır.
        acildi = bool(webbrowser.open(url))
        _giris["url"] = "" if acildi else url
        return acildi

    try:
        _g.giris(ac=_ac)
        _giris.update(durum="tamam", hata="", url="")
    except kimlik.PlanKimlikHatasi as e:
        _giris.update(durum="hata", hata=str(e)[:200], url="")
    except Exception as e:  # noqa: BLE001 — sır taşımayan tek satır
        logger.warning("chatgpt giriş başarısız (%s)", type(e).__name__)
        _giris.update(durum="hata", hata=type(e).__name__, url="")


def _aktif_mi() -> bool:
    from app.services import llm as _llm
    return _llm.aktif_saglayici() == SAGLAYICI


@router.get("/durum")
@limiter.limit("120/minute")
async def durum(request: Request):
    d = await asyncio.to_thread(kimlik.durum)
    return {"ok": True, **d, "aktif": _aktif_mi(),
            "giris_durumu": _giris["durum"], "giris_hatasi": _giris["hata"],
            "url": _giris["url"]}


@router.post("/giris")
@limiter.limit("6/minute")
async def giris_baslat(request: Request):
    with _kilit:
        if _giris["durum"] == "bekliyor":
            return {"ok": True, "giris_durumu": "bekliyor"}
        _giris.update(durum="bekliyor", hata="", url="")
    threading.Thread(target=_giris_isi, daemon=True, name="chatgpt-giris").start()
    return {"ok": True, "giris_durumu": "bekliyor"}


@router.post("/sec")
@limiter.limit("10/minute")
async def sec(request: Request, body: dict | None = None):
    d = await asyncio.to_thread(kimlik.durum)
    if not d.get("giris"):
        return {"ok": False, "error": M("chatgpt.giris-yok")}
    if not d.get("plan_acik"):
        return {"ok": False, "error": M("chatgpt.plan-kapali")}
    from app.api.llm_config_api import _persist_env
    from app.services import llm as _llm
    from app.services.chatgpt_plan.istemci import VARSAYILAN_MODEL
    model = str((body or {}).get("model") or "").strip() or VARSAYILAN_MODEL
    try:
        _persist_env("LLM_PROVIDER", SAGLAYICI)
        _persist_env("LLM_MODEL", model)
    except Exception as e:
        return {"ok": False, "error": M("llm.env-yazilamadi", sebep=e)}
    _llm.set_runtime_config(SAGLAYICI, model)
    return {"ok": True, "provider": SAGLAYICI, "model": model, "message": M("chatgpt.secildi", model=model)}


@router.post("/cikis")
@limiter.limit("6/minute")
async def cikis(request: Request):
    sonuc = await asyncio.to_thread(kimlik.cikis)
    _giris.update(durum="bos", hata="", url="")
    if _aktif_mi():
        from app.api.llm_config_api import _persist_env
        from app.config import LLM_MODEL
        from app.services import llm as _llm, llm_providers as _lp
        try:
            _persist_env("LLM_PROVIDER", _lp.VARSAYILAN)
        except Exception:
            logger.warning("chatgpt çıkış: LLM_PROVIDER .env'e yazılamadı")
        _llm.set_runtime_config(_lp.VARSAYILAN, LLM_MODEL)
    return {"ok": True, **sonuc}


@router.get("/modeller")
@limiter.limit("30/minute")
async def modeller(request: Request):
    from app.services.chatgpt_plan.istemci import ChatGPTAsyncClient
    liste = await ChatGPTAsyncClient().modeller(zorla=True)
    return {"ok": bool(liste), "modeller": liste}

"""Görev şeridi ölçüm sunucusu — İKİNCİ PORTTA (Faz 0c).

Gerçek olan: `api/gorev.py` uçları, `services/gorev.py` servisi (görev modu runner,
çalışma alanı kilidi, adım kaydı), `event_bus` → `/ws/realtime` olay yolu,
worktree'deki `frontend/` (/ui).
Sahte olan: LLM (her adımda `alan_yaz` isteyen, `--gecikme` sn bekleyen model).
Atölye kökü `YUKI_ATOLYE_KOK` (test geçici dizini) — gerçek veri dizinine, 
gerçek LLM'e dokunmaz. AUTH_TOKEN bu süreçte boş (yerel test).

Koşum (cwd = backend/):
    YUKI_ATOLYE_KOK=/tmp/x venv/bin/python tests/gorev_sahte_sunucu.py --port 8097
Test ucu: POST /test/baslat {"tur","ad","adimlar"} — yerel bağlamda görev başlatır.

Faz 0d  seçenekleri:
  --onay-suresi SN   taslağın düşme süresi (gerçekte 300; ölçüm için kısaltılır)
  --onay-kipi K      dokunus | masaustu (ATOLYE_DIS_ONAY)
  --dis-origin URL   dış başlatmanın kabul ettiği Origin'e ek (Playwright sayfası
                     http://127.0.0.1:<port>'tan açılır; gerçekte yalnız izinli https adresi)
  POST /test/llm {"adimlar","gecikme"} — sahte modelin ayarı (dış başlatmadan önce)
Masaüstü bildirimi GÖNDERİLMEZ: kayda alınır, /test/durum → "bildirimler".

Harness H4 : POST /test/oneri {"ad","tur"?,"istek"?,"kaynak"?,"ref"?} — öneri kaydı
(motorun yazdığı biçim), GET /test/kuyruk — iş sırası kayıtları.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("OPENROUTER_API_KEY", "sahte-test")
os.environ["ATOLYE"] = "true"   # sahte Atölye sunucusu: test sürecinin ATOLYE=false'u (conftest) buraya geçmesin
if not os.environ.get("YUKI_ATOLYE_KOK"):
    sys.exit("YUKI_ATOLYE_KOK ver — gerçek <atölye kökü> kullanılmaz")

from fastapi import FastAPI, Request                        # noqa: E402
from fastapi.responses import JSONResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles                 # noqa: E402

import app.config as _cfg                                    # noqa: E402
_cfg.AUTH_TOKEN = ""

import app.api.websocket as wsmod                            # noqa: E402
import app.services.llm_router as llm_router                 # noqa: E402
from app.api import gorev as gorev_api                       # noqa: E402
from app.services import gorev as gorev_mod                  # noqa: E402
from app.services.gorev import GorevHatasi, get_gorev_servisi  # noqa: E402
from app.services.atolye.baglam import yerel_baglam    # noqa: E402
from tests.atolye_yardimci import _arac_akisi, _icerik_akisi  # noqa: E402


AYAR = {"gecikme": 0.5, "adimlar": 1000}
SITE = ("<!doctype html><html lang=\"tr\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>Deneme</title></head><body><main><h1>Gece</h1><p>Bahçede yıldızlar var, küçük bir deneme sayfası.</p></main></body></html>")
_sayac = {"n": 0}
BILDIRIMLER: list[dict] = []


async def _sahte_create(**kw):
    await asyncio.sleep(AYAR["gecikme"])
    _sayac["n"] += 1
    n = _sayac["n"]
    if n >= AYAR["adimlar"]:
        return _icerik_akisi("bitti")
    if AYAR.get("site") and n == 1:      # doğrulamadan geçen sayfa → görev `bitti`
        return _arac_akisi([("c1", "alan_yaz", {"yol": "index.html", "icerik": SITE})])
    return _arac_akisi([(f"c{n}", "alan_yaz", {"yol": f"adim-{n}.txt", "icerik": "x"})])


def _sahte_router():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=_sahte_create)
    r = MagicMock()
    r.get_client = AsyncMock(return_value=(client, "gpt-5.6-luna"))
    r.record_success = MagicMock()
    r.record_failure = MagicMock()
    return r


llm_router.get_router = _sahte_router


from app.services import gorev as _gorev_mod  # noqa: E402
_gercek_gorsel = _gorev_mod._gorsel_kontrol


async def _sahte_gorsel(kok, client, router, model):
    """`site` kipinde görsel denetim sahte LLM'den metin bekler (MagicMock → TypeError) — atla."""
    if not AYAR.get("site"):
        return await _gercek_gorsel(kok, client, router, model)
    return {"durum": "atlandi", "neden": "test sunucusu", "ciddi": [], "kucuk": []}


_gorev_mod._gorsel_kontrol = _sahte_gorsel


def uygulama(port: int, dis_origin: list[str] | None = None) -> FastAPI:
    # Origin kapısı TAM eşleşme ister — portuyla (yalnız bu süreçte).
    wsmod.ALLOWED_ORIGINS = list(wsmod.ALLOWED_ORIGINS) + [f"http://127.0.0.1:{port}"]
    _cfg.ALLOWED_ORIGINS = list(_cfg.ALLOWED_ORIGINS) + [f"http://127.0.0.1:{port}"]
    if dis_origin:
        _gercek = gorev_api.dis_originler
        gorev_api.dis_originler = lambda: _gercek() + list(dis_origin)
    get_gorev_servisi().bildir = lambda baslik, govde: BILDIRIMLER.append(
        {"baslik": baslik, "govde": govde})
    app = FastAPI()
    app.include_router(wsmod.router)
    app.include_router(gorev_api.router)

    @app.post("/test/baslat")
    async def baslat(request: Request):
        g = await request.json()
        AYAR["adimlar"] = int(g.get("adimlar", 1000))
        AYAR["gecikme"] = float(g.get("gecikme", 0.5))
        AYAR["site"] = bool(g.get("site"))
        _sayac["n"] = 0
        try:
            with yerel_baglam():
                d = await get_gorev_servisi().baslat(g.get("tur", "site"), g["ad"], "Luna için site")
        except GorevHatasi as e:
            return JSONResponse({"hata": str(e)}, status_code=409)
        return {"id": d["id"]}

    @app.post("/test/oneri")
    async def oneri(request: Request):
        """Harness H4: öneri motorunun yazdığı kaydın aynısı (kaynak ≠ kullanici) — iş başlatmaz."""
        from app.services.gorev_kuyrugu import get_gorev_kuyrugu
        g = await request.json()
        try:
            with yerel_baglam():
                k = get_gorev_kuyrugu().oner(g.get("tur", "site"), g["ad"], g.get("istek", "Luna için site"),
                                             gerekce=g.get("gerekce", "Plan'daki Yuki listesinde bekliyor"),
                                             kaynak=g.get("kaynak", "plan"), kaynak_ref=g.get("ref"))
        except GorevHatasi as e:
            return JSONResponse({"hata": str(e)}, status_code=409)
        return {"id": k["id"]}

    @app.post("/test/oneri_yarim")
    async def oneri_yarim(request: Request):
        from app.services.gorev_kuyrugu import get_gorev_kuyrugu
        g = await request.json()
        tur, _, ad = g["gid"].partition("/")
        with yerel_baglam():
            k = get_gorev_kuyrugu().oner(tur, ad, f"{g['gid']} görevini sürdür",
                                         gerekce="yarım kaldı (gece) — devam edeyim mi?",
                                         kaynak="yarim", kaynak_ref=f"gorev:{g['gid']}", oncelik=1,
                                         devam_gid=g["gid"])
        return {"id": k["id"]}

    @app.get("/test/kuyruk")
    async def kuyruk_durum():
        from app.services.gorev_kuyrugu import get_gorev_kuyrugu
        return {"kayitlar": get_gorev_kuyrugu().liste()}

    @app.post("/test/llm")
    async def llm_ayar(request: Request):
        g = await request.json()
        AYAR["adimlar"] = int(g.get("adimlar", 1000))
        AYAR["gecikme"] = float(g.get("gecikme", 0.5))
        _sayac["n"] = 0
        return AYAR

    @app.get("/test/durum")
    async def durum():
        s = get_gorev_servisi()
        return {"pid": os.getpid(),   # test, hazır yoklamasında KENDİ sürecini tanır (port yarışı)
                "llm_cagri": _sayac["n"], "gorevler": s.liste(),
                "bildirimler": BILDIRIMLER,
                # Harness H1: bu süreçte gerçekten koşan asyncio görevi sayısı
                "kosan": s._kosan_sayisi()}

    @app.get("/")
    async def kok():
        return RedirectResponse("/ui/index.html")

    @app.api_route("/api/{yol:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def api_bos(yol: str):
        return JSONResponse({})

    app.mount("/ui", StaticFiles(directory=str(BACKEND.parent / "frontend"), html=True), name="ui")
    return app


if __name__ == "__main__":
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8097)
    ap.add_argument("--onay-suresi", type=float, default=None)
    ap.add_argument("--onay-kipi", default=None)
    ap.add_argument("--dis-origin", action="append", default=[])
    a = ap.parse_args()
    if a.port == 8001:
        sys.exit("8001 Yuki'nin portu — başka port seç")
    if a.onay_suresi is not None:
        gorev_mod.ONAY_SURESI = a.onay_suresi
    if a.onay_kipi is not None:
        os.environ["YUKI_ATOLYE_DIS_ONAY"] = a.onay_kipi
    uvicorn.run(uygulama(a.port, a.dis_origin), host="127.0.0.1", port=a.port, log_level="warning")

"""Restart ölçümü için sahte yürütücü (Faz 0b, kabul ⑥) — test_gorev_restart.py çağırır.

Ayrı SÜREÇTE görev servisi koşar; LLM sahte, atölye kökü `YUKI_ATOLYE_KOK`.
gerçek veri dizinine, gerçek LLM'e dokunmaz.

  python tests/gorev_sahte_yurutucu.py baslat   # sonsuz yazan görev — dışarıdan kill -9 edilir
  python tests/gorev_sahte_yurutucu.py kurtar   # yeni süreç: servis kurulur, 1,5 sn izlenir
  python tests/gorev_sahte_yurutucu.py devam    # yeni süreç: onaylı DEVAM, bitene kadar
Son satır JSON sonuç.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.gorev import GorevServisi  # noqa: E402
from app.services.atolye.baglam import yerel_baglam  # noqa: E402
from tests.atolye_yardimci import _arac_akisi, _icerik_akisi  # noqa: E402


def _servis() -> GorevServisi:
    # Faz 1 bitiş doğrulaması bu yürütücünün konusu değil (⑥ restart) — site türünde kapalı.
    import dataclasses
    from app.services.atolye.turler import TURLER
    return GorevServisi(KOK, turler={**TURLER, "site": dataclasses.replace(
        TURLER["site"], dogrulayici=False)})

GID = "site/restart"
KOK = Path(os.environ["YUKI_ATOLYE_KOK"])


def _router(create):
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=create)
    r = MagicMock()
    r.get_client = AsyncMock(return_value=(client, "gpt-5.6-luna"))
    return r, client


async def baslat():
    sayac = {"n": 0}

    async def _create(**kw):
        await asyncio.sleep(0.25)
        sayac["n"] += 1
        return _arac_akisi([(f"c{sayac['n']}", "alan_yaz",
                             {"yol": f"once-{sayac['n']}.txt", "icerik": "x"})])

    router, _ = _router(_create)
    servis = _servis()
    with patch("app.services.llm_router.get_router", return_value=router), yerel_baglam():
        await servis.baslat("site", "restart", "Luna için site")
        print("BASLADI", flush=True)
        await servis.bekle(GID)          # asla bitmez (60 adım × 0,25 sn) — kill -9 bekler


async def kurtar():
    cagri = []

    async def _create(**kw):
        cagri.append(1)
        return _icerik_akisi("KENDİLİĞİNDEN KOŞTU")

    router, _ = _router(_create)
    with patch("app.services.llm_router.get_router", return_value=router):
        servis = _servis()
        await asyncio.sleep(1.5)
        d = servis.durum(GID)
    return {"durum": d["durum"], "neden": d["neden"], "adim": d["adim"],
            "llm_cagri": len(cagri), "kosan": len(servis._kosan)}


async def devam():
    gelen = []
    yanitlar = [_arac_akisi([("d1", "alan_yaz", {"yol": "sonra-1.txt", "icerik": "y"})]),
                _arac_akisi([("d2", "alan_yaz", {"yol": "sonra-2.txt", "icerik": "y"})]),
                _icerik_akisi("site bitti")]

    async def _create(**kw):
        gelen.append(json.loads(json.dumps(kw["messages"])))
        return yanitlar.pop(0)

    router, _ = _router(_create)
    with patch("app.services.llm_router.get_router", return_value=router), yerel_baglam():
        servis = _servis()
        once = servis.durum(GID)
        kayitli = json.loads((KOK / "site" / "restart" / ".gorev" / "mesajlar.json").read_text())
        await servis.devam(GID, onay=True)
        d = await servis.bekle(GID, 10)
    return {"once_durum": once["durum"], "once_adim": once["adim"], "durum": d["durum"],
            "adim": d["adim"], "ilk_mesaj_kayitla_ayni": gelen[0] == kayitli,
            "kayitli_mesaj": len(kayitli),
            "devam_sayisi": d["devam_sayisi"]}


if __name__ == "__main__":
    kip = sys.argv[1]
    sonuc = asyncio.run({"baslat": baslat, "kurtar": kurtar, "devam": devam}[kip]())
    print(json.dumps(sonuc, ensure_ascii=False), flush=True)

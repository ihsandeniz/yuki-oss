"""Kamera görüşü — selam ve mola için söylenecek cümleyi seç.

Sunucu ses ÜRETMEZ ve kimseye göndermez: cümle yalnız kamerayı açan istemcinin `/ws/gorus`
cevabına (`soyle`) konur. Kamera yalnız bu bilgisayardan açılabildiği için cümle masa başındaki
kişiye gider; ön yüz (frontend/js/gorus.js) onu Yuki'nin sesiyle çalar.

Rahatsız etmeme kapıları (asıl tavan `gorus_varlik`'te, bu ikinci katman):
  · selam ≤ 1 / `SELAM_ARALIK_SN`, mola ≤ 1 / `MOLA_SN` (süreç geneli)
  · selam yalnız tanınan bir adla (yabancıya "hoş geldin" denmez)
  · `GORUS_SES=0` yalnız sesi kapatır, görüş açık kalır
"""
from __future__ import annotations

import os
import re
import time
from typing import Callable

from app.services.gorus_varlik import MOLA_SN, SELAM_ARALIK_SN

MOLA_CUMLESI = "Elli dakikadır oturuyorsun. Kısa bir mola iyi gelir; biraz kalkıp gerinsene."


def ses_acik() -> bool:
    return os.getenv("GORUS_SES", "1").strip().lower() not in ("0", "false", "no", "off", "kapali")


def _ad_temizle(ad: str) -> str:
    ad = re.sub(r"[^\w\s'-]", "", str(ad))
    return re.sub(r"\s+", " ", ad).strip()[:40].strip()


class GorusSeslendirici:
    def __init__(self, saat: Callable[[], float] = time.monotonic) -> None:
        self._saat = saat
        self._son: dict[str, float] = {}
        self.sayac = {"soylendi": 0, "tavan": 0, "adsiz": 0, "kapali": 0}

    def cumle(self, olay_veri: dict) -> str | None:
        olay = olay_veri.get("olay")
        if olay not in ("selam", "mola"):
            return None
        if not ses_acik():
            self.sayac["kapali"] += 1
            return None
        if olay == "selam":
            ad = _ad_temizle(olay_veri.get("ad") or "")
            if not ad:
                self.sayac["adsiz"] += 1
                return None
            metin = f"Tekrar hoş geldin {ad}."
        else:
            metin = MOLA_CUMLESI
        t = self._saat()
        aralik = SELAM_ARALIK_SN if olay == "selam" else MOLA_SN
        son = self._son.get(olay)
        if son is not None and t - son < aralik:
            self.sayac["tavan"] += 1
            return None
        self._son[olay] = t
        self.sayac["soylendi"] += 1
        return metin

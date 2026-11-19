#!/usr/bin/env python3
"""Masaüstü Yuki UZANMAZ: varsayılan `UZAN_ACIK = False`.

Ölçer: çubuk ne kendiliğinden (dar) ne bırakınca (geniş) aday olur · host `gir("uzan")`'ı geri çevirir · çubuğun
üstüne bırakılan Yuki poza girmez, balon da çıkmaz · oturuş aynen çalışır. Mekanizmanın kendisi (açıkken) hâlâ
`test_etkilesim.py`'de sınanır. Koş: /usr/bin/python3 masaustu/tests/test_uzan_kapali.py
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import etkilesim as E  # noqa: E402

gecti = kaldi = 0


def kontrol(ad, kosul, ayrinti=""):
    global gecti, kaldi
    if kosul:
        gecti += 1
        print(f"  ✓ {ad}")
    else:
        kaldi += 1
        print(f"  ✗ {ad} {ayrinti}")


PANEL, CUBUK = (2800, 355, 268, 476), (2050, 985, 650, 48)
EKRAN = {"panel": PANEL, "cubuk": CUBUK, "paneller": ()}
yuki = lambda x, y=1080 - 486: (x, y, 243, 486)  # noqa: E731

print("— varsayılan")
kontrol("UZAN_ACIK varsayılan kapalı", E.UZAN_ACIK is False)

print("— aday seçimi")
sag_uc = yuki(2050 + 650 + 10)                                  # eskiden dar 'uzan' tutan yer (çubuğun sağ ucu)
kontrol("dar: çubuğun sağ ucunda → aday yok", E.capa_sec(sag_uc, EKRAN) == [], E.capa_sec(sag_uc, EKRAN))
kontrol("yakin_capa: çubuk yanında → None", E.yakin_capa(sag_uc, EKRAN) is None)
orta = (2050 + 300 - 121, 985 - 486 + 40, 243, 486)             # çubuğun ortasına bırakılmış
kontrol("geniş: çubuğa bırakınca 'uzan' adayı yok",
        all(ad != "uzan" for ad, _k in E.capa_sec(orta, EKRAN, genis=True)), E.capa_sec(orta, EKRAN, genis=True))
onunde = yuki(2800 + 134 - 121, 355 - round(0.52 * 486))       # PANEL'in önünde
kontrol("oturuş bozulmadı: PANEL'in önünde → otur", E.capa_sec(onunde, EKRAN) == [("otur", PANEL)])
kontrol("oturuş bozulmadı (geniş)", E.capa_sec(onunde, EKRAN, genis=True)[:1] == [("otur", PANEL)])


class Gov:
    sol, alt, w, h = 2229, 0, 243, 486
    gizli = uyku = False
    _bas = None

    def __init__(self):
        self.js, self.boy = [], []

    def _geo(self):
        return (1440, 0, 1920, 1080)

    def _js(self, kod, geri=None):
        self.js.append(kod)
        if geri:
            geri(None)

    def _marj_uygula(self):
        pass

    def boyut_uygula(self):
        self.boy.append((self.w, self.h))

    def _girdi_bolgesi(self):
        pass

    def _ilk_bolge(self):
        return [(0, 0, self.w, self.h)]


print("— host")
g, LOG = Gov(), []
h = E.EtkilesimHost(g, saat=lambda: 1000.0, pencere=lambda k: {}, rnd=random.Random(1),
                    zamanla=lambda ms, f: None, log=LOG.append)
h.kadraj_geldi({"otur": {"ad": "otur", "w": 243, "h": 421, "temas": [120, 277], "govde": [78, 165]},
                "uzan": {"ad": "uzan", "w": 493, "h": 178, "temas": [216, 163], "govde": [15, 479]}})
h.gir("uzan", EKRAN)
kontrol("gir('uzan') geri çevrilir: poz yok, sayfaya komut yok", h.poz is None and g.js == [] and g.boy == [], (h.poz, g.js))
h.ekran = lambda: EKRAN
h._ayakta_kutu = lambda: orta
kontrol("çubuğa bırakınca yapışmaz", h.yapis() is False and h.poz is None, h.poz)
kontrol("çubuğa bırakınca balon/neden yok", getattr(h, "son_neden", None) in (None, "") and g.js == [], (h.son_neden, g.js))

print(f"\n{gecti}/{gecti + kaldi} geçti")
sys.exit(1 if kaldi else 0)

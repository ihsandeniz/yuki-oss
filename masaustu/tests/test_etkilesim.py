#!/usr/bin/env python3
"""Arayüzle etkileşim: çapa → ekran → poz yeri → ne sıklıkla; host bağı sahte gövdeyle.

Ekrana bir şey AÇILMAZ, pencere kaynağına ve canlı backend'e bağlanılmaz: pencere kaynağı yanıtları sahte, saat sahte, sayfa
çağrıları (`_js`) kaydedilir. Koordinatlar örnek kurulumdan: iki monitör (1440,0 1920×1080), ana pencere
yuki penceresi at (1450,55) boy 1900×1015, masaüstü Yuki 243×486.
Kullanım: python3 tests/test_etkilesim.py
"""
import json
import random
import types
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
import etkilesim as E  # noqa: E402
import baglanti  # noqa: E402

E.UZAN_ACIK = True   # uzanma MEKANİZMASI burada sınanır; varsayılanın kapalı olduğu tests/test_uzan_kapali.py'de

gecti = kaldi = 0


def kontrol(ad, kosul, ayrinti=""):
    global gecti, kaldi
    if kosul:
        gecti += 1
        print("  ✓", ad)
    else:
        kaldi += 1
        print("  ✗", ad, ayrinti)


MON = (1440, 0, 1920, 1080)
IST = {"class": "yuki", "title": "YUKI // AI COMPANION", "at": [1450, 55], "size": [1900, 1015],
       "workspace": {"id": -92, "name": "special:yuki"}, "monitor": 1, "mapped": True, "hidden": False}
SITE = dict(IST, title="site", size=[800, 600], at=[1500, 100])
MONS = [{"id": 1, "activeWorkspace": {"id": 2}, "specialWorkspace": {"id": -92, "name": "special:yuki"}},
        {"id": 0, "activeWorkspace": {"id": 8}, "specialWorkspace": {"id": 0, "name": ""}}]
# görüntüdeki gibi: PANEL sağda yüzen kutu, giriş hapı altta ortada
CAPA = {"type": "masaustu_capa", "vw": 1900, "vh": 1015, "panel": [1350, 300, 268, 476], "cubuk": [600, 930, 650, 48]}
OTUR_K = {"ad": "otur", "w": 243, "h": 421, "temas": [120, 277], "govde": [78, 165]}
UZAN_K = {"ad": "uzan", "w": 493, "h": 178, "temas": [216, 163], "govde": [15, 479]}

print("— çapa iletisi")
c = E.capa_dogrula(CAPA)
kontrol("geçerli ileti kabul", c and c["panel"] == (1350.0, 300.0, 268.0, 476.0) and c["vw"] == 1900.0, c)
kontrol("tip yanlışsa red", E.capa_dogrula(dict(CAPA, type="text")) is None)
kontrol("görünüm bozuksa red", E.capa_dogrula(dict(CAPA, vw="x")) is None and E.capa_dogrula(dict(CAPA, vh=10)) is None)
kontrol("bozuk kutu → o çapa None", E.capa_dogrula(dict(CAPA, panel=[1, 2, 3]))["panel"] is None
        and E.capa_dogrula(dict(CAPA, cubuk=[0, 0, float("nan"), 40]))["cubuk"] is None)
kontrol("çok küçük kutu (gizli öğe) → None", E.capa_dogrula(dict(CAPA, panel=[0, 0, 10, 4]))["panel"] is None)
cv = baglanti.Cevirici()
kontrol("çevirici: masaustu_capa → ('capa', dict)", cv.cevir(CAPA) == [("capa", c)], cv.cevir(CAPA))
kontrol("çevirici: bozuk çapa → komut yok", cv.cevir({"type": "masaustu_capa", "vw": None}) == [])

print("— pencere kaynağı")
kontrol("ana pencere: site penceresi değil en büyük yuki", E.istemci_bul([SITE, {"class": "kitty"}, IST]) is IST)
kontrol("gizli/eşlenmemiş alınmaz", E.istemci_bul([dict(IST, hidden=True), dict(IST, mapped=False)]) is None)
kontrol("special:yuki açıkken görünür", E.gorunur_mu(IST, MONS))
kapali = [dict(MONS[0], specialWorkspace={"id": 0, "name": ""}), MONS[1]]
kontrol("special:yuki kapalıyken görünmez", not E.gorunur_mu(IST, kapali))
kontrol("normal alanda: aktif alan eşleşirse görünür",
        E.gorunur_mu(dict(IST, workspace={"id": 2}), kapali) and not E.gorunur_mu(dict(IST, workspace={"id": 3}), kapali))

print("— CSS → ekran")
e = E.capa_ekran(c, IST)
kontrol("ölçek 1: at + css", e["panel"] == (2800, 355, 268, 476) and e["cubuk"] == (2050, 985, 650, 48), e)
e2 = E.capa_ekran(dict(c, vw=950, vh=507.5), IST)
kontrol("zoom 2× (CSS px yarıya iner): ekran kutusu iki katı", e2["panel"][2] == 536 and e2["panel"][0] == 1450 + 2700, e2)
kontrol("çapa Yuki'nin monitöründe", E.capa_monitorde(e, MON) and not E.capa_monitorde(e, (0, 0, 1440, 900)))

print("— yakınlık (ayaktaki Yuki 243×486, alt kenar ekranın altında)")
yuki = lambda x, y=1080 - 486: (x, y, 243, 486)  # noqa: E731
# görüntü 1: Yuki PANEL'in önüne sürüklenmiş, PANEL'in üstü bedeninin ≈%52'sinde (yere basmıyor)
YUKARI = 355 - round(0.52 * 486)
kontrol("PANEL'in önünde (görüntü 1) → otur", E.yakin_capa(yuki(2800 + 134 - 121, YUKARI), e) == "otur")
kontrol("çubuğun sağ ucunda (görüntü 2) → uzan", E.yakin_capa(yuki(2050 + 650 + 10), e) == "uzan")
kontrol("uzakta → None", E.yakin_capa(yuki(1500), e) is None)
kontrol("çapa yoksa → None", E.yakin_capa(yuki(2800), None) is None)
kontrol("PANEL Yuki'nin başından yukarıdaysa oturmaz",
        E.yakin_capa(yuki(2813), {"panel": (2800, 400, 268, 476), "cubuk": None}) is None)

print("— poz yeri")
yer, neden = E.poz_yeri("otur", OTUR_K, e, MON, 2934)
gx, gy = MON[0] + yer[0], MON[1] + MON[3] - yer[1] - OTUR_K["h"]
kontrol("otur: temas noktası PANEL'in üst kenarında", neden == "tamam" and gy + OTUR_K["temas"][1] == 355, (yer, neden))
kontrol("otur: kalça PANEL'in içinde", 2800 + 0.18 * 268 <= gx + 120 <= 2800 + 0.82 * 268, gx)
yer2, _ = E.poz_yeri("otur", OTUR_K, e, MON, 9999)
kontrol("otur: oturma noktası panelin %62'si, Yuki nerede olursa olsun",
        MON[0] + yer2[0] + 120 == round(2800 + 0.62 * 268) and yer2 == E.poz_yeri("otur", OTUR_K, e, MON, 0)[0], yer2)
yer, neden = E.poz_yeri("uzan", UZAN_K, e, MON, 2700)
gx, gy = MON[0] + yer[0], MON[1] + MON[3] - yer[1] - UZAN_K["h"]
kontrol("uzan: alt çizgi çubuğun üstünde", neden == "tamam" and gy + UZAN_K["temas"][1] == 985, (yer, neden))
kontrol("uzan: baştan ayağa beden çubuğun içinde (6 px pay)",
        gx + UZAN_K["govde"][0] >= 2050 + 6 and gx + UZAN_K["govde"][1] <= 2050 + 650 - 6, (gx,))
kontrol("uzan: çubuk kısaysa vazgeçer (cubuk_kisa)",
        E.poz_yeri("uzan", UZAN_K, {"cubuk": (2050, 985, 400, 48)}, MON, 2300) == (None, "cubuk_kisa"))
# görüntüdeki/sahnedeki gibi: PANEL sağda aşağı sürüklenmiş, çubuğun sağ ucunu dikeyde örtüyor (2. göz turu bulgusu)
ek = {"panel": (2660, 455, 268, 476), "cubuk": (2050, 985, 650, 48)}   # sahnedeki gibi: ucundan 40 px önce
yer, neden = E.poz_yeri("uzan", UZAN_K, ek, MON, 2700)
gx = MON[0] + yer[0] if yer else None
kontrol("uzan: PANEL çubuğu örtüyorsa beden PANEL'e girmez (ayaklar PANEL'in solunda)",
        yer and gx + UZAN_K["govde"][1] <= 2660 - 4 and gx + UZAN_K["govde"][0] >= 2050 + 6, (yer, neden, gx))
kontrol("uzan: PANEL çubuğun tamamını örtüyorsa vazgeçer (panel_cakisir)",
        E.poz_yeri("uzan", UZAN_K, {"panel": (2000, 455, 760, 600), "cubuk": (2050, 985, 650, 48)}, MON, 2700)
        == (None, "panel_cakisir"))
kontrol("uzan: PANEL çubuğun üstünde değilse (dikeyde ayrı) kısıt yok",
        E.poz_yeri("uzan", UZAN_K, {"panel": (2410, 100, 268, 300), "cubuk": (2050, 985, 650, 48)}, MON, 2700)[1] == "tamam")
kontrol("üstte yer yoksa vazgeçer (ekran_disi)",
        E.poz_yeri("otur", OTUR_K, {"panel": (2800, 100, 268, 476)}, MON, 2934) == (None, "ekran_disi"))
kontrol("çapa yoksa vazgeçer", E.poz_yeri("otur", OTUR_K, {"panel": None}, MON, 0) == (None, "panel_yok"))

print("— ne sıklıkla (Planlayici, tohumlu)")
p = E.Planlayici(random.Random(7))
olay = []
for t in range(0, 400):
    olay += [(t,) + x for x in p.adim(float(t), {"poz": None, "yakin": None})]
selamlar = [o[0] for o in olay if o[1] == "selam"]
aralar = [b - a for a, b in zip(selamlar, selamlar[1:])]
kontrol("açılışta 20–50 sn içinde 'merhaba' selamı", selamlar and 20 <= selamlar[0] <= 51, selamlar[:2])
kontrol("400 sn'de 4-9 kendi selamı", 4 <= len(selamlar) <= 9, selamlar)
kontrol("uyanıkken selam aralığı 45–110 sn", aralar and all(45 <= a <= 111 for a in aralar), aralar)
p = E.Planlayici(random.Random(1))
kontrol("gizliyken selam yok", not [x for t in range(900) for x in p.adim(float(t), {"gizli": True})])
p = E.Planlayici(random.Random(1))
uy = [t for t in range(0, 1500) for x in p.adim(float(t), {"uyku": True}) if x == ("selam",)]
ua = [b - a for a, b in zip(uy, uy[1:])]
kontrol("uykudayken 3–6 dk'da bir uyanıp el sallar (1500 sn'de 4-8)", 4 <= len(uy) <= 8 and all(180 <= a <= 361 for a in ua)
        and 180 <= uy[0] <= 361, (uy, ua))
p = E.Planlayici(random.Random(1))
kontrol("uykuda bile sürüklerken / dokunduktan hemen sonra selam yok",
        not [x for t in range(400) for x in p.adim(float(t), {"uyku": True, "surukle": True})])
p = E.Planlayici(random.Random(1))
p.sonraki_selam, p.sonraki_uyku_selam = 1e9, 0.0
kontrol("uzanırken uykuda da el sallamaz", p.adim(10.0, {"uyku": True, "poz": "uzan"}) == [])
p = E.Planlayici(random.Random(2))
son = []
for t in range(300):
    if t % 5 == 0:
        p.etkilesim(float(t))
    son += p.adim(float(t), {})
kontrol("sürekli etkileşimde (5 sn'de bir tık) kendiliğinden bir şey yapmaz", son == [], son)
p = E.Planlayici(random.Random(3))
ilk = None
for t in range(0, 60):
    r = p.adim(float(t), {"yakin": "otur"})
    if ("poz", "otur") in r:
        ilk = t
        break
kontrol("çapanın yanında 3–7 sn sonra poza girer", ilk is not None and 3 <= ilk <= 7, ilk)
p = E.Planlayici(random.Random(3))
p.birakildi(100.0)
r = [(t, x) for t in (100, 101, 102) for x in p.adim(float(t), {"yakin": "uzan"})]
kontrol("sürükleyip bırakınca ≈1 sn içinde poza girer", r and r[0][1] == ("poz", "uzan") and r[0][0] <= 101, r)
p = E.Planlayici(random.Random(4))
p.poz_bitis = 50.0
kontrol("çapa geçersizleşince kalkar", p.adim(10.0, {"poz": "otur", "gecerli": False}) == [("kalk",)])
p = E.Planlayici(random.Random(4))
p.poz_bitis = 50.0
kontrol("sürüklenince kalkar", p.adim(10.0, {"poz": "otur", "surukle": True}) == [("kalk",)])
p = E.Planlayici(random.Random(4))
p.poz_bitis = 50.0
kontrol("süre dolunca kalkar, uykudaysa beklemeye devam",
        p.adim(51.0, {"poz": "otur", "uyku": True}) == [] and p.adim(52.0, {"poz": "otur"}) == [("kalk",)])
r = [x for t in range(53, 90) for x in p.adim(float(t), {"yakin": "otur"})]
kontrol("kalktıktan sonra en az 40 sn aynı poza dönmez", ("poz", "otur") not in r, r)
p = E.Planlayici(random.Random(5))
p.sonraki_selam = 0.0
kontrol("uzanırken el sallamaz (destek kolu)", p.adim(100.0, {"poz": "uzan"}) == [])


print("— host bağı (sahte gövde)")


class Gov:
    def __init__(self):
        self.sol, self.alt, self.w, self.h = 1300, 0, 243, 486
        self.gizli = self.uyku = False
        self._bas = None
        self.js, self.marj, self.boy, self.bolge = [], [], [], None
        self.cevap = {}

    def _geo(self):
        return MON

    def _js(self, kod, geri=None):
        self.js.append(kod)
        if geri:
            for k, v in self.cevap.items():
                if k in kod:
                    return geri(v)
            geri(None)

    def _marj_uygula(self):
        self.marj.append((self.sol, self.alt))

    def boyut_uygula(self):
        self.boy.append((self.w, self.h))

    def _girdi_bolgesi(self):
        pass

    def _ilk_bolge(self):
        return [(0, 0, self.w, self.h)]


class Saat:
    t = 1000.0

    def __call__(self):
        return self.t


LOG = []


def kur(capa=CAPA, istemciler=None, mons=None):
    g, s, bekleyen = Gov(), Saat(), []
    hy = {"clients": istemciler if istemciler is not None else [IST], "monitors": mons or MONS}
    sayac = {"n": 0}

    def pencere(k):
        sayac["n"] += 1
        return hy[k]
    h = E.EtkilesimHost(g, saat=s, pencere=pencere, rnd=random.Random(11), zamanla=lambda ms, f: bekleyen.append((ms, f)),
                        log=LOG.append)
    if capa:
        h.capa_geldi(E.capa_dogrula(capa))
    h.kadraj_geldi({"otur": OTUR_K, "uzan": UZAN_K})          # sayfanın durum POST'undan
    return g, s, h, bekleyen, sayac


g, s, h, bek, say = kur(capa=None)
for _ in range(30):
    s.t += 1
    h.tur()
kontrol("çapa hiç gelmezse pencere kaynağı okunmaz (0 IPC)", say["n"] == 0, say)
s.t += 1
h.capa_geldi(E.capa_dogrula(CAPA))
s.t += E.CAPA_TAZE_SN + 1
kontrol("bayat çapa (>12 sn) → ekran yok", h.ekran() is None)

# PANEL'in önünde duran Yuki: sol marj = (2813 - 1440)
g, s, h, bek, say = kur()
g.sol, g.alt = 2813 - 1440, 1080 - YUKARI - 486
g.cevap = {"yukiPozHazirla": OTUR_K}
oldu = None
for i in range(40):
    s.t += 1
    h.capa_geldi(E.capa_dogrula(CAPA))     # ön yüz tazeliyor
    h.tur()
    if h.poz and h.poz["durum"] == "aktif":
        oldu = i
        break
kontrol("host: yakınken kendiliğinden oturur", oldu is not None and any("yukiPozBasla(\"otur\")" in j for j in g.js), g.js[-3:])
kontrol("host: pencere poz boyuna geldi", g.boy[-1:] == [(243, 421)], g.boy)
kontrol("host: temas PANEL kenarında (marj)",
        MON[3] - g.alt - OTUR_K["h"] + OTUR_K["temas"][1] == 355, (g.sol, g.alt))
ayakta = h.poz["ayakta"]
kontrol("host: ayaktaki yer saklandı, kayıt onu yazar", ayakta[:2] == (1373, 1080 - YUKARI - 486) and h.ayakta_marj() == ayakta[:2])
# PANEL 20 px sağa sürüklendi → izler
s.t += 1
h.capa_geldi(E.capa_dogrula(dict(CAPA, panel=[1370, 300, 268, 476])))
eski = g.sol
h.tur()
kontrol("host: PANEL kayınca Yuki onu izler (+20 px)", g.sol == eski + 20, (eski, g.sol))
# pencere gizlendi (special:yuki kapandı) → kalkar
g2_mons = [dict(MONS[0], specialWorkspace={"id": 0, "name": ""}), MONS[1]]
h.pencere = lambda k: {"clients": [IST], "monitors": g2_mons}[k]
s.t += 1
h.tur()
kontrol("host: ana pencere gizlenince kalkar (yukiPozBitir)", any("yukiPozBitir" in j for j in g.js[-2:]) and h.poz["durum"] == "kalkiyor")
kontrol("host: kalkış bitmeden ayakta boyuna dönmez", g.boy[-1] == (243, 421) and bek and bek[-1][0] == E.KALK_MS)
bek[-1][1]()
kontrol("host: 0,65 sn sonra ayaktaki boy + kadraj", g.boy[-1] == (243, 486)
        and "yukiBoyut(243, 486)" in g.js[-1] and h.poz is None, (g.boy[-1], g.sol, g.alt, g.js[-1]))
kontrol("host: kalkınca eski (ayaktaki) yerinde", (g.sol, g.alt) == ayakta[:2], (g.sol, g.alt))

# uzan: çubuk kısa → vazgeçer, pencere değişmez
g, s, h, bek, say = kur(capa=dict(CAPA, cubuk=[1700, 930, 380, 48]))
g.sol = 1700 + 1450 - 1440 + 380 - 60
g.cevap = {"yukiPozHazirla": UZAN_K}
for _ in range(40):
    s.t += 1
    h.capa_geldi(E.capa_dogrula(dict(CAPA, cubuk=[1700, 930, 380, 48])))
    h.tur()
kontrol("host: çubuk Yuki'yi taşımıyorsa uzanmaz (cubuk_kisa), pencere aynı",
        h.son_neden == "cubuk_kisa" and g.boy == [] and h.poz is None, (h.son_neden, g.boy))

# sürükleme başında kalkar
g, s, h, bek, say = kur()
g.sol, g.alt = 2813 - 1440, 1080 - YUKARI - 486
g.cevap = {"yukiPozHazirla": OTUR_K}
for _ in range(40):
    s.t += 1
    h.capa_geldi(E.capa_dogrula(CAPA))
    h.tur()
    if h.poz and h.poz["durum"] == "aktif":
        break
h.surukle_basladi()
kontrol("host: sürüklemeye başlayınca kalkar", h.poz and h.poz["durum"] == "kalkiyor")
h.kalk(hemen=True)
kontrol("host: kalkış sürerken ikinci kalk yeni zamanlayıcı kurmaz", len(bek) == 1, bek)

# kendi selamı: sayfaya yalnız olayda gider
g, s, h, bek, say = kur(capa=None)
for _ in range(400):
    s.t += 1
    h.tur()
sel = [j for j in g.js if "yukiKendiSelam" in j]
kontrol("host: 400 sn'de JS çağrısı yalnız selam anlarında (her turda değil)", 4 <= len(g.js) == len(sel) <= 9, len(g.js))
kontrol("log: her selam bir satır, her turda satır yok", len([l for l in LOG if l == "[etkilesim] selam"]) >= len(sel)
        and len(LOG) < 100, len(LOG))

g, s, h, bek, say = kur()
h.kadraj = {}
h.kadraj_geldi({"otur": {"w": "x"}, "uzan": dict(UZAN_K, temas=[1]), "baska": OTUR_K})
kontrol("host: bozuk/bilinmeyen kadraj alınmaz", h.kadraj == {}, h.kadraj)
g.sol, g.alt = 2813 - 1440, 1080 - YUKARI - 486
for _ in range(40):
    s.t += 1
    h.capa_geldi(E.capa_dogrula(CAPA))
    h.tur()
kontrol("host: kadraj gelmeden poza girmez (kadraj_yok), pencere aynı", h.poz is None and g.boy == []
        and h.son_neden == "kadraj_yok", (h.son_neden, g.boy))

kontrol("log: ilk çapa bir kez yazılır (PANEL/çubuk konumuyla)",
        len([l for l in LOG if l.startswith("[etkilesim] çapa geldi panel=")]) >= 1
        and any("cubuk=(600.0, 930.0, 650.0, 48.0)" in l for l in LOG), [l for l in LOG if "çapa" in l][:2])
kontrol("log: poz, vazgeç ve kalk satırları", any(l.startswith("[etkilesim] poz otur marj=") for l in LOG)
        and any(l == "[etkilesim] vazgeç uzan cubuk_kisa" for l in LOG) and "[etkilesim] kalk" in LOG, LOG[-8:])

print("— 2. tur: diğer paneller · bırakınca yapışma · uzanma sağ uçta")
AKIS_CSS = [100, 400, 320, 300]                                   # AKIŞ paneli açık → ekranda (1550, 455, 320, 300)
CAPA2 = dict(CAPA, paneller=[AKIS_CSS])
c2 = E.capa_dogrula(CAPA2)
kontrol("paneller: geçerli kutu alınır", c2["paneller"] == ((100.0, 400.0, 320.0, 300.0),), c2["paneller"])
kontrol("paneller: bozuk kutu atlanır, liste değilse boş",
        E.capa_dogrula(dict(CAPA, paneller=[[1, 2, 3], "x", [0, 0, float("inf"), 9], AKIS_CSS]))["paneller"] == ((100.0, 400.0, 320.0, 300.0),)
        and E.capa_dogrula(dict(CAPA, paneller="abc"))["paneller"] == () and E.capa_dogrula(CAPA)["paneller"] == ())
kontrol("paneller: en çok 12", len(E.capa_dogrula(dict(CAPA, paneller=[[i, 0, 50, 50] for i in range(30)]))["paneller"]) == 12)
e2 = E.capa_ekran(c2, IST)
AKIS = (1550, 455, 320, 300)
kontrol("paneller ekrana çevrilir", e2["paneller"] == (AKIS,), e2)
kontrol("paneller(): önce PANEL, aynı kutu iki kez yok", E.paneller(dict(e2, paneller=(AKIS, e2["panel"]))) == [e2["panel"], AKIS])
kontrol("çapa monitörde: yalnız AKIŞ varsa da", E.capa_monitorde({"panel": None, "cubuk": None, "paneller": (AKIS,)}, MON))
kontrol("izle: aynı boyda kayan kutu bulunur", E.capa_izle(AKIS, [e2["panel"], (1580, 470, 320, 300)]) == (1580, 470, 320, 300))
kontrol("izle: kapandıysa (aynı boyda yok) None", E.capa_izle(AKIS, [e2["panel"]]) is None)
yk = (1710 - 121, 455 - 253, 243, 486)                            # AKIŞ'ın önünde (üstü bedeninin %52'sinde)
kontrol("dar: AKIŞ'ın önünde → otur AKIŞ", E.capa_sec(yk, e2) == [("otur", AKIS)], E.capa_sec(yk, e2))
ust = (1550 - 40 - 121, 455 - 30 - 486, 243, 486)                 # AKIŞ'ın sol kenarından 40 px dışarıda, ayak üstünden 30 px yukarıda
kontrol("dar: kabaca bırakılan yer tutmaz", E.capa_sec(ust, e2) == [])
kontrol("geniş: kabaca bırakılan yer AKIŞ'a yapışır", E.capa_sec(ust, e2, genis=True)[:1] == [("otur", AKIS)],
        E.capa_sec(ust, e2, genis=True))
kontrol("geniş: hiçbir şeye yakın değilse aday yok", E.capa_sec((2400, 0, 243, 486), dict(e2, cubuk=None), genis=True) == [])
alt = (2050 + 300 - 121, 985 - 486 + 40, 243, 486)               # çubuğun ortasına, ayakları çubuğun 40 px içinde
kontrol("geniş: çubuğun ortasına bırakınca uzan (dar tutmaz)", E.capa_sec(alt, e2, genis=True)[:1] == [("uzan", e2["cubuk"])]
        and E.capa_sec(alt, e2) == [], E.capa_sec(alt, e2, genis=True))
yer, neden = E.poz_yeri("otur", OTUR_K, e2, MON, 1700, kutu=AKIS)
kontrol("poz yeri: kutu verilince AKIŞ'ın üst kenarına oturur", neden == "tamam"
        and MON[3] - yer[1] - OTUR_K["h"] + OTUR_K["temas"][1] == 455, (yer, neden))
yer, neden = E.poz_yeri("uzan", UZAN_K, e2, MON, 2700)
kontrol("uzan: baş çubuğun SAĞ ucunda (beden sağ kenarı = çubuk sonu − 6 px)", neden == "tamam"
        and MON[0] + yer[0] + UZAN_K["govde"][1] == 2050 + 650 - 6, (yer, neden))
yer2, _ = E.poz_yeri("uzan", UZAN_K, e2, MON, 2100)
kontrol("uzan: şimdiki yerden bağımsız (hep sağ uç)", yer2 == yer)
ortu = dict(e2, panel=None, paneller=((2560, 600, 200, 400),))     # AKIŞ çubuğun sağ ucunu örtüyor
yer, neden = E.poz_yeri("uzan", UZAN_K, ortu, MON, 2700)
kontrol("uzan: açık paneli de atlar (beden panelin solunda)", neden == "tamam" and MON[0] + yer[0] + UZAN_K["govde"][1] <= 2556,
        (yer, neden))
ortu2 = dict(e2, paneller=((2560, 600, 200, 400),))                 # PANEL çubuktan uzakta, AKIŞ sağ ucu örtüyor
yer, neden = E.poz_yeri("uzan", UZAN_K, ortu2, MON, 2700)
kontrol("uzan: PANEL'den sonraki paneli de atlar", neden == "tamam" and MON[0] + yer[0] + UZAN_K["govde"][1] <= 2556, (yer, neden))
iki = dict(e2, panel=(2040, 600, 200, 400), paneller=((2200, 600, 600, 400),))
kontrol("uzan: iki panel çubuğu kapatıyorsa panel_cakisir", E.poz_yeri("uzan", UZAN_K, iki, MON, 2700) == (None, "panel_cakisir"))

BALON = []
g, s, h, bek, say = kur(capa=CAPA2)
g.kopru = types.SimpleNamespace(balon=types.SimpleNamespace(goster=lambda m, sn: BALON.append(m)))
g.sol, g.alt = ust[0] - MON[0], MON[3] - ust[1] - 486
h.birakildi()
kontrol("bırakınca HEMEN AKIŞ'a oturur (tur beklemeden)", h.poz and h.poz["durum"] == "aktif" and h.poz["kutu"] == AKIS
        and any('yukiPozBasla("otur")' in j for j in g.js), (h.poz, h.kayit))
kontrol("yapışınca temas AKIŞ'ın üstünde", MON[3] - g.alt - OTUR_K["h"] + OTUR_K["temas"][1] == 455, (g.sol, g.alt))
kontrol("log: yapış satırı", any(l.startswith("[etkilesim] yapış otur") for l in LOG), LOG[-3:])
s.t += 1
h.capa_geldi(E.capa_dogrula(dict(CAPA, paneller=[[130, 420, 320, 300]])))   # AKIŞ 30 px sağa, 20 px aşağı sürüklendi
eski = g.sol
h.tur()
kontrol("AKIŞ sürüklenince onunla gider", g.sol == eski + 30 and h.poz["kutu"] == (1580, 475, 320, 300), (eski, g.sol, h.poz.get("kutu")))
s.t += 1
h.capa_geldi(E.capa_dogrula(CAPA))                                # AKIŞ kapandı (PANEL duruyor ama oturduğu panel değil)
h.tur()
kontrol("oturduğu panel kapanınca kalkar (PANEL'e atlamaz)", h.poz and h.poz["durum"] == "kalkiyor", h.poz and h.poz["durum"])
kontrol("yapışınca balon yok", BALON == [])

g, s, h, bek, say = kur(capa=dict(CAPA, panel=None, paneller=[[100, 40, 320, 300]]))   # AKIŞ üst çubuğun hemen altında (y=95)
g.kopru = types.SimpleNamespace(balon=types.SimpleNamespace(goster=lambda m, sn: BALON.append(m)))
g.sol, g.alt = 1589 - MON[0], MON[3] - 486                       # ekranın tepesine bırakıldı, AKIŞ'ın önünde: oturunca baş taşar
h.birakildi()
kontrol("sığmıyorsa yapışmaz, balonla nedenini söyler (ekran_disi)", h.poz is None and len(BALON) == 1
        and BALON[0] == E.YAPISAMADI["ekran_disi"] and "[etkilesim] yapışamadı ekran_disi" in LOG, (BALON, h.kayit, LOG[-2:]))
g, s, h, bek, say = kur(capa=CAPA2)
g.kopru = types.SimpleNamespace(balon=types.SimpleNamespace(goster=lambda m, sn: BALON.append(m)))
g.sol, g.alt = 0, 0                                               # hiçbir şeyin yanında değil
BALON.clear()
h.birakildi()
kontrol("hiçbir şeye yakın bırakılınca: poz yok, balon yok", h.poz is None and BALON == [])

print("— yuki_govde kaynağı (GTK'siz denetim)")
src = (KOK / "yuki_govde.py").read_text()
kontrol("kip tam: etkileşim turu yalnız gerçek kipte (kuru değil)", "GLib.timeout_add(1000, self.etk.tur)" in src
        and src.index("        if not arg.kuru:\n            # sayfa durumu") < src.index("GLib.timeout_add(1000, self.etk.tur)"))
kontrol("kadraj sayfanın durum POST'undan host'a", 'self.etk.kadraj_geldi(d.get("poz_kadraj"))' in src)
esrc = (KOK / "etkilesim.py").read_text()
kontrol("etkileşim host'u sayfadan yanıt beklemez (evaluate_javascript sonucu yok)",
        "_js(" in esrc and not [l for l in esrc.splitlines() if "_js(" in l and "lambda" in l] and ", geri" not in esrc)
kontrol("konum kaydı pozda ayaktaki yeri yazar", "etk.ayakta_marj()" in src)
kontrol("monitör değişince önce ayağa", "self.etk.kalk(hemen=True)" in src)

print(f"\n{gecti}/{gecti + kaldi} geçti")
sys.exit(1 if kaldi else 0)

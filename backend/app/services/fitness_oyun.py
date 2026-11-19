"""Fitnes oyun motoru — XP · seviye · stat · lig (Gölge) · beceri ağacı · unvan · ödül · haftalık özet · olay.

İki katman:
  1. Saf hesap (`durum_hesapla` ve kurallar): girdi düz sözlük, depo/ağ bilmez. Testler bunu sınar.
  2. Depo katmanı (`veri_oku`, `olay_uret`, `durum`, `haftalik_ozet`): `fitness_store` sözlüğünü okur,
     olay günlüğünü tekil anahtarla yazar.

İlke: XP saklanmaz, her okumada kayıtlardan yeniden türetilir. Saklananlar yalnız olay günlüğü
(`olaylar`, tekil `anahtar` → aynı kutlama iki kez çıkmaz) ve kalıcı kazanımlar (`beceriler`,
`unvanlar`): kayıt silinse de kazanılan unvan gitmez, beceri "askıda" görünür.

Set "yapıldı" tek kural: `girildi` damgası var ya da bitişte onaylandı (`completed`). Şablondan gelip
dokunulmamış set — kilosu ne olursa olsun — XP, rekor ya da beceri üretmez.
Süreli hareket: adında "(sn)" geçen harekette `reps` saniyedir; tonaja ve rekora girmez.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from app.services import fitness_store as depo
from app.services.fitnes_metin import t

HESAP_SURUMU = 2
RUTBELER = "EDCBAS"
KATALOG = ("squat", "bench", "deadlift", "ohp", "row")
ESLEME = {
    "squat": "squat", "back squat": "squat", "front squat": "squat", "comelme": "squat",
    "bench": "bench", "bench press": "bench", "gogus pres": "bench",
    "deadlift": "deadlift", "olu kaldirma": "deadlift",
    "ohp": "ohp", "overhead press": "ohp", "askeri pres": "ohp", "omuz pres": "ohp",
    "row": "row", "barbell row": "row", "bent over row": "row", "kurek cekis": "row",
}
KALIBRASYON_GUN = 14
GEC_ESIK_GUN = 2
VARSAYILAN_SET_HEDEFI = 12
OZET_SAATI = time(8, 30)          # Pazartesi haftalık özet bu saatten önce doğmaz
SURUM_KARTI_GOSTER = False
DROP_EN_COK = depo.DROP_EN_COK

_HARF = str.maketrans("çğıöşüâî", "cgiosuai")
_SURELI = re.compile(r"\(\s*sn\s*\)", re.IGNORECASE)


def lig_ad(kod: str) -> str:
    return t(f"lig.{kod}")


# Seviye ödülleri — yalnız görünüm, hesaba girmez. Açık = seviye ≤ ulaşılan en yüksek seviye.
_ODUL_TABLO = (
    (2, "unvan", "uyanan"), (3, "vurgu", "gece_moru"), (4, "cerceve", "ince_gumus"),
    (5, "unvan", "yolcu"), (5, "sigil", "sigil_1"), (7, "vurgu", "buz_mavisi"),
    (10, "unvan", "demir_cirak"), (10, "cerceve", "cift_halka"), (10, "toren", "halka_genisleme"),
    (12, "ray", "cizgili"), (15, "unvan", "gece_talimcisi"), (15, "sigil", "sigil_2"),
    (18, "vurgu", "ay_gumusu"), (20, "unvan", "sessiz_guc"), (20, "cerceve", "isaretli_halka"),
    (20, "toren", "yildiz_tozu"), (25, "unvan", "yuku_tasiyan"), (25, "sigil", "sigil_3"),
    (25, "ray", "takimyildiz"), (30, "unvan", "golgesini_asan"), (30, "cerceve", "altin_cizgi"),
    (35, "vurgu", "gece_yarisi"), (35, "toren", "tutulma_gecisi"), (40, "unvan", "yildiz_doven"),
    (40, "sigil", "sigil_4"), (45, "cerceve", "yorunge"), (50, "unvan", "tutulma_bekcisi"),
    (50, "sigil", "sigil_5"), (50, "toren", "tam_toren"),
)


def oduller_tablosu() -> list[dict]:
    return [{"seviye": sv, "tur": tur, "kod": kod, "ad": t(f"odul.{kod}")} for sv, tur, kod in _ODUL_TABLO]


# Beceri ağacı: (kod, dal, evrim kodu, gizli). Ad ve koşul metinleri fitnes_metin'de.
_BECERI_TABLO = (
    ("agir_yuk", "guc", "dev_gucu", False), ("rekor_avcisi", "guc", "sinir_kirici", False),
    ("hacim_bilgesi", "day", "bitmeyen_nefes", False), ("uzun_soluk", "day", None, False),
    ("demir_tutus", "dis", "celik_irade", False), ("seri_ustasi", "dis", "kirilmaz", False),
    ("kayit_tutucu", "bes", None, False), ("protein_sezgisi", "bes", "metabolik_hakim", False),
    ("golge_yarisi", "golge", "golgesiz", True), ("donus", "golge", None, True),
)

# Unvanlar: kod → (kaynak, koşul). Seviye unvanları ödül tablosundan gelir.
_UNVAN_KOSUL = {
    **{kod: ("seviye", sv) for sv, tur, kod in _ODUL_TABLO if tur == "unvan"},
    "kor_tasiyici": ("lig", "D"), "ay_yuruyuscusu": ("lig", "C"), "hilal_muhafizi": ("lig", "B"),
    "yildiz_okuyucu": ("lig", "A"), "tutulmus": ("lig", "S"),
    "celik_irade": ("evrim", "demir_tutus"), "dev_gucu": ("evrim", "agir_yuk"),
    "sinir_kirici": ("evrim", "rekor_avcisi"), "kirilmaz": ("evrim", "seri_ustasi"),
    "metabolik_hakim": ("evrim", "protein_sezgisi"), "bitmeyen_nefes": ("evrim", "hacim_bilgesi"),
    "golgesiz": ("evrim", "golge_yarisi"), "geri_donen": ("beceri", "donus"),
}


def unvan_ad(kod: str) -> str:
    return t(f"unvan.{kod}")


# Olay türü → varsayılan teslim kanalı ve ekran sırası
TESLIM = {"SEVIYE": "anlik", "REKOR": "anlik", "PR": "anlik", "BECERI": "kart", "EVRIM": "ozet", "LIG": "ozet",
          "HAFTALIK_OZET": "anlik", "UYANIS": "anlik", "GOREV_TAMAM": "kart", "HAFTA_HEDEFI": "kart",
          "GOLGE": "kart", "HATIRLATMA": "anlik", "DONDURMA": "kart", "SURUM": "kart"}
SIRA = {"SEVIYE": 0, "SURUM": 0, "HAFTALIK_OZET": 1, "UYANIS": 2, "REKOR": 3, "PR": 3, "BECERI": 4,
        "GOREV_TAMAM": 5, "HAFTA_HEDEFI": 5, "GOLGE": 5, "DONDURMA": 5, "HATIRLATMA": 6, "EVRIM": 7, "LIG": 7}


# ══════════════════════════════════════════════════════════════════════════════
# Temel kurallar
# ══════════════════════════════════════════════════════════════════════════════

def normal_ad(ad: str) -> str:
    """'Bench  Press' → 'bench press', 'Ölü Kaldırma' → 'olu kaldirma' (Türkçe İ/I doğru küçülür)."""
    kucuk = ad.replace("İ", "i").replace("I", "ı").lower().translate(_HARF)
    return " ".join(kucuk.split())


def hareket_kodu(ad: str, esleme: dict | None = None):
    return (esleme or ESLEME).get(normal_ad(ad))


def sureli_mi(ad) -> bool:
    return bool(_SURELI.search(ad or ""))


def drop_listesi(ham) -> list:
    if isinstance(ham, str):
        import json
        try:
            ham = json.loads(ham)
        except ValueError:
            return []
    return depo.drop_listesi(ham)


def set_tonaj(ad, kilo: float, tekrar: int, drops=None) -> float:
    """Ana set + her drop'un kg × tekrar'ı. Süreli harekette 0."""
    if sureli_mi(ad):
        return 0.0
    ana = float(kilo) * int(tekrar)
    return ana + sum(d["kg"] * d["tekrar"] for d in drop_listesi(drops))


def xp_kilo(ad, kilo: float) -> float:
    return 0.0 if sureli_mi(ad) else float(kilo)


def e1rm(kilo: float, tekrar: int):
    """Epley; 1-12 tekrar dışında tahmin güvenilmez → None."""
    return kilo * (1 + tekrar / 30) if 1 <= tekrar <= 12 else None


def yapildi_mi(s: dict) -> bool:
    if s.get("yapildi") is not None:
        return bool(s["yapildi"])
    return s.get("girildi") is not None or bool(s.get("tamam"))


def set_xp(kilo: float, tekrar: int, yapildi: bool) -> float:
    return 10 + min(20, kilo * tekrar / 50) if yapildi else 0.0


def gun_xp(setler, ogun_kalorileri, gorev: int, pr: int) -> float:
    """setler: [(kilo, tekrar, yapildi)]. Günde en çok 30 set, 6 öğün, 3 görev, 3 rekor puan alır."""
    yapilan = [s for s in setler if s[2]][:30]
    return (sum(set_xp(*s) for s in yapilan)
            + 5 * min(6, sum(1 for k in ogun_kalorileri if k > 0))
            + 50 * min(3, gorev) + 40 * min(3, pr))


def gereken(L: int) -> int:
    """L. seviyeden L+1'e geçmek için gereken XP: 100 · L^1.25."""
    return round(100 * L ** 1.25)


def kumulatif(L: int) -> int:
    return sum(gereken(i) for i in range(1, L))


def seviye(toplam_xp: float) -> int:
    L, kalan = 1, toplam_xp
    while kalan >= gereken(L):
        kalan -= gereken(L)
        L += 1
    return L


def disiplin(kacan_planli_antrenman: int, ogun_kayitli_gun: int) -> int:
    tutulan = 28 - kacan_planli_antrenman
    return min(999, round(999 * (0.6 * tutulan / 28 + 0.4 * ogun_kayitli_gun / 28)))


def gec_mi(etkinlik: date, olusturma) -> bool:
    """Kayıt etkinlik gününden GEC_ESIK_GUN'den fazla sonra girildiyse "geç": XP alır, görev ilerletmez."""
    if olusturma is None:
        return False
    gun = olusturma.date() if isinstance(olusturma, datetime) else olusturma
    return (gun - etkinlik).days > GEC_ESIK_GUN


def gorev_ilerlemesi(kayitlar) -> int:
    return sum(1 for e, o in kayitlar if not gec_mi(e, o))


def pr_durum(onceki_en_iyi, yeni, ikinci_oturumda_tekrar=False) -> str:
    """'yok' · 'pr' · 'dogrulanmamis' (öncekinin %120'sini aşan sıçrama ikinci oturumda tekrarlanmalı)."""
    if onceki_en_iyi is not None and yeni <= onceki_en_iyi:
        return "yok"
    if onceki_en_iyi and yeni > onceki_en_iyi * 1.2 and not ikinci_oturumda_tekrar:
        return "dogrulanmamis"
    return "pr"


def guc(setler, onceki_en_iyi=None, esleme=None) -> int:
    """setler: [(ad, kilo, tekrar, tamam[, oturum])] — en iyi 3 katalog e1RM'nin toplamı (≤ 999)."""
    onceki_en_iyi = onceki_en_iyi or {}
    gorulen: dict = defaultdict(set)
    for s in setler:
        ad, kilo, tekrar, tamam = s[:4]
        kod = hareket_kodu(ad, esleme)
        if not tamam or kod not in KATALOG or sureli_mi(ad):
            continue
        v = e1rm(kilo, tekrar)
        if v is not None:
            gorulen[(kod, round(v, 3))].add(s[4] if len(s) > 4 else 0)
    en_iyi = dict(onceki_en_iyi)
    for (kod, v), oturumlar in gorulen.items():
        o = onceki_en_iyi.get(kod)
        if o and v > o * 1.2 and len(oturumlar) < 2:
            continue
        en_iyi[kod] = max(en_iyi.get(kod, 0), v)
    return min(999, round(sum(sorted(en_iyi.values(), reverse=True)[:3])))


def _guc_pencere(pencere, esleme) -> int:
    """Pencere içindeki oturumları tarih sırasıyla gezer; %20'yi aşan sıçrama ancak tekrar görülünce sayılır."""
    en_iyi: dict = {}
    goruldu: dict = defaultdict(set)
    oturumlar = defaultdict(list)
    for s in pencere:
        oturumlar[(s["tarih"], s.get("oturum"))].append(s)
    for anahtar in sorted(oturumlar, key=lambda k: k[0]):
        for s in oturumlar[anahtar]:
            kod = hareket_kodu(s["ad"], esleme)
            if not s["tamam"] or kod not in KATALOG or sureli_mi(s["ad"]):
                continue
            v = e1rm(float(s["kilo"]), int(s["tekrar"]))
            if v is None:
                continue
            o, iz = en_iyi.get(kod), round(v, 1)
            ilk_kez = iz not in goruldu[kod]
            goruldu[kod].add(iz)
            if o and v > o * 1.2 and ilk_kez:
                continue
            en_iyi[kod] = max(o or 0, v)
    return min(999, round(sum(sorted(en_iyi.values(), reverse=True)[:3])))


# ══════════════════════════════════════════════════════════════════════════════
# Lig ve Gölge
# ══════════════════════════════════════════════════════════════════════════════

def _golge(gecerli_xp: list, i: int):
    """i. haftanın Gölge'si: son 4 geçerli haftanın ortalaması; en az 2 hafta geçmiş ve toplam > 0 olmalı."""
    son4 = gecerli_xp[-4:]
    if i >= 2 and len(son4) >= 2 and sum(son4) > 0:
        return sum(son4) / len(son4)
    return None


def rutbe_ayrinti(haftalar) -> list[dict]:
    """Her biten hafta için lig, Gölge, oran, seri ve sonuç (terfi / kalis / dusme / degerlendirilmedi).
    Terfi: Gölge'nin %110'u ya da 3 hafta üst üste haftalık hedef. Düşme: oran < 0,7 (S'de 0,9) ve hedef tutmadı.
    Deload/dondurma haftası değerlendirilmez, Gölge'ye girmez."""
    r, seri, sonuc, gecerli = 0, 0, [], []
    for i, h in enumerate(haftalar):
        golge = _golge(gecerli, i)
        if h["tur"] != "normal":
            sonuc.append({"lig": RUTBELER[r], "golge": golge, "oran": None, "seri": seri,
                          "sonuc": "degerlendirilmedi",
                          "sebep": t("sebep.dondurma" if h["tur"] == "dondurma" else "sebep.deload")})
            continue
        once, oran, durum_, sebep = r, None, "degerlendirilmedi", t("sebep.gecmis-yok")
        if golge is not None:
            oran = h["xp"] / golge
            seri = seri + 1 if h["tuttu"] else 0
            dus_esik = 0.9 if RUTBELER[r] == "S" else 0.7
            durum_, sebep = "kalis", t("sebep.oran", yuzde=round(oran * 100))
            if (oran >= 1.10 or seri >= 3) and r < 5:
                sebep = t("sebep.seri", seri=seri) if oran < 1.10 else t("sebep.oran", yuzde=round(oran * 100))
                r, seri, durum_ = r + 1, 0, "terfi"
            elif oran < dus_esik and not h["tuttu"] and r > 0:
                r, durum_ = r - 1, "dusme"
            elif h["tuttu"]:
                sebep = t("sebep.seri", seri=seri)
        gecerli.append(h["xp"])
        sonuc.append({"lig": RUTBELER[r], "lig_once": RUTBELER[once], "golge": golge, "oran": oran,
                      "seri": seri, "sonuc": durum_, "sebep": sebep})
    return sonuc


def rutbe_gecmisi(haftalar) -> list[str]:
    return [a["lig"] for a in rutbe_ayrinti(haftalar)]


def golge_serisi(haftalar) -> list:
    """Her haftanın Gölge'si + sonda süren haftanınki (uzunluk len+1)."""
    gecerli, out = [], []
    for i in range(len(haftalar) + 1):
        out.append(_golge(gecerli, i))
        if i < len(haftalar) and haftalar[i]["tur"] == "normal":
            gecerli.append(haftalar[i]["xp"])
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Bildirim yardımcıları
# ══════════════════════════════════════════════════════════════════════════════

def gunluk_bildirim(olay_turleri) -> int:
    """Günlük kart sayısı: anlık rekor ≤ 3; taşan rekor ve diğer olaylar ≤ 2 özet kartına satır olur."""
    turler = list(olay_turleri)
    pr = sum(1 for x in turler if x in ("PR", "REKOR"))
    diger = len(turler) - pr
    anlik = min(3, pr)
    return anlik + min(2, diger + (1 if pr > anlik else 0))


def seviye_bildirimleri(seviye_akisi) -> list[int]:
    """Yalnız yeni zirveler bildirilir (düşüp yeniden çıkılan seviye tekrar kutlanmaz)."""
    zirve, cikan = seviye_akisi[0], []
    for L in seviye_akisi[1:]:
        if L > zirve:
            cikan.append(L)
            zirve = L
    return cikan


def acilan_oduller(bas: int, son: int) -> list[dict]:
    return [o for o in oduller_tablosu() if bas < o["seviye"] <= son]


def _yonelme(n: int) -> str:
    """Sayının yönelme eki: 2'ye · 3'e · 6'ya · 10'a · 40'a · 100'e."""
    birler = {1: "e", 2: "ye", 3: "e", 4: "e", 5: "e", 6: "ya", 7: "ye", 8: "e", 9: "a"}
    onlar = {1: "a", 2: "ye", 3: "a", 4: "a", 5: "ye", 6: "a", 7: "e", 8: "e", 9: "a"}
    if n % 10:
        return birler[n % 10]
    if n % 100:
        return onlar[(n // 10) % 10]
    return "e"


def _odul_metni(oduller) -> str:
    return ", ".join(f"«{o['ad']}»" if o["tur"] == "unvan" else o["ad"] for o in oduller)


def hafta_turu_kontrol(mevcut: dict, hafta: date, tur, bugun: date | None = None):
    """Dondurma takvim ayında 1 · deload 4 haftada en çok 1 · bitmiş hafta işaretlenmez.
    Uygunsa None, değilse kullanıcıya gösterilecek sebep."""
    if tur is None:
        return None
    if tur not in ("deload", "dondurma"):
        return t("hafta.tur-gecersiz")
    if hafta.weekday() != 0:
        return t("hafta.pazartesi")
    if bugun is not None and hafta + timedelta(days=6) < bugun:
        return t("hafta.bitmis")
    for w, x in mevcut.items():
        if w == hafta or x != tur:
            continue
        if tur == "dondurma" and (w.year, w.month) == (hafta.year, hafta.month):
            return t("hafta.dondurma-dolu")
        if tur == "deload" and abs((w - hafta).days) < 28:
            return t("hafta.deload-dolu")
    return None


def hatirlatma_olayi(sonuc: dict, bugun: date):
    acik = sum(1 for g in sonuc.get("gorevler", []) if not g["tamam"])
    if not acik:
        return None
    return {"anahtar": f"hatirlat:{bugun.isoformat()}", "tur": "HATIRLATMA",
            "metin": t("olay.hatirlatma", acik=acik),
            "veri": {"tarih": bugun.isoformat(), "acik": acik}, "teslim": None}


# ══════════════════════════════════════════════════════════════════════════════
# Durum hesabı (saf)
# ══════════════════════════════════════════════════════════════════════════════

def _pazartesi(d: date) -> date:
    return d - timedelta(days=d.weekday())


class _Hesap:
    """durum_hesapla'nın ara tabloları. Her alan bir kez hesaplanır; kural yöntemleri bunları okur."""

    def __init__(self, veri: dict, bugun: date):
        self.bugun = bugun
        self.esleme = veri.get("esleme") or ESLEME
        self.plan = set(veri.get("plan_gunleri") or [1, 3, 5])
        self.hedef_kal = float(veri["hedef"].get("kal") or 0)
        self.hedef_pro = float(veri["hedef"].get("protein") or 0)
        self.hafta_turu = veri.get("hafta_turu") or {}
        self.setler = [dict(s, tamam=yapildi_mi(s)) for s in veri["setler"] if s["tarih"] <= bugun]
        self.ogunler = [o for o in veri["ogunler"] if o["tarih"] <= bugun]
        self.gun_set = defaultdict(list)
        for s in self.setler:
            self.gun_set[s["tarih"]].append(s)
        self.gun_ogun = defaultdict(list)
        for o in self.ogunler:
            self.gun_ogun[o["tarih"]].append(o)
        self.gunler = sorted(set(self.gun_set) | set(self.gun_ogun))
        self.ilk = self.gunler[0] if self.gunler else bugun
        self._rekorlar()
        self._xp()

    # ── sayımlar
    def tamam_sayisi(self, d, gec_haric=False) -> int:
        return sum(1 for s in self.gun_set.get(d, [])
                   if s["tamam"] and not (gec_haric and gec_mi(d, s["olusturma"])))

    def set_hedefi(self, d) -> int:
        onceki = [n for g in self.gun_set if d - timedelta(days=28) <= g < d
                  for n in (self.tamam_sayisi(g),) if n > 0]
        h = round(sum(onceki) / len(onceki)) if onceki else VARSAYILAN_SET_HEDEFI
        if self.hafta_turu.get(_pazartesi(d)) == "deload":
            h = max(1, (h + 1) // 2)
        return h

    def gorevler(self, d) -> list[dict]:
        zamaninda = [o for o in self.gun_ogun.get(d, []) if not gec_mi(d, o["olusturma"])]
        protein = sum(float(o["protein"]) for o in zamaninda)
        ogun_n = sum(1 for o in zamaninda if float(o["kal"]) > 0)
        if d.isoweekday() in self.plan:
            h = self.set_hedefi(d)
            ikinci = {"kod": "antrenman", "ad": t("gorev.antrenman", n=h), "hedef": h,
                      "ilerleme": self.tamam_sayisi(d, gec_haric=True)}
        else:
            ikinci = {"kod": "dinlenme", "ad": t("gorev.dinlenme"), "hedef": 1, "ilerleme": min(1, ogun_n)}
        liste = [
            {"kod": "protein", "ad": t("gorev.protein", g=f"{self.hedef_pro:g}"), "hedef": self.hedef_pro,
             "ilerleme": round(protein, 1)},
            ikinci,
            {"kod": "ogun", "ad": t("gorev.ogun"), "hedef": 3, "ilerleme": ogun_n},
        ]
        for g in liste:
            g["tamam"] = g["hedef"] > 0 and g["ilerleme"] >= g["hedef"]
        return liste

    # ── rekorlar: tüm geçmiş boyunca katalog hareketlerinin en iyi e1RM'i
    def _rekorlar(self):
        en_iyi, bekleyen = {}, defaultdict(set)
        self.gun_pr = defaultdict(list)
        self.en_iyi_seyri = []
        for d in sorted(self.gun_set):
            gunluk = {}
            for s in self.gun_set[d]:
                kod = hareket_kodu(s["ad"], self.esleme)
                if not s["tamam"] or kod not in KATALOG or sureli_mi(s["ad"]):
                    continue
                v = e1rm(float(s["kilo"]), int(s["tekrar"]))
                if v is not None and v > gunluk.get(kod, (0, None))[0]:
                    gunluk[kod] = (v, s)
            for kod, (v, s) in gunluk.items():
                sonuc = pr_durum(en_iyi.get(kod), v, round(v, 1) in bekleyen[kod])
                if sonuc == "pr":
                    en_iyi[kod] = v
                    self.gun_pr[d].append((kod, v, s))
                elif sonuc == "dogrulanmamis":
                    bekleyen[kod].add(round(v, 1))
            if self.gun_pr.get(d):
                self.en_iyi_seyri.append((d, dict(en_iyi)))

    # ── XP: gün XP'si + haftalık hedef bonusu (200) hedefin tuttuğu güne yazılır
    def _xp(self):
        gun_ham = {}
        for d in self.gunler:
            s_list = [(xp_kilo(s["ad"], s["kilo"]), int(s["tekrar"]), s["tamam"]) for s in self.gun_set.get(d, [])]
            kal = [float(o["kal"]) for o in self.gun_ogun.get(d, [])]
            gorev_n = sum(1 for g in self.gorevler(d) if g["tamam"])
            gun_ham[d] = gun_xp(s_list, kal, gorev_n, len(self.gun_pr.get(d, [])))
        self.hafta_ant = defaultdict(int)
        self.hedef_gunu = {}
        for d in self.gunler:
            if self.tamam_sayisi(d) > 0:
                p = _pazartesi(d)
                self.hafta_ant[p] += 1
                if self.hafta_ant[p] == len(self.plan):
                    self.hedef_gunu[p] = d
        self.gun_toplam = {d: x + (200 if self.hedef_gunu.get(_pazartesi(d)) == d else 0)
                           for d, x in gun_ham.items()}
        self.hafta_xp = defaultdict(float)
        for d, x in self.gun_toplam.items():
            self.hafta_xp[_pazartesi(d)] += x
        self.toplam = sum(self.hafta_xp.values())

    def xp_kadar(self, son: date) -> float:
        return sum(x for d, x in self.gun_toplam.items() if d <= son)

    def statlar(self, gun: date) -> dict:
        p28, p7 = gun - timedelta(days=27), gun - timedelta(days=6)
        pencere = sorted((s for s in self.setler if p28 <= s["tarih"] <= gun), key=lambda s: s["tarih"])
        tonaj = sum(_tonaj(s) for s in self.setler if s["tamam"] and p7 <= s["tarih"] <= gun)
        bas = max(p28, self.ilk)
        kacan = sum(1 for i in range((gun - bas).days)
                    if (bas + timedelta(days=i)).isoweekday() in self.plan
                    and self.tamam_sayisi(bas + timedelta(days=i)) == 0)
        ogun_gun = sum(1 for d in self.gun_ogun
                       if p28 <= d <= gun and any(float(o["kal"]) > 0 for o in self.gun_ogun[d]))
        bes_toplam = 0.0
        for i in range(7):
            os_ = self.gun_ogun.get(p7 + timedelta(days=i), [])
            if not os_ or self.hedef_pro <= 0 or self.hedef_kal <= 0:
                continue
            pro = sum(float(o["protein"]) for o in os_)
            kal = sum(float(o["kal"]) for o in os_)
            bes_toplam += (0.6 * min(1, pro / self.hedef_pro)
                           + 0.4 * (1 - min(1, abs(kal - self.hedef_kal) / self.hedef_kal)))
        return {"guc": _guc_pencere(pencere, self.esleme), "day": min(999, round(tonaj / 100)),
                "dis": disiplin(kacan, ogun_gun), "bes": min(999, round(bes_toplam / 7 * 999)), "hiz": None}

    def golge_gecis_gunu(self, hafta: date, esik: float):
        biriken = 0.0
        for i in range(7):
            d = hafta + timedelta(days=i)
            biriken += self.gun_toplam.get(d, 0.0)
            if biriken >= esik and self.gun_toplam.get(d):
                return d
        return None


def _tonaj(s: dict) -> float:
    return set_tonaj(s["ad"], s["kilo"], s["tekrar"], s.get("drops"))


def _beceri_kosullari(h: _Hesap, haftalar, ayrinti, golgeler, bu_hafta, bu_tur) -> dict:
    """Her beceri/evrim kodu → koşulun İLK sağlandığı gün."""
    kosul: dict = {}

    def isaretle(kod, gun):
        if gun is not None and kod not in kosul:
            kosul[kod] = gun

    for d, eb in h.en_iyi_seyri:
        if max(eb.values()) >= 100:
            isaretle("agir_yuk", d)
        if sum(sorted(eb.values(), reverse=True)[:3]) >= 300:
            isaretle("dev_gucu", d)
    pr_sirasi = [d for d in sorted(h.gun_pr) for _ in h.gun_pr[d]]
    isaretle("rekor_avcisi", pr_sirasi[9] if len(pr_sirasi) >= 10 else None)
    isaretle("sinir_kirici", pr_sirasi[49] if len(pr_sirasi) >= 50 else None)
    gun_tonaj = {d: sum(_tonaj(s) for s in ss if s["tamam"]) for d, ss in h.gun_set.items()}
    ant_gunleri = [d for d in sorted(h.gun_set) if h.tamam_sayisi(d) > 0]
    for d in ant_gunleri:
        if gun_tonaj[d] >= 10000:
            isaretle("hacim_bilgesi", d)
        if sum(x for g, x in gun_tonaj.items() if d - timedelta(days=6) <= g <= d) >= 40000:
            isaretle("bitmeyen_nefes", d)
        if h.tamam_sayisi(d) >= 25:
            isaretle("uzun_soluk", d)
    isaretle("demir_tutus", ant_gunleri[9] if len(ant_gunleri) >= 10 else None)
    isaretle("celik_irade", ant_gunleri[49] if len(ant_gunleri) >= 50 else None)
    for onceki, d in zip(ant_gunleri, ant_gunleri[1:]):
        if (d - onceki).days > 14:
            isaretle("donus", d)
            break
    ogun_gunleri = sorted(d for d, os_ in h.gun_ogun.items() if any(float(o["kal"]) > 0 for o in os_))
    isaretle("kayit_tutucu", ogun_gunleri[29] if len(ogun_gunleri) >= 30 else None)
    if h.hedef_pro > 0:
        pro_gun = sorted(d for d, os_ in h.gun_ogun.items() if sum(float(o["protein"]) for o in os_) >= h.hedef_pro)
        seri, onceki = 0, None
        for d in pro_gun:
            seri = seri + 1 if onceki and (d - onceki).days == 1 else 1
            onceki = d
            if seri >= 7:
                isaretle("protein_sezgisi", d)
            if sum(1 for g in pro_gun if d - timedelta(days=29) <= g <= d) >= 25:
                isaretle("metabolik_hakim", d)
    tum = haftalar + [{"hafta": bu_hafta, "xp": h.hafta_xp.get(bu_hafta, 0.0), "tur": bu_tur or "normal",
                       "tuttu": h.hafta_ant.get(bu_hafta, 0) >= len(h.plan)}]
    seri_h = seri_g = 0
    for i, hf in enumerate(tum):
        if hf["tur"] != "normal":
            continue  # dondurma/deload seriyi bozmaz, ilerletmez
        sonuncu = i == len(tum) - 1
        if hf["tuttu"]:
            seri_h += 1
            if seri_h >= 4:
                isaretle("seri_ustasi", h.hedef_gunu.get(hf["hafta"]))
            if seri_h >= 12:
                isaretle("kirilmaz", h.hedef_gunu.get(hf["hafta"]))
        elif not sonuncu:
            seri_h = 0
        g = golgeler[i]
        if g is not None and hf["xp"] >= g * 1.10:
            seri_g += 1
            if seri_g >= 4:
                isaretle("golge_yarisi", h.golge_gecis_gunu(hf["hafta"], g * 1.10))
        elif not sonuncu:
            seri_g = 0
    for hf, a in zip(haftalar, ayrinti):
        if a["lig"] == "S":
            isaretle("golgesiz", hf["hafta"] + timedelta(days=7))
            break
    return kosul


def _beceriler(kosul: dict, kayitli: dict) -> list[dict]:
    liste = []
    for kod, dal, ev_kod, gizli in _BECERI_TABLO:
        edin = kosul.get(kod)
        ev = kosul.get(ev_kod) if ev_kod and edin else None
        if ev is not None:
            ev = max(ev, edin)
        hesap = "evrim" if ev else ("edinildi" if edin else "kapali")
        k = kayitli.get(kod)
        durum_ = "askida" if k and (hesap == "kapali" or (k == "evrim" and hesap == "edinildi")) else hesap
        gorunmez = gizli and durum_ == "kapali"
        liste.append({"kod": kod, "ad": "???" if gorunmez else t(f"beceri.{kod}"), "dal": dal, "durum": durum_,
                      "evrim_kod": ev_kod,
                      "evrim_ad": None if gorunmez or not ev_kod else t(f"beceri.{ev_kod}"),
                      "kosul": "???" if gorunmez else t(f"kosul.{kod}"),
                      "evrim_kosul": None if gorunmez or not ev_kod else t(f"kosul.{ev_kod}"),
                      "gizli": gizli, "tarih": edin.isoformat() if edin else None,
                      "evrim_tarih": ev.isoformat() if ev else None})
    return liste


def durum_hesapla(veri: dict, bugun: date, zirve_seviye: int = 1, kayitli_beceriler: dict | None = None,
                  ozet_hafta: date | None = None) -> dict:
    """Tüm oyun durumu. veri: setler [{tarih, ad, kilo, tekrar, tamam, olusturma, oturum, girildi?, yapildi?,
    drops?}], ogunler [{tarih, kal, protein, olusturma}], hedef {kal, protein}, plan_gunleri, hafta_turu,
    esleme. kayitli_beceriler: kalıcı kazanımlar (dayanağı silinen ⏸ askıda görünür).
    ozet_hafta: haftalık özetin haftası (varsayılan son biten hafta)."""
    h = _Hesap(veri, bugun)
    zirve_seviye = max(1, zirve_seviye or 1)
    L = seviye(h.toplam)
    stat = h.statlar(bugun)

    bu_hafta = _pazartesi(bugun)
    haftalar, w = [], _pazartesi(h.ilk)
    while w < bu_hafta:
        haftalar.append({"hafta": w, "xp": h.hafta_xp.get(w, 0.0), "tur": h.hafta_turu.get(w, "normal"),
                         "tuttu": h.hafta_ant.get(w, 0) >= len(h.plan)})
        w += timedelta(days=7)
    ayrinti = rutbe_ayrinti(haftalar) if haftalar else []
    rutbeler = [a["lig"] for a in ayrinti]
    rutbe = rutbeler[-1] if rutbeler else "E"
    golgeler = golge_serisi(haftalar)
    kalibrasyon = not h.gunler or (bugun - h.ilk).days < KALIBRASYON_GUN
    golge_simdi = golgeler[-1]
    bu_tur = h.hafta_turu.get(bu_hafta)
    dort_once = bu_hafta - timedelta(days=28)
    lig_ilerleme = {
        "golge": round(golge_simdi, 1) if golge_simdi is not None else None,
        "terfi_esik": math.ceil(golge_simdi * 1.10 - 1e-9) if golge_simdi is not None else None,
        "xp": round(h.hafta_xp.get(bu_hafta, 0.0), 1),
        "guvende": h.hafta_ant.get(bu_hafta, 0) >= len(h.plan),
        "degerlendirme": golge_simdi is not None and bu_tur is None,
        # podyumun 3. basamağı "4 hafta önceki sen"; kayıt o haftadan sonra başladıysa None
        "dort_hafta_once": (round(h.hafta_xp.get(dort_once, 0.0))
                            if h.gunler and dort_once >= _pazartesi(h.ilk) else None),
    }

    kosul = _beceri_kosullari(h, haftalar, ayrinti, golgeler, bu_hafta, bu_tur)
    beceriler = _beceriler(kosul, kayitli_beceriler or {})

    zirve_simdi = max(zirve_seviye, L)
    ulasilan_lig = max([0] + [RUTBELER.index(r) for r in rutbeler])
    durumlar = {b["kod"]: b["durum"] for b in beceriler}
    unvanlar = []
    for kod, (kaynak, k) in _UNVAN_KOSUL.items():
        if ((kaynak == "seviye" and zirve_simdi >= k) or (kaynak == "lig" and ulasilan_lig >= RUTBELER.index(k))
                or (kaynak == "evrim" and durumlar.get(k) == "evrim")
                or (kaynak == "beceri" and durumlar.get(k) in ("edinildi", "evrim"))):
            unvanlar.append({"kod": kod, "ad": unvan_ad(kod), "kaynak": kaynak})
    tablo = oduller_tablosu()
    oduller = {"acik": [o for o in tablo if o["seviye"] <= zirve_simdi],
               "sonraki": next((o for o in tablo if o["seviye"] > zirve_simdi), None)}

    haftalik = _haftalik(h, haftalar, ayrinti, golgeler, beceriler, rutbe, bugun,
                         ozet_hafta if ozet_hafta is not None else (haftalar[-1]["hafta"] if haftalar else None))
    olaylar = _olaylar(h, L, zirve_seviye, rutbeler, haftalar, kalibrasyon, stat, rutbe, beceriler,
                       haftalik if ozet_hafta is None else None, bu_hafta, lig_ilerleme, golge_simdi)

    return {
        "hesap_surumu": HESAP_SURUMU,
        "seviye": L, "zirve_seviye": zirve_simdi, "xp_toplam": round(h.toplam, 1),
        "xp_seviye_ici": round(h.toplam - kumulatif(L), 1), "xp_sonraki": gereken(L),
        "stat": stat,
        "rutbe": rutbe, "lig": rutbe, "lig_ad": lig_ad(rutbe), "lig_ilerleme": lig_ilerleme,
        "kalibrasyon": kalibrasyon,
        "hafta_hedefi": {"hedef": len(h.plan), "ilerleme": h.hafta_ant.get(bu_hafta, 0)},
        "hafta_turu": bu_tur,
        "gorevler": h.gorevler(bugun),
        "unvanlar": unvanlar,
        "beceriler": beceriler,
        "oduller": oduller,
        "haftalik_ozet": haftalik,
        "haftalar": [{"hafta": hf["hafta"].isoformat(), "xp": round(hf["xp"], 1), "lig": a["lig"]}
                     for hf, a in zip(haftalar, ayrinti)],
        "olaylar": olaylar,
    }


def _haftalik(h: _Hesap, haftalar, ayrinti, golgeler, beceriler, rutbe, bugun, oh):
    if oh is None:
        return None
    idx = next((i for i, hf in enumerate(haftalar) if hf["hafta"] == oh), None)
    son_gun = oh + timedelta(days=6)
    hs = [s for d in h.gun_set if oh <= d <= son_gun for s in h.gun_set[d] if s["tamam"]]
    agir = max((s for s in hs if not sureli_mi(s["ad"])), key=lambda s: (float(s["kilo"]), int(s["tekrar"])),
               default=None)
    rek = [{"hareket": s["ad"].strip(), "kod": kod, "kilo": float(s["kilo"]), "tekrar": int(s["tekrar"])}
           for d in sorted(h.gun_pr) if oh <= d <= son_gun for kod, v, s in h.gun_pr[d]]
    a = ayrinti[idx] if idx is not None else None
    st_son, st_bas = h.statlar(min(son_gun, bugun)), h.statlar(oh - timedelta(days=1))
    sv_bas, sv_son = seviye(h.xp_kadar(oh - timedelta(days=1))), seviye(h.xp_kadar(son_gun))
    sonraki_g = golgeler[idx + 1] if idx is not None else None
    ay = oh + timedelta(days=7)
    dondu = sum(1 for w, x in h.hafta_turu.items() if x == "dondurma" and (w.year, w.month) == (ay.year, ay.month))
    lig_son = a["lig"] if a else rutbe
    return {
        "hafta": oh.isoformat(), "bitis": son_gun.isoformat(), "xp": round(h.hafta_xp.get(oh, 0.0), 1),
        "golge": round(a["golge"], 1) if a and a["golge"] is not None else None,
        "oran": round(a["oran"], 2) if a and a["oran"] is not None else None,
        "lig_once": (a.get("lig_once") or (ayrinti[idx - 1]["lig"] if idx else "E")) if a else rutbe,
        "lig_sonra": lig_son, "lig_ad": lig_ad(lig_son),
        "sonuc": a["sonuc"] if a else "degerlendirilmedi",
        "sebep": a["sebep"] if a else t("sebep.suruyor"),
        "antrenman": {"gun": h.hafta_ant.get(oh, 0), "hedef": len(h.plan), "yapilan_set": len(hs),
                      "tonaj": round(sum(_tonaj(s) for s in hs), 1),
                      "en_agir": ({"hareket": agir["ad"].strip(), "kilo": float(agir["kilo"]),
                                   "tekrar": int(agir["tekrar"])} if agir else None)},
        "rekorlar": rek[:5], "rekor_fazla": max(0, len(rek) - 5),
        "stat_degisim": {k: st_son[k] - st_bas[k] for k in ("guc", "day", "dis", "bes")},
        "beceriler": [{"kod": b["kod"], "ad": b["ad"], "durum": d_}
                      for b in beceriler for d_, x in (("edinildi", b["tarih"]), ("evrim", b["evrim_tarih"]))
                      if x and oh.isoformat() <= x <= son_gun.isoformat()],
        "seviye": {"bas": sv_bas, "son": sv_son, "acilan": acilan_oduller(sv_bas, sv_son)},
        "bu_hafta": {"terfi_esik": math.ceil(sonraki_g * 1.10 - 1e-9) if sonraki_g is not None else None,
                     "hedef": len(h.plan), "dondurma_hakki": max(0, 1 - dondu)},
        "seri": a["seri"] if a else 0,
    }


def _olaylar(h: _Hesap, L, zirve_seviye, rutbeler, haftalar, kalibrasyon, stat, rutbe, beceriler,
             haftalik, bu_hafta, lig_ilerleme, golge_simdi) -> list[dict]:
    """Bu durumdan doğan olaylar; her olayın tekil anahtarı ve `veri.tarih`'i var (ilk çalışma kuralı ona bakar)."""
    olaylar = []

    def olay(anahtar, tur, metin, tarih: date, **ek):
        olaylar.append({"anahtar": anahtar, "tur": tur, "metin": metin,
                        "veri": {"tarih": tarih.isoformat(), **ek}, "teslim": None})

    for d in sorted(h.gun_pr):
        for kod, v, s in h.gun_pr[d]:
            olay(f"pr:{kod}:{d.isoformat()}:{round(v, 1)}", "REKOR",
                 t("olay.rekor", ad=s["ad"].strip(), kg=f"{float(s['kilo']):g}", tekrar=int(s["tekrar"])),
                 d, kod=kod, e1rm=round(v, 1), kilo=float(s["kilo"]), tekrar=int(s["tekrar"]), hareket=s["ad"].strip())
    if L > zirve_seviye:
        acilan = acilan_oduller(zirve_seviye, L)
        metin = t("olay.seviye", sv=L, ek=_yonelme(L))
        if acilan:
            metin += " " + t("olay.seviye-acilan", liste=_odul_metni(acilan))
        olay(f"seviye:{L}", "SEVIYE", metin, h.bugun, seviye=L, onceki_zirve=zirve_seviye, acilan=acilan)
    if len(rutbeler) >= 2 and rutbeler[-1] != rutbeler[-2]:
        eski, yeni = rutbeler[-2], rutbeler[-1]
        terfi = RUTBELER.index(yeni) > RUTBELER.index(eski)
        olay(f"lig:{haftalar[-1]['hafta'].isoformat()}", "LIG",
             t("olay.lig-terfi" if terfi else "olay.lig-dusme", eski=lig_ad(eski), yeni=lig_ad(yeni)),
             haftalar[-1]["hafta"] + timedelta(days=7), onceki=eski, yeni=yeni, onceki_ad=lig_ad(eski),
             yeni_ad=lig_ad(yeni), yon="terfi" if terfi else "dusme")
    if not kalibrasyon:
        olay("uyanis", "UYANIS", t("olay.uyanis", lig=lig_ad(rutbe), **stat),
             h.ilk + timedelta(days=KALIBRASYON_GUN), **stat)
    for b in beceriler:
        if b["tarih"]:
            olay(f"beceri:{b['kod']}", "BECERI", t("olay.beceri", ad=b["ad"]), date.fromisoformat(b["tarih"]),
                 kod=b["kod"], ad=b["ad"], dal=b["dal"])
        if b["evrim_tarih"]:
            unvan = next((k for k, (kay, kk) in _UNVAN_KOSUL.items() if kay == "evrim" and kk == b["kod"]), None)
            olay(f"evrim:{b['evrim_kod']}", "EVRIM", t("olay.evrim", ad=b["ad"], evrim=b["evrim_ad"]),
                 date.fromisoformat(b["evrim_tarih"]), kod=b["evrim_kod"], ad=b["evrim_ad"], beceri=b["kod"],
                 unvan=unvan)
    if haftalik and (haftalik["xp"] > 0 or haftalik["lig_once"] != haftalik["lig_sonra"]):
        metin = (t("olay.ozet-golge", xp=f"{haftalik['xp']:g}", golge=f"{haftalik['golge']:g}", lig=haftalik["lig_ad"])
                 if haftalik["golge"] is not None else
                 t("olay.ozet", xp=f"{haftalik['xp']:g}", lig=haftalik["lig_ad"]))
        olay(f"ozet:{haftalik['hafta']}", "HAFTALIK_OZET", metin, bu_hafta, hafta=haftalik["hafta"],
             xp=haftalik["xp"], golge=haftalik["golge"], lig=haftalik["lig_sonra"], lig_ad=haftalik["lig_ad"])
    if all(g["tamam"] for g in h.gorevler(h.bugun)):
        olay(f"gorev:{h.bugun.isoformat()}", "GOREV_TAMAM", t("olay.gorev"), h.bugun, xp=150)
    if bu_hafta in h.hedef_gunu:
        n = len(h.plan)
        olay(f"hedef:{bu_hafta.isoformat()}", "HAFTA_HEDEFI", t("olay.hedef", n=n), h.hedef_gunu[bu_hafta], n=n)
    if lig_ilerleme["degerlendirme"] and lig_ilerleme["xp"] >= golge_simdi * 1.10:
        olay(f"golge:{bu_hafta.isoformat()}", "GOLGE",
             t("olay.golge", xp=f"{lig_ilerleme['xp']:g}", golge=f"{round(golge_simdi):g}"),
             h.golge_gecis_gunu(bu_hafta, golge_simdi * 1.10) or h.bugun,
             xp=lig_ilerleme["xp"], golge=round(golge_simdi, 1))
    for w, x in sorted(h.hafta_turu.items()):
        if w <= h.bugun:
            olay(f"dondur:{w.isoformat()}", "DONDURMA", t("olay.dondurma" if x == "dondurma" else "olay.deload"),
                 w, hafta=w.isoformat(), hafta_tur=x)
    return olaylar


# Kişisel sürümle aynı adla erişilen tablolar (testler ve ön yüz sözlüğü bunları okur)
def __getattr__(ad):
    if ad == "ODULLER":
        return oduller_tablosu()
    if ad == "LIG_AD":
        return {k: lig_ad(k) for k in RUTBELER}
    if ad == "UNVANLAR":
        return {k: (unvan_ad(k), kay, kk) for k, (kay, kk) in _UNVAN_KOSUL.items()}
    if ad == "BECERILER":
        return [(kod, t(f"beceri.{kod}"), dal, t(f"kosul.{kod}"), ev, t(f"beceri.{ev}") if ev else None,
                 t(f"kosul.{ev}") if ev else None, gizli) for kod, dal, ev, gizli in _BECERI_TABLO]
    raise AttributeError(ad)


# ══════════════════════════════════════════════════════════════════════════════
# Depo katmanı
# ══════════════════════════════════════════════════════════════════════════════

def _zaman(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v))
    except ValueError:
        return None


def veri_oku(db: dict | None = None) -> dict:
    """Depo sözlüğü → durum_hesapla girdisi."""
    db = db if db is not None else depo.oku()
    w_gun = {w["id"]: w for w in db["workouts"]}
    ex = {e["id"]: e for e in db["exercises"]}
    setler = []
    for s in sorted(db["sets"], key=lambda s: s.get("position", 0)):
        e = ex.get(s.get("exercise_id"))
        w = w_gun.get(e["workout_id"]) if e else None
        if not w:
            continue
        try:
            gun = date.fromisoformat(str(w["session_date"])[:10])
        except ValueError:
            continue
        setler.append({"tarih": gun, "oturum": w["id"], "ad": e.get("name") or "", "tekrar": int(s.get("reps") or 0),
                       "kilo": float(s.get("weight") or 0), "tamam": bool(s.get("completed")),
                       "olusturma": _zaman(s.get("created_at")), "set_id": s["id"], "girildi": s.get("girildi"),
                       "drops": drop_listesi(s.get("drops")), "sablon_id": e.get("sablon_id"),
                       "yapildi": depo.yapildi_mi(s), "_sira": (gun, float(e.get("position", 0)))})
    setler.sort(key=lambda s: s.pop("_sira"))
    ogunler = []
    for m in db["meals"]:
        try:
            gun = date.fromisoformat(str(m["entry_date"])[:10])
        except (KeyError, ValueError):
            continue
        ogunler.append({"tarih": gun, "kal": float(m.get("cal") or 0), "protein": float(m.get("protein") or 0),
                        "olusturma": _zaman(m.get("created_at"))})
    hafta_turu = {}
    for k, v in (db.get("hafta_turu") or {}).items():
        try:
            hafta_turu[date.fromisoformat(k)] = v
        except ValueError:
            continue
    cfg = db["config"]
    return {"setler": setler, "ogunler": ogunler,
            "hedef": {"kal": cfg.get("calGoal", 2000), "protein": cfg.get("proteinGoal", 150)},
            "plan_gunleri": depo.plan_gunleri(db), "hafta_turu": hafta_turu, "esleme": ESLEME}


def zirve(db: dict) -> int:
    return max([1] + [int((o.get("veri") or {}).get("seviye") or 1) for o in db["olaylar"] if o.get("tur") == "SEVIYE"])


def _kayitli_beceriler(db: dict) -> dict:
    return {k: v.get("durum") for k, v in (db.get("beceriler") or {}).items()}


def olay_yaz(db: dict, anahtar: str, tur: str, metin: str, veri: dict, goruldu: bool = False):
    """Tekil anahtarla ekler; anahtar varsa None, yoksa yeni kayıt."""
    if any(o.get("anahtar") == anahtar for o in db["olaylar"]):
        return None
    k = {"id": depo._uid(), "anahtar": anahtar, "tur": tur, "metin": metin, "veri": veri,
         "olustu": depo._simdi(), "goruldu": goruldu, "teslim": None, "itildi": None}
    db["olaylar"].append(k)
    return k


def _uret(db: dict, bugun: date, gecis=None, simdi: datetime | None = None):
    sonuc = durum_hesapla(veri_oku(db), bugun, zirve(db), _kayitli_beceriler(db))
    if gecis is None:
        gecis = not any(o.get("anahtar") == f"surum:{HESAP_SURUMU}" for o in db["olaylar"])
    ozet_erken = simdi is not None and bugun.weekday() == 0 and simdi.time() < OZET_SAATI
    yeni = []
    for o in sonuc["olaylar"]:
        if ozet_erken and o["tur"] == "HAFTALIK_OZET":
            continue
        # İlk çalışma: geçmişte kalmış kutlamalar sessizce "görüldü" yazılır, bugünkü gösterilir.
        goruldu = bool(gecis and o["veri"]["tarih"] < bugun.isoformat())
        k = olay_yaz(db, o["anahtar"], o["tur"], o["metin"], o["veri"], goruldu)
        if k is not None:
            yeni.append({**o, "id": k["id"], "goruldu": goruldu})
    if gecis:
        olay_yaz(db, f"surum:{HESAP_SURUMU}", "SURUM", t("olay.surum", sv=sonuc["seviye"], lig=sonuc["lig_ad"]),
                 {"tarih": bugun.isoformat(), "surum": HESAP_SURUMU}, not SURUM_KARTI_GOSTER)
    for b in sonuc["beceriler"]:
        if b["durum"] in ("edinildi", "evrim"):
            mevcut = db["beceriler"].get(b["kod"])
            if mevcut is None or (mevcut.get("durum") == "edinildi" and b["durum"] == "evrim"):
                db["beceriler"][b["kod"]] = {"durum": b["durum"], "zaman": depo._simdi()}
    for u in sonuc["unvanlar"]:
        db["unvanlar"].setdefault(u["kod"], {"kazanildi": depo._simdi(), "secili": False})
    return sonuc, yeni


def olay_uret(bugun: date | None = None, gecis=None, simdi: datetime | None = None) -> list[dict]:
    """Hesaplar, yeni olayları yazar; yalnız BU turda yazılanları döner. Yazma uçlarından sonra çağrılır."""
    bugun = bugun or depo.bugun()
    with depo.islem() as db:
        return _uret(db, bugun, gecis, simdi)[1]


def durum(bugun: date | None = None, simdi: datetime | None = None) -> dict:
    """GET /durum: olay üretimi + kalıcı kazanımlar + bekleyen olaylar (ekran sırasıyla)."""
    bugun = bugun or depo.bugun()
    with depo.islem() as db:
        sonuc, _ = _uret(db, bugun, None, simdi)
        sonuc.pop("olaylar")
        sonuc.pop("haftalar")
        tum = [{"kod": kod, "ad": unvan_ad(kod), "kaynak": _UNVAN_KOSUL.get(kod, ("?", None))[0],
                "kazanildi": r.get("kazanildi"), "secili": bool(r.get("secili"))}
               for kod, r in db["unvanlar"].items()]
        tum.sort(key=lambda u: u["kazanildi"] or "")
        sonuc["unvanlar"] = tum
        secili = next((u["kod"] for u in tum if u["secili"]), None)
        sonuc["unvan_secili"] = secili or (tum[-1]["kod"] if tum else None)
        bekleyen = [{"id": o["id"], "anahtar": o["anahtar"], "tur": o["tur"], "metin": o["metin"],
                     "veri": o.get("veri") or {}, "teslim": o.get("teslim") or TESLIM.get(o["tur"], "kart"),
                     "olustu": o.get("olustu")}
                    for o in sorted(db["olaylar"], key=lambda o: o.get("olustu") or "") if not o.get("goruldu")]
        bekleyen.sort(key=lambda o: SIRA.get(o["tur"], 9))  # kararlı: eşitlerde oluşma sırası kalır
        sonuc["bekleyen_olaylar"] = bekleyen
        return sonuc


def haftalik_ozet(hafta: date, bugun: date | None = None) -> dict | None:
    """Verilen haftanın özeti (yazma yapmaz). Hafta pazartesi değilse ValueError."""
    if hafta.weekday() != 0:
        raise ValueError("hafta pazartesi olmalı")
    db = depo.oku()
    return durum_hesapla(veri_oku(db), bugun or depo.bugun(), zirve(db), _kayitli_beceriler(db),
                         ozet_hafta=hafta)["haftalik_ozet"]

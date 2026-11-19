"""Fitnes bildirim teslimi — tarayıcı bildirimi (push) + sayfa kartı.

Olayı motor üretir (`fitness_oyun.olay_uret`); bu modül yalnız TESLİMİ karara bağlar:
  - `teslim_karari()` saf: tür → anlik | kart | ozet | bekleyen; push ve ses kararı.
  - `ilet()` teslimi yazılmamış olayları sıraya dizer, karar verir, `teslim` yazar. Push gidecekse
    ÖNCE `itildi` damgalanır ve depo kaydedilir, SONRA gönderilir: gönderim yarıda kalsa da aynı olay
    iki kez itilmez.
  - Tavanlar: günde en çok 5 kart/anlık (EVRIM, LIG, DONDURMA sayılmaz), rekor en çok 3. Taşan olay
    "bekleyen"e düşer, ertesi açılışta kartta görünür. Sessiz saatte ve geçmiş tarihli olayda push yok.
  - Zamanlayıcı: 21:00 açık görev hatırlatması · Pzt 00:05 lig · Pzt 08:30 haftalık özet (+ açılış telafisi).

Gerçek gönderim `gonder`/`kaydet` kancalarıyla değiştirilebilir (testler sahte yürütücü verir).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.services import fitness_store as depo
from app.services.fitnes_metin import t

logger = logging.getLogger(__name__)

GUNLUK_TAVAN = 5
REKOR_TAVAN = 3
FITNES_URL = "/ui/planner.html#fitnes"
VARSAYILAN_AYAR = {"push": True, "hatirlatma": True, "sessiz": [23, 8]}

KANAL = {
    "SEVIYE": "anlik", "REKOR": "anlik", "PR": "anlik", "HAFTALIK_OZET": "anlik",
    "UYANIS": "anlik", "HATIRLATMA": "anlik",
    "BECERI": "kart", "GOREV_TAMAM": "kart", "HAFTA_HEDEFI": "kart", "GOLGE": "kart", "DONDURMA": "kart",
    "EVRIM": "ozet", "LIG": "ozet",
}
SAYILMAZ = {"EVRIM", "LIG", "DONDURMA"}
REKOR_TURLERI = {"REKOR", "PR"}
SESLI = {"SEVIYE", "UYANIS"}
_SIRA_LISTE = ["SEVIYE", "HAFTALIK_OZET", "UYANIS", "REKOR", "BECERI", "GOREV_TAMAM", "HATIRLATMA"]
SIRA = {x: i for i, x in enumerate(_SIRA_LISTE)}
SIRA.update({"PR": SIRA["REKOR"], "HAFTA_HEDEFI": SIRA["GOREV_TAMAM"], "GOLGE": SIRA["GOREV_TAMAM"],
             "DONDURMA": SIRA["GOREV_TAMAM"]})
_TARIHLI = {"REKOR", "PR", "GOREV_TAMAM", "HATIRLATMA"}
_TARIH_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


# ── saf kurallar ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Karar:
    teslim: str      # anlik | kart | ozet | bekleyen
    push: bool
    ses: bool        # sayfa görünürken Yuki okur mu
    sayilir: bool    # günlük tavana sayılır mı
    neden: str = ""


def sessiz_mi(an: datetime, sessiz=(23, 8)) -> bool:
    bas, bit = int(sessiz[0]), int(sessiz[1])
    h = an.hour
    return (h >= bas or h < bit) if bas > bit else (bas <= h < bit)


def olay_tarihi(olay: dict):
    """Olayın günü: `veri.tarih`, yoksa tarihli türlerde anahtardaki ilk tarih."""
    v = olay.get("veri") if isinstance(olay.get("veri"), dict) else {}
    x = v.get("tarih")
    if not x and olay.get("tur") in _TARIHLI:
        m = _TARIH_RE.search(olay.get("anahtar") or "")
        x = m.group(0) if m else None
    try:
        return date.fromisoformat(str(x)[:10]) if x else None
    except ValueError:
        return None


def teslim_karari(olay: dict, an: datetime, bugun_sayilan: int, bugun_rekor: int = 0,
                  ayar: dict | None = None) -> Karar:
    ayar = {**VARSAYILAN_AYAR, **(ayar or {})}
    tur = olay.get("tur", "")
    kanal = KANAL.get(tur, "kart")
    if kanal == "ozet":
        return Karar("ozet", False, False, False, "haftalık özet satırı")
    sayilir = tur not in SAYILMAZ
    if sayilir and bugun_sayilan >= GUNLUK_TAVAN:
        return Karar("bekleyen", False, False, False, "günlük tavan dolu")
    if tur in REKOR_TURLERI and bugun_rekor >= REKOR_TAVAN:
        return Karar("bekleyen", False, False, False, "rekor tavanı dolu")
    if kanal == "kart":
        return Karar("kart", False, False, sayilir)
    gun = olay_tarihi(olay)
    # Haftalık özetin tarihi pazartesidir: 08:30 kaçtıysa sonraki ilk açılışta yine push'lanır.
    if tur != "HAFTALIK_OZET" and gun is not None and gun < an.date():
        return Karar("kart", False, False, sayilir, "geçmiş tarihli")
    if not ayar.get("push", True):
        return Karar("kart", False, False, sayilir, "push kapalı")
    if sessiz_mi(an, ayar.get("sessiz") or VARSAYILAN_AYAR["sessiz"]):
        return Karar("kart", False, False, sayilir, "sessiz saat")
    v = olay.get("veri") if isinstance(olay.get("veri"), dict) else {}
    ses = tur in SESLI or (tur == "HAFTALIK_OZET" and bool(v.get("sesli")))
    return Karar("anlik", True, ses, sayilir)


def sirala(olaylar: list[dict]) -> list[dict]:
    return sorted(olaylar, key=lambda o: (SIRA.get(o.get("tur"), len(SIRA)), str(o.get("olustu") or "")))


# ── depo katmanı ──────────────────────────────────────────────────────────────

def ayar_oku(db: dict | None = None) -> dict:
    v = depo.cfg_oku("bildirim", db)
    return {**VARSAYILAN_AYAR, **(v if isinstance(v, dict) else {})}


def _yerel_gun(olustu) -> date | None:
    try:
        return datetime.fromisoformat(str(olustu)).astimezone(depo._tz()).date()
    except (TypeError, ValueError):
        return None


def bugun_sayilan(db: dict, gun: date) -> int:
    """Bugün kart/anlık olarak teslim edilmiş, tavana sayılan olay sayısı."""
    return sum(1 for o in db["olaylar"] if o.get("teslim") in ("anlik", "kart") and o.get("tur") not in SAYILMAZ
               and _yerel_gun(o.get("olustu")) == gun)


def _bugun_rekor(db: dict, gun: date) -> int:
    return sum(1 for o in db["olaylar"] if o.get("teslim") in ("anlik", "kart") and o.get("tur") in REKOR_TURLERI
               and _yerel_gun(o.get("olustu")) == gun)


async def _varsayilan_gonder(baslik: str, govde: str, url: str) -> int:
    from app.api.push import send_push_to_all
    return await send_push_to_all(baslik, govde, url)


async def _varsayilan_kaydet(metin: str, telefon: int) -> None:
    from app.api.push import yuki_dedi_kaydet
    await yuki_dedi_kaydet("fitnes", metin, 0, telefon, 0)


def _karara_bagla(an: datetime) -> tuple[list[dict], list[dict]]:
    """Kilit içinde: teslimi yazılmamış olaylara karar ver, yaz. Dönüş: (sonuç listesi, itilecekler)."""
    gun = an.date()
    sonuc, itilecek = [], []
    with depo.islem() as db:
        ayar = ayar_oku(db)
        sayilan, rekor = bugun_sayilan(db, gun), _bugun_rekor(db, gun)
        adaylar = [o for o in db["olaylar"] if o.get("teslim") is None and not o.get("goruldu")]
        for o in sirala(adaylar):
            k = teslim_karari(o, an, sayilan, rekor, ayar)
            o["teslim"] = k.teslim
            if k.push and not o.get("itildi"):
                o["itildi"] = depo._simdi()   # önce damga (depo bu blok sonunda kaydedilir), sonra gönderim
                itilecek.append({"anahtar": o["anahtar"], "metin": o["metin"]})
            if k.sayilir and k.teslim in ("anlik", "kart"):
                sayilan += 1
                if o["tur"] in REKOR_TURLERI:
                    rekor += 1
            sonuc.append({"anahtar": o["anahtar"], "tur": o["tur"], "teslim": k.teslim, "push": k.push,
                          "ses": k.ses, "gonderildi": 0, "neden": k.neden})
    return sonuc, itilecek


async def ilet(an: datetime | None = None, gonder=None, kaydet=None) -> list[dict]:
    """Teslimi yazılmamış olayları karara bağlar; ANLIK olanları push'lar. Dönüş: işlenen olaylar."""
    an = an or depo.simdi()
    gonder = gonder or _varsayilan_gonder
    kaydet = kaydet or _varsayilan_kaydet
    sonuc, itilecek = _karara_bagla(an)
    gonderilen = {}
    for p in itilecek:
        try:
            n = await gonder(t("bildirim.baslik"), p["metin"], FITNES_URL)
            gonderilen[p["anahtar"]] = n
            await kaydet(p["metin"], n)
        except Exception as e:  # noqa: BLE001 — push düşse de olay kartta kalır
            logger.warning("Fitnes push gönderilemedi (%s): %s", p["anahtar"], e)
    for s in sonuc:
        s["gonderildi"] = gonderilen.get(s["anahtar"], 0)
    return sonuc


def _olay_ekle(anahtar: str, tur: str, metin: str, veri: dict) -> bool:
    from app.services import fitness_oyun as F
    with depo.islem() as db:
        return F.olay_yaz(db, anahtar, tur, metin, veri) is not None


async def hatirlatma(an: datetime | None = None, gonder=None, kaydet=None) -> list[dict]:
    """21:00: açık görev varsa HATIRLATMA olayı (ayarla kapatılır), sonra ilet."""
    from app.services import fitness_oyun as F
    an = an or depo.simdi()
    if not ayar_oku().get("hatirlatma", True):
        return []
    gun = an.date()
    olay = F.hatirlatma_olayi(F.durum_hesapla(F.veri_oku(), gun), gun)
    if olay:
        _olay_ekle(olay["anahtar"], olay["tur"], olay["metin"], olay["veri"])
    return await ilet(an, gonder, kaydet)


async def uret_ve_ilet(an: datetime | None = None, gonder=None, kaydet=None) -> list[dict]:
    """Olay üret (haftalık özet kendi 08:30 kapısıyla) + ilet. Lig/haftalık iş ve yazma uçları bunu çağırır."""
    from app.services import fitness_oyun as F
    an = an or depo.simdi()
    F.olay_uret(an.date(), simdi=an)
    return await ilet(an, gonder, kaydet)


async def _is(ad: str, is_) -> None:
    # FITNES ayardan canlı açılıp kapanır; iş zamanlayıcıda hep kayıtlı → kapı burada, koşarken.
    from app.services.yetki import bayrak_acik
    if not bayrak_acik("fitnes"):
        return
    try:
        await is_()
    except Exception as e:  # noqa: BLE001
        logger.warning("Fitnes bildirim işi (%s) başarısız: %s", ad, e)


async def hatirlatma_isi() -> None:
    await _is("hatirlatma", hatirlatma)


async def lig_isi() -> None:
    await _is("lig", uret_ve_ilet)


async def haftalik_isi() -> None:
    await _is("haftalik", uret_ve_ilet)


def zamanlayiciya_ekle(sched, an: datetime | None = None) -> None:
    """Zamanlayıcı açılışında çağrılır (`scheduler.startup`, FITNES'ten bağımsız; kapı `_is`'te). Bilgisayar gece kapalı olabilir: açılışta
    haftalık özet telafisi (özet kendi saat kapısını ve tekil anahtarını denetler, erken çağrı zararsız)."""
    if not sched.get_job("fitnes_hatirlatma"):
        sched.add_job(hatirlatma_isi, trigger="cron", hour=21, minute=0, id="fitnes_hatirlatma")
    if not sched.get_job("fitnes_lig"):
        sched.add_job(lig_isi, trigger="cron", day_of_week="mon", hour=0, minute=5, id="fitnes_lig")
    if not sched.get_job("fitnes_haftalik"):
        sched.add_job(haftalik_isi, trigger="cron", day_of_week="mon", hour=8, minute=30, id="fitnes_haftalik")
    sched.add_job(haftalik_isi, trigger="date", run_date=(an or depo.simdi()) + timedelta(seconds=45),
                  id="fitnes_haftalik_telafi", replace_existing=True)

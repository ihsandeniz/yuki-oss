"""Atölye öneri motoru — "bunu ben yapayım mı?" adaylarını kuyruğa ÖNERİ olarak yazar.

Motor görev BAŞLATAMAZ. Ayrım içe aktarma düzeyindedir: bu modül görev servisini ve kuyruğu
içe aktarmaz; yazma işlevi dışarıdan verilir (`OneriMotoru(oner=…)`), kuyruk da kaydı `oneri`
durumunda açar — kullanıcı onaylamadan hiçbir şey koşmaz. Testte AST ile ölçülür.

Kaynaklar deterministiktir (LLM yok):
  plan    Plan'da adı `YUKI_ATOLYE_ONERI_PLAN_LISTE` (varsayılan "Yuki") olan listenin açık
          görevleri; tür sezgisi tutmayan başlık önerilmez.
  yarim   kendiliğinden duran iş (gece, yeniden başlatma, asılma, sağlayıcı, kota; son 48 sa)
          → "devam edeyim mi?"; onay AYNI işi kaldığı adımdan sürdürür (`devam_gid`).
  rutin   aynı tür + benzer istek en az 3 kez `bitti` → "bir kez daha yapayım mı?".

Gürültü korkulukları (ortam değişkeniyle ayarlanır, bozuk değer varsayılana düşer):
  · günde en çok YUKI_ATOLYE_ONERI_GUNLUK (3) yeni öneri · aynı anda en çok 3 açık öneri
  · reddedilen kaynak 7 gün, düşen 1 gün susar · aynı kaynak ikinci kez açılmaz
  · tur yalnız Atölye çalışma penceresinde (`gorev_kapilari.pencerede_mi`)
  · TÜMÜNÜ DURDUR basıldıysa gün sonuna kadar tur hiçbir şey yazmaz
  · bildirim (`gorev_bildirim`): YUKI_ATOLYE_ONERI_BILDIRIM_DK (120) dakikada en çok 1,
    sessiz saatte (YUKI_ATOLYE_SESSIZ, 23-08) hiç; YUKI_ATOLYE_ONERI_BILDIRIM=0 tamamen kapatır.
    Bildirim metni öneri içeriğini taşımaz (kilit ekranında okunur).

Durum defteri `<atölye kökü>/.kuyruk/onerici.json`. Bozuk defter → bugün DOLU sayılır,
üzerine yazılmaz.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.services import gorev_bildirim as _bildirim
from app.services import gorev_kapilari as _kapi

logger = logging.getLogger(__name__)

KAYNAKLAR = ("plan", "yarim", "rutin")
ACIK_AZAMI = 3
RED_SUSMA = 7 * 24 * 3600
DUSME_SUSMA = 24 * 3600
YARIM_PENCERE = 48 * 3600
TEKRAR_ESIGI = 3
BENZERLIK = 0.6
# Kendiliğinden duruş nedenleri (gorev_kuyrugu.TELAFI_NEDENLERI ile aynı; o modül içe aktarılmaz)
YARIM_NEDENLERI = frozenset({"gece", "yeniden_baslatma", "asildi", "saglayici_gecici", "kota"})
_ACIK = ("oneri", "onay_bekliyor")
_SURUYOR = _ACIK + ("sirada", "kosuyor", "ertelendi")
_AD = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_TUR_IPUCU = (
    ("arastirma", re.compile(r"araştır|arastir|özetle|ozetle|karşılaştır|karsilastir|incele|"
                             r"research|summari[sz]e|compare", re.I)),
    ("site", re.compile(r"\bsite|\bsayfa|web ?sayfa|landing|\bpage\b|website", re.I)),
)


def _zaman() -> float:
    """Saat — testler sahte saatle değiştirir."""
    return time.time()


def _ortam(ad: str, varsayilan: str) -> str:
    v = os.environ.get(ad)
    return varsayilan if v is None or not v.strip() else v.strip()


def _pozitif(ad: str, varsayilan: int) -> int:
    try:
        v = int(_ortam(ad, str(varsayilan)))
    except ValueError:
        logger.warning("[oneri] %s okunamadı → %s", ad, varsayilan)
        return varsayilan
    return v if v > 0 else varsayilan


def ayarlar() -> dict:
    istenen = {x.strip() for x in _ortam("YUKI_ATOLYE_ONERI_KAYNAKLAR", ",".join(KAYNAKLAR)).split(",")}
    return {
        # Bildirim yalnız açıkça "0" ile kapanır.
        "bildirim": _ortam("YUKI_ATOLYE_ONERI_BILDIRIM", "1") != "0",
        "gunluk": _pozitif("YUKI_ATOLYE_ONERI_GUNLUK", 3),
        "aralik_sn": _pozitif("YUKI_ATOLYE_ONERI_BILDIRIM_DK", 120) * 60,
        "sessiz": _bildirim.sessiz_aralik(),
        "plan_liste": _ortam("YUKI_ATOLYE_ONERI_PLAN_LISTE", "Yuki"),
        # Kodu olmayan kaynak adı ayarla açılamaz.
        "kaynaklar": tuple(k for k in KAYNAKLAR if k in istenen),
    }


@dataclass
class Aday:
    tur: str
    ad: str
    istek: str
    kaynak: str
    kaynak_ref: str
    gerekce: str
    oncelik: int = 2
    devam_gid: str | None = None


def tur_tahmini(metin: str) -> str | None:
    for tur, desen in _TUR_IPUCU:
        if desen.search(metin or ""):
            return tur
    return None


def kisa_ad(metin: str) -> str:
    t = (metin or "").replace("ı", "i").replace("İ", "i")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:40].rstrip("-")
    return t if t and _AD.match(t) else "is"


def _iz_ozeti(metin: str) -> str:
    return hashlib.sha256((metin or "").encode("utf-8")).hexdigest()[:12]


def _tek_satir(metin, azami: int = 500) -> str:
    return " ".join(str(metin or "").split())[:azami]


# ── kaynaklar (saf işlevler) ───────────────────────────────────────────────

def plan_adaylari(gorevler: list[dict]) -> list[Aday]:
    """`gorevler`: Plan listesinin açık görevleri `{"id", "baslik"}`."""
    out = []
    for g in gorevler:
        baslik = _tek_satir(g.get("baslik"))
        tur = tur_tahmini(baslik)
        if tur and g.get("id"):
            out.append(Aday(tur, kisa_ad(baslik), baslik, "plan", f"todo:{g['id']}",
                            "Plan listende bekliyor"))
    return out


def _zaman_damgasi(metin: str) -> float | None:
    try:
        return time.mktime(time.strptime(metin or "", "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return None


def yarim_adaylari(gorevler: list[dict], simdi: float) -> list[Aday]:
    """`gorevler`: görev servisinin `durum.json` kayıtları."""
    out = []
    for d in gorevler:
        if d.get("durum") != "durdu" or d.get("neden") not in YARIM_NEDENLERI:
            continue
        t = _zaman_damgasi(d.get("guncelleme"))
        if t is None or simdi - t > YARIM_PENCERE:
            continue
        gid = str(d.get("id") or "")
        tur, _, ad = gid.partition("/")
        if not tur or not ad:
            continue
        out.append(Aday(tur, ad, f"{gid} görevini kaldığı adımdan sürdür", "yarim",
                        f"gorev:{gid}@{d.get('guncelleme')}",
                        f"yarım kaldı ({d.get('neden')}) — devam edeyim mi?", 1, gid))
    return out


def _kelime_kumesi(metin: str) -> frozenset:
    return frozenset(w for w in re.findall(r"\w+", (metin or "").lower()) if len(w) >= 4)


def rutin_adaylari(gorevler: list[dict]) -> list[Aday]:
    """Aynı tür + benzer istek (kelime kümesi Jaccard ≥ BENZERLIK) en az TEKRAR_ESIGI kez bitti."""
    gruplar: list[tuple[str, frozenset, list[dict]]] = []
    for d in sorted(gorevler, key=lambda x: x.get("guncelleme") or ""):
        if d.get("durum") != "bitti":
            continue
        tur = str(d.get("tur") or str(d.get("id") or "/").split("/")[0])
        k = _kelime_kumesi(d.get("istek"))
        if not k:
            continue
        for gt, gk, uyeler in gruplar:
            if gt == tur and len(gk & k) / len(gk | k) >= BENZERLIK:
                uyeler.append(d)
                break
        else:
            gruplar.append((tur, k, [d]))
    out = []
    for tur, k, uyeler in gruplar:
        if len(uyeler) < TEKRAR_ESIGI:
            continue
        son = uyeler[-1]
        out.append(Aday(tur, kisa_ad(str(son.get("id") or "/").split("/")[-1]),
                        _tek_satir(son.get("istek")), "rutin",
                        f"rutin:{tur}:{_iz_ozeti(' '.join(sorted(k)))}",
                        f"bunu {len(uyeler)} kez yaptırdın — bir kez daha yapayım mı?", 3))
    return out


# ── varsayılan dış bağlantılar ────────────────────────────────────────────

async def plan_listesi_oku(liste_adi: str) -> list[dict]:
    """Plan'da adı `liste_adi` olan arşivsiz listenin açık görevleri (yalnız kimlik + başlık).
    Veritabanı yoksa boş liste."""
    from app.db.connection import get_pool
    pool = await get_pool()
    if pool is None:
        return []
    async with pool.acquire() as c:
        rows = await c.fetch(
            "SELECT t.id::text AS id, t.title AS baslik FROM todo_tasks t "
            "JOIN todo_lists l ON l.id = t.list_id "
            "WHERE lower(l.name) = lower($1) AND NOT l.is_archived AND NOT t.is_archived "
            "AND t.completed_at IS NULL AND t.deleted_at IS NULL "
            "ORDER BY t.created_at LIMIT 20", liste_adi)
    return [dict(r) for r in rows]


# ── motor ─────────────────────────────────────────────────────────────────

class OneriMotoru:
    """Bir tur: topla → süz (susturma, tavanlar) → `oner` ile yaz → bildir.

    oner(tur, ad, istek, gerekce=, kaynak=, kaynak_ref=, oncelik=, devam_gid=) → kayıt
    kuyruk_liste() → kuyruk kayıtları · gorev_liste() → görev `durum.json` kayıtları
    plan_oku(liste_adi) → async · gonder(baslik, govde, url) → async
    iz(olay, **ek) → olay günlüğü · kapali() → True ise tur hiçbir şey yazmaz."""

    def __init__(self, kok: Path, *, oner, kuyruk_liste, gorev_liste, plan_oku=None,
                 gonder=None, iz=None, kapali=None) -> None:
        self.kok = Path(kok)
        self.oner = oner
        self.kuyruk_liste = kuyruk_liste
        self.gorev_liste = gorev_liste
        self.plan_oku = plan_oku or plan_listesi_oku
        self.gonder = gonder or _bildirim.push_gonder
        self.iz = iz or (lambda olay, **ek: None)
        self.kapali = kapali or (lambda: False)
        self.defter = self.kok / ".kuyruk" / "onerici.json"

    def _defter_oku(self, gun: str) -> dict:
        try:
            v = json.loads(self.defter.read_text(encoding="utf-8"))
            if not isinstance(v, dict):
                raise ValueError("defter sözlük değil")
        except FileNotFoundError:
            v = {}
        except (OSError, ValueError):
            logger.error("[oneri] onerici.json okunamadı — bugün öneri yazılmıyor")
            return {"gun": gun, "yazilan": 10 ** 9, "bozuk": True}
        if v.get("gun") != gun:
            v = {"gun": gun, "yazilan": 0, "son_bildirim": v.get("son_bildirim")}
        return v

    def _defter_yaz(self, v: dict) -> None:
        if v.get("bozuk"):
            return
        self.defter.parent.mkdir(parents=True, exist_ok=True)
        gecici = self.defter.with_name(f".onerici.{os.getpid()}.tmp")
        gecici.write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
        os.replace(gecici, self.defter)

    @staticmethod
    def _susanlar(kayitlar: list[dict], simdi: float) -> set[str]:
        """Önerilmeyecek kaynak_ref'ler: kayıtlı olan her şey; reddedilen 7, düşen 1 gün sonra serbest."""
        out = set()
        for k in kayitlar:
            ref = k.get("kaynak_ref")
            if not ref:
                continue
            durum = k.get("durum")
            if durum == "reddedildi" and simdi - float(k.get("red_zaman") or simdi) >= RED_SUSMA:
                continue
            if durum == "dustu" and simdi - float(k.get("son_gecerlilik") or simdi) >= DUSME_SUSMA:
                continue
            out.add(ref)
        return out

    async def _topla(self, a: dict, simdi: float) -> list[Aday]:
        adaylar: list[Aday] = []
        gorevler = self.gorev_liste() if {"yarim", "rutin"} & set(a["kaynaklar"]) else []
        if "yarim" in a["kaynaklar"]:
            adaylar += yarim_adaylari(gorevler, simdi)
        if "plan" in a["kaynaklar"]:
            try:
                adaylar += plan_adaylari(await self.plan_oku(a["plan_liste"]))
            except Exception as e:
                logger.warning("[oneri] Plan okunamadı: %s", type(e).__name__)
        if "rutin" in a["kaynaklar"]:
            adaylar += rutin_adaylari(gorevler)
        return sorted(adaylar, key=lambda x: x.oncelik)

    async def tur(self) -> dict:
        simdi = _zaman()
        a = ayarlar()
        sonuc: dict = {"aday": 0, "yazilan": [], "atlanan": {}, "bildirim": 0}

        def atla(neden: str) -> None:
            sonuc["atlanan"][neden] = sonuc["atlanan"].get(neden, 0) + 1

        if not _kapi.pencerede_mi(simdi):
            atla("pencere")
            return sonuc
        if self.kapali():
            atla("tumunu_durdur")
            return sonuc
        v = self._defter_oku(_kapi.gun(simdi))
        kayitlar = self.kuyruk_liste()
        sus = self._susanlar(kayitlar, simdi)
        suren = {k.get("devam_gid") or k.get("gid") for k in kayitlar if k.get("durum") in _SURUYOR}
        acik = sum(1 for k in kayitlar if k.get("durum") in _ACIK)
        adaylar = await self._topla(a, simdi)
        sonuc["aday"] = len(adaylar)
        for ad in adaylar:
            if ad.kaynak_ref in sus or (ad.devam_gid and ad.devam_gid in suren):
                atla("susturuldu")
                continue
            if int(v.get("yazilan") or 0) >= a["gunluk"]:
                atla("gunluk")
                continue
            if acik >= ACIK_AZAMI:
                atla("acik")
                continue
            try:
                k = self.oner(ad.tur, ad.ad, ad.istek, gerekce=ad.gerekce, kaynak=ad.kaynak,
                              kaynak_ref=ad.kaynak_ref, oncelik=ad.oncelik, devam_gid=ad.devam_gid)
            except Exception as e:
                logger.warning("[oneri] %s yazılamadı: %s", ad.kaynak_ref, e)
                atla("yazilamadi")
                continue
            sus.add(ad.kaynak_ref)
            acik += 1
            v["yazilan"] = int(v.get("yazilan") or 0) + 1
            sonuc["yazilan"].append(k["id"])
        self._defter_yaz(v)
        if sonuc["yazilan"]:
            await self._bildir(sonuc, v, a, simdi)
        return sonuc

    async def _bildir(self, sonuc: dict, v: dict, a: dict, simdi: float) -> None:
        if not a["bildirim"]:
            self.iz("oneri_bildirim_yok", neden="kapali")
            return
        if _bildirim.sessiz_mi(datetime.fromtimestamp(simdi), a["sessiz"]):
            self.iz("oneri_bildirim_yok", neden="sessiz")
            return
        son = v.get("son_bildirim")
        if son and simdi - float(son) < a["aralik_sn"]:
            self.iz("oneri_bildirim_yok", neden="aralik")
            return
        n = len(sonuc["yazilan"])
        from app.mesajlar import M
        govde = M("atolye.oneri-cok", n=n) if n > 1 else M("atolye.oneri-tek")
        try:
            await self.gonder(_bildirim.baslik(), govde,
                              f"/ui/index.html#atolye-oneri={sonuc['yazilan'][0]}")
        except Exception as e:
            logger.warning("[oneri] bildirim gitmedi: %s", type(e).__name__)
            return
        v["son_bildirim"] = round(simdi, 3)
        self._defter_yaz(v)
        sonuc["bildirim"] = 1
        self.iz("oneri_bildirim", sayi=n)

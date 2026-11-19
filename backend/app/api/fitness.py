"""Fitnes API (v2) — beslenme, antrenman oturumu, şablon, geçmiş, oyun katmanı ve ayarlar.

Kapılar: önce özellik bayrağı (`FITNES` kapalı → 404, kayıtsız uçla aynı), sonra PLAN kapısı.
Depo: tek kaynak `services/fitness_store` (gömülü JSON). Postgres'li eski kurulumun v1 verisi
`init_fitness_db()`'de bir kez içeri alınır (bkz. fitness_store modül notu).

Yazma uçları yanıt döndükten SONRA olay üretir (`_arka_olay`): sayfa açılmasa da rekor/seviye
olayı doğar, bildirim gider. Hata yanıtı etkilemez.

Set "yapıldı" tek kural: `girildi` damgası ya da bitişte onay (`completed`). Şablondan gelen set
kullanıcı dokunana kadar SAYILMAZ.
"""
from __future__ import annotations

import logging
import math
import re
from datetime import date as _date
from datetime import datetime
from typing import Optional
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.todo import require_planner
from app.limiter import limiter
from app.mesajlar import M
from app.services import fitness_oyun as F
from app.services import fitness_store as depo
from app.services.fitnes_metin import t
from app.services.yetki import ozellik_kapisi

router = APIRouter(prefix="/api/fitness", tags=["fitness"],
                   dependencies=[Depends(ozellik_kapisi("fitnes")), Depends(require_planner)])
log = logging.getLogger(__name__)


# ── yardımcılar ───────────────────────────────────────────────────────────────

def _tarih(deger) -> Optional[_date]:
    """'YYYY-MM-DD' → date; boşsa None. Geçersiz metin 400 (kusur istekte, sunucuda değil)."""
    if deger is None or deger == "":
        return None
    if isinstance(deger, _date):
        return deger
    try:
        return _date.fromisoformat(str(deger)[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail=M("fitness.tarih-gecersiz", deger=str(deger)[:40]))


def _gun(deger) -> Optional[str]:
    d = _tarih(deger)
    return d.isoformat() if d else None


def _hata(kod: int, anahtar: str, **kw):
    raise HTTPException(status_code=kod, detail=t(f"hata.{anahtar}", **kw))


async def init_fitness_db() -> bool:
    """Depoyu kur; Postgres'te v1 verisi varsa ve depo boşsa bir kez içeri al. Dönüş: PG'den aktarıldı mı."""
    depo.get_config()
    try:
        from app.db.connection import get_pool
        p = await get_pool()
    except Exception:  # noqa: BLE001 — Postgres'siz kurulumun normali
        return False
    if p is None:
        return False
    try:
        async with p.acquire() as conn:
            var = await conn.fetchval("SELECT to_regclass('public.fitness_meals') IS NOT NULL")
            if not var:
                return False
            n = await depo.pg_ice_aktar(conn)
    except Exception as e:  # noqa: BLE001
        log.warning("Fitnes: Postgres v1 verisi içeri alınamadı: %s", e)
        return False
    if n:
        log.info("Fitnes: Postgres v1 verisinden %d kayıt gömülü depoya alındı", n)
    return bool(n)


async def _arka_olay():
    """Yazma ucundan sonra (yanıt gittikten sonra): olay üret + bildirimi ilet. Hata yutulur."""
    try:
        from app.services import fitnes_bildirim as B
        await B.uret_ve_ilet(depo.simdi())
    except Exception:  # noqa: BLE001
        log.exception("fitnes arka plan olay üretimi başarısız")


# ── modeller ──────────────────────────────────────────────────────────────────

class MealCreate(BaseModel):
    meal: str = "ara"
    name: str = Field(max_length=200)
    cal: float = 0
    protein: float = 0
    carb: float = 0
    fat: float = 0
    entry_date: Optional[str] = None


class ExerciseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    sets: list[dict] = Field(default_factory=list, max_length=50)
    session_date: Optional[str] = None
    oturum_adi: Optional[str] = Field(default=None, max_length=80)


class ExerciseSetsUpdate(BaseModel):
    # [{id?, reps, weight, completed, dokunuldu?, girildi?: null, drops?: [{kg, tekrar}]}]
    sets: list[dict] = Field(max_length=100)


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    exercises: list[dict] = Field(default_factory=list, max_length=30)


class ConfigUpdate(BaseModel):
    calGoal: Optional[int] = None
    proteinGoal: Optional[int] = None
    carbGoal: Optional[int] = None
    fatGoal: Optional[int] = None


# ── öğünler ───────────────────────────────────────────────────────────────────

@router.get("/meals")
async def list_meals(date: Optional[str] = None):
    return depo.list_meals(_gun(date))


@router.get("/meals/gunluk")
async def meals_gunluk(bitis: str, gun: int = 7):
    """`bitis` dahil son `gun` (1-62) günün toplamı — haftalık kalori çubuğu tek istekle."""
    return depo.meals_gunluk(_gun(bitis), max(1, min(int(gun), 62)))


@router.post("/meals", status_code=201)
async def create_meal(body: MealCreate, arka: BackgroundTasks):
    k = depo.create_meal(body.meal, body.name, body.cal, body.protein, body.carb, body.fat,
                         _gun(body.entry_date))
    arka.add_task(_arka_olay)
    return k


@router.delete("/meals/{meal_id}", status_code=204)
async def delete_meal(meal_id: str):
    if not depo.delete_meal(meal_id):
        raise HTTPException(status_code=404, detail=M("fitness.ogun-yok"))


# ── antrenman ─────────────────────────────────────────────────────────────────

def _gun_rekorlari(db: dict, gun: str) -> list[dict]:
    return [o.get("veri") or {} for o in db["olaylar"]
            if o.get("tur") in ("PR", "REKOR") and (o.get("veri") or {}).get("tarih") == gun]


def _rekor_mu(ad: str, rekorlar: list[dict]) -> bool:
    n, kod = F.normal_ad(ad or ""), F.hareket_kodu(ad or "")
    for v in rekorlar:
        if v.get("hareket"):
            if F.normal_ad(str(v["hareket"])) == n:
                return True
        elif kod is not None and v.get("kod") == kod:
            return True
    return False


@router.get("/workouts")
async def get_workout(date: Optional[str] = None):
    gun = _gun(date)
    w = depo.get_workout(gun)
    if w.get("id"):
        rek = _gun_rekorlari(depo.oku(), w["session_date"])
        for e in w["exercises"]:
            e["rekor"] = _rekor_mu(e["name"], rek)
    return w


@router.get("/workouts/en-iyi")
async def en_iyi_setler(once: Optional[str] = None, adlar: list[str] = Query(default=[])):
    """Her ad için YAPILMIŞ en iyi set {ad_kucuk: {kg, tekrar, tarih}}: en ağır kilo, eşitse çok tekrar,
    eşitse ilk tarih. Süreli harekette ("(sn)") en uzun süre, eşitse ağır kilo. `once` → o günden önce."""
    sinir = _gun(once)
    istenen = {a.lower() for a in adlar[:30] if a}
    if not istenen:
        return {}
    db = depo.oku()
    gunler = {w["id"]: w["session_date"] for w in db["workouts"]}
    ex = {e["id"]: e for e in db["exercises"] if (e.get("name") or "").lower() in istenen}
    adaylar: dict = {}
    for s in db["sets"]:
        e = ex.get(s.get("exercise_id"))
        if not e or not depo.yapildi_mi(s) or int(s.get("reps") or 0) <= 0:
            continue
        gun = gunler.get(e["workout_id"])
        if gun is None or (sinir and gun >= sinir):
            continue
        ad = e["name"].lower()
        kg, tk = float(s.get("weight") or 0), int(s.get("reps") or 0)
        anahtar = (tk, kg) if F.sureli_mi(e["name"]) else (kg, tk)
        eski = adaylar.get(ad)
        if eski is None or anahtar > eski[0] or (anahtar == eski[0] and gun < eski[1]["tarih"]):
            adaylar[ad] = (anahtar, {"kg": kg, "tekrar": tk, "tarih": gun})
    return {ad: v for ad, (_, v) in adaylar.items()}


@router.get("/workouts/onceki")
async def onceki_setler(once: str, adlar: list[str] = Query(default=[])):
    adlar = [a for a in adlar if a][:30]
    return depo.onceki_setler(_gun(once), adlar) if adlar else {}


def _set_alanlari(s: dict) -> tuple[int, float, bool]:
    try:
        reps, weight = int(s.get("reps", 0)), float(s.get("weight", 0))
    except (TypeError, ValueError):
        _hata(400, "set-sayi")
    if not math.isfinite(weight) or abs(weight) > 10000 or not 0 <= reps <= 9999:
        _hata(400, "set-aralik")
    return reps, weight, bool(s.get("completed", False))


def _drop_alanlari(s: dict) -> Optional[list]:
    """Gövdede `drops` yoksa anahtar hiç eklenmez (eski istemci silmesin). Boş/None → kaldır."""
    ham = s["drops"]
    if ham is None:
        return None
    if not isinstance(ham, list) or len(ham) > F.DROP_EN_COK:
        _hata(400, "drop-liste", n=F.DROP_EN_COK)
    temiz = []
    for d in ham:
        try:
            kg, tk = float(d["kg"]), d["tekrar"]
        except (TypeError, ValueError, KeyError):
            _hata(400, "drop-bicim")
        if isinstance(tk, bool) or not isinstance(tk, (int, float)) or tk != int(tk):
            _hata(400, "drop-tekrar")
        if not math.isfinite(kg) or not 0 <= kg <= 2000 or not 0 <= int(tk) <= 999:
            _hata(400, "drop-aralik")
        temiz.append({"kg": round(kg, 2), "tekrar": int(tk)})
    return temiz or None


@router.post("/workouts/exercise", status_code=201)
async def add_exercise(body: ExerciseCreate):
    sets = []
    for s in body.sets:
        reps, weight, tamam = _set_alanlari(s if isinstance(s, dict) else {})
        sets.append({"reps": reps, "weight": weight, "completed": tamam})
    return depo.add_exercise(body.name, sets, _gun(body.session_date), body.oturum_adi)


@router.put("/workouts/exercise/{exercise_id}/sets")
async def update_exercise_sets(exercise_id: UUID, body: ExerciseSetsUpdate, arka: BackgroundTasks):
    """Upsert: id'li set güncellenir, id'siz eklenir, listede olmayan silinir. `dokunuldu: true` →
    girildi damgası (bir kez); açık `"girildi": null` damgayı kaldırır (GERİ AL)."""
    temiz = []
    for s in body.sets:
        if not isinstance(s, dict):
            _hata(400, "set-nesne")
        reps, weight, tamam = _set_alanlari(s)
        k = {"reps": reps, "weight": weight, "completed": tamam, "dokunuldu": bool(s.get("dokunuldu"))}
        if s.get("id"):
            try:
                k["id"] = str(UUID(str(s["id"])))
            except ValueError:
                _hata(400, "set-id")
        if "girildi" in s and s["girildi"] is None:
            k["girildi"] = None
        if "drops" in s:
            k["drops"] = _drop_alanlari(s)
        temiz.append(k)
    sonuc = depo.update_exercise_sets(str(exercise_id), temiz)
    if sonuc is None:
        raise HTTPException(status_code=404, detail=M("fitness.egzersiz-yok"))
    arka.add_task(_arka_olay)
    return sonuc


@router.delete("/workouts/exercise/{exercise_id}", status_code=204)
async def delete_exercise(exercise_id: str):
    if not depo.delete_exercise(exercise_id):
        raise HTTPException(status_code=404, detail=M("fitness.egzersiz-yok"))


# ── antrenman oturumu: başla / bitir / aç ─────────────────────────────────────

class BitirGovde(BaseModel):
    onayla: list[UUID] = Field(default_factory=list, max_length=500)  # "bunu da yaptım"


@router.post("/workouts/{tarih}/basla")
async def antrenman_basla(tarih: str):
    """Süre sunucuda tutulur (cihazlar arası görünür). İdempotent: ilk başlangıç korunur."""
    gun = _gun(tarih)
    with depo.islem() as db:
        w = depo.workout_kur(db, gun)
        if not w.get("baslangic"):
            w["baslangic"] = depo._simdi()
        return {"baslangic": w["baslangic"]}


def _sure(w: dict) -> Optional[int]:
    try:
        b, e = datetime.fromisoformat(w["baslangic"]), datetime.fromisoformat(w["bitis"])
    except (TypeError, ValueError, KeyError):
        return None
    return max(0, round((e - b).total_seconds()))


@router.post("/workouts/{tarih}/bitir")
async def antrenman_bitir(tarih: str, arka: BackgroundTasks, body: BitirGovde = Body(default_factory=BitirGovde)):
    """Bitiş ekranının tek kaynağı. Dokunulmamış set SAYILMAZ; yalnız `onayla`'daki setler completed +
    girildi alır. xp_kazanc = onayın etkisi, xp_gun = bu günün toplam katkısı. olaylar önizlemedir."""
    gun_d = _tarih(tarih)
    gun = gun_d.isoformat()
    bugun = depo.bugun()
    onay = {str(x) for x in body.onayla}
    with depo.islem() as db:
        w = depo.workout_bul(db, gun)
        if not w:
            _hata(404, "gun-yok")
        zirve = F.zirve(db)
        once = F.durum_hesapla(F.veri_oku(db), bugun, zirve)
        ex_idler = {e["id"]: e for e in depo.egzersizler(db, w["id"])}
        for s in db["sets"]:
            if s.get("exercise_id") in ex_idler and s["id"] in onay:
                s["completed"] = True
                s["girildi"] = s.get("girildi") or depo._simdi()
        if not w.get("bitis"):
            w["bitis"] = depo._simdi()
        veri = F.veri_oku(db)
        sonra = F.durum_hesapla(veri, bugun, zirve)
        gunsuz = F.durum_hesapla({**veri, "setler": [s for s in veri["setler"] if s["tarih"] != gun_d]}, bugun, zirve)
        satirlar = [(e, s) for e in ex_idler.values() for s in depo.setler(db, e["id"])]
        zaman = dict(w)
    yapilan = [(e, s) for e, s in satirlar if depo.yapildi_mi(s)]
    eski = {o["anahtar"] for o in gunsuz["olaylar"]}
    olaylar = [{"anahtar": o["anahtar"], "tur": o["tur"], "metin": o["metin"]}
               for o in sonra["olaylar"] if o["anahtar"] not in eski]
    arka.add_task(_arka_olay)
    return {
        "bitis": zaman["bitis"], "sure_sn": _sure(zaman),
        "yapilan_set": len(yapilan),
        "tonaj": round(sum(F.set_tonaj(e["name"], s["weight"], s["reps"], s.get("drops")) for e, s in yapilan), 1),
        "xp_kazanc": round(sonra["xp_toplam"] - once["xp_toplam"], 1),
        "xp_gun": round(sonra["xp_toplam"] - gunsuz["xp_toplam"], 1),
        "yeni_pr": [o for o in olaylar if o["tur"] in ("PR", "REKOR")],
        "olaylar": olaylar,
        "dokunulmamis": [{"id": s["id"], "egzersiz": e["name"], "reps": s["reps"], "weight": float(s["weight"])}
                         for e, s in satirlar if not depo.yapildi_mi(s)],
    }


@router.post("/workouts/{tarih}/ac")
async def antrenman_ac(tarih: str):
    """Bitmiş günü yeniden açar (bitis = None)."""
    gun = _gun(tarih)
    with depo.islem() as db:
        w = depo.workout_bul(db, gun)
        if not w:
            _hata(404, "gun-yok")
        w["bitis"] = None
    return {"bitis": None}


# ── geçmiş takvimi ────────────────────────────────────────────────────────────

@router.get("/workouts/ozet")
async def workouts_ozet(bas: str, bit: str):
    """[bas, bit] (≤ 62 gün) aralığında seti olan her gün: set/yapılan sayısı, tonaj, xp (set XP'si), pr, süre."""
    b0, b1 = _tarih(bas), _tarih(bit)
    if b0 is None or b1 is None or b1 < b0 or (b1 - b0).days + 1 > 62:
        _hata(400, "aralik")
    db = depo.oku()
    pr: dict = {}
    for o in db["olaylar"]:
        g = (o.get("veri") or {}).get("tarih")
        if o.get("tur") in ("PR", "REKOR") and g and b0.isoformat() <= g <= b1.isoformat():
            pr[g] = pr.get(g, 0) + 1
    sonuc = []
    for w in sorted(db["workouts"], key=lambda w: w["session_date"]):
        if not b0.isoformat() <= w["session_date"] <= b1.isoformat():
            continue
        g = {"tarih": w["session_date"], "ad": w.get("notes") or None, "set": 0, "yapilan": 0, "tonaj": 0.0,
             "xp": 0.0, "pr": pr.get(w["session_date"], 0), "sure_sn": _sure(w)}
        for e in depo.egzersizler(db, w["id"]):
            for s in depo.setler(db, e["id"]):
                g["set"] += 1
                if depo.yapildi_mi(s):
                    g["yapilan"] += 1
                    g["tonaj"] += F.set_tonaj(e["name"], s["weight"], s["reps"], s.get("drops"))
                    g["xp"] += F.set_xp(F.xp_kilo(e["name"], s["weight"]), int(s["reps"]), True)
        if g["set"]:
            g["tonaj"], g["xp"] = round(g["tonaj"], 1), round(g["xp"], 1)
            sonuc.append(g)
    return sonuc


# ── şablonlar ─────────────────────────────────────────────────────────────────

_HAZIR = re.compile(r"^hazir-[a-z0-9-]{1,40}$")
_ARALIK = re.compile(r"^\d{1,3}(-\d{1,3})?$")


def _hazir_id(slug: str) -> str:
    """Hazır şablonun kararlı kimliği. Rastgele OLMAMALI: geçmişteki "son yapılma" buna bağlı."""
    return str(uuid5(NAMESPACE_URL, f"yuki-fitnes-hazir:{slug}"))


def _son_yapilma(db: dict, sablon_idler: set) -> dict:
    """sablon_id → o şablondan yüklenip en az bir seti YAPILMIŞ en son gün."""
    gunler = {w["id"]: w["session_date"] for w in db["workouts"]}
    yapilan_ex = {s["exercise_id"] for s in db["sets"] if depo.yapildi_mi(s)}
    son: dict = {}
    for e in db["exercises"]:
        sid = e.get("sablon_id")
        if sid in sablon_idler and e["id"] in yapilan_ex:
            g = gunler.get(e["workout_id"])
            if g and g > son.get(sid, ""):
                son[sid] = g
    return son


@router.get("/templates")
async def list_templates():
    db = depo.oku()
    liste = depo.list_templates()
    son = _son_yapilma(db, {x["id"] for x in liste})
    return [{**x, "son_yapilma": son.get(x["id"])} for x in liste]


@router.get("/templates/son-yapilma")
async def hazir_son_yapilma(hazir: list[str] = Query(default=[])):
    """Hazır şablonlar (ön yüz sabiti) depoda yok: `?hazir=<slug>` → {"hazir-<slug>": ISO|null}."""
    sluglar = [h for h in hazir if _HAZIR.match(f"hazir-{h}")][:30]
    if not sluglar:
        return {}
    son = _son_yapilma(depo.oku(), {_hazir_id(h) for h in sluglar})
    return {f"hazir-{h}": son.get(_hazir_id(h)) for h in sluglar}


@router.post("/templates", status_code=201)
async def create_template(body: TemplateCreate):
    return depo.create_template(body.name, body.exercises)


class SablonSet(BaseModel):
    reps: int = Field(ge=0, le=999)
    weight: float = Field(ge=0, le=2000)


class SablonEgzersiz(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    aralik: Optional[str] = Field(default=None, max_length=7)
    sets: list[SablonSet] = Field(default_factory=list, max_length=20)


class SablonDuzenle(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    exercises: list[SablonEgzersiz] = Field(min_length=1, max_length=30)


def _sablon_egzersizleri(body: SablonDuzenle) -> list[dict]:
    cikti = []
    for e in body.exercises:
        ad = e.name.strip()
        if not ad:
            _hata(400, "egzersiz-ad")
        if not e.sets:
            _hata(400, "set-yok", ad=ad)
        ex = {"name": ad, "sets": [{"reps": s.reps, "weight": round(s.weight, 2)} for s in e.sets]}
        aralik = (e.aralik or "").strip()
        if aralik:
            if not _ARALIK.match(aralik):
                _hata(400, "aralik-bicim", ad=ad)
            ex["aralik"] = aralik
        cikti.append(ex)
    return cikti


@router.put("/templates/{sablon}")
async def sablon_duzenle(sablon: str, body: SablonDuzenle):
    """Şablonu bütünüyle değiştirir. `{sablon}` = kendi şablonunun UUID'si (yoksa 404) ya da `hazir-<slug>`
    → hazırın KENDİ KOPYASI (kararlı id, varsa üzerine). Kopya silinince hazır geri gelir."""
    ad = body.name.strip()
    if not ad:
        _hata(400, "sablon-ad")
    ex = _sablon_egzersizleri(body)
    with depo.islem() as db:
        try:
            sid = str(UUID(sablon))
        except ValueError:
            if not _HAZIR.match(sablon):
                _hata(400, "sablon-kimlik")
            sid = _hazir_id(sablon[6:])
            kayit = next((x for x in db["templates"] if x["id"] == sid), None)
            if kayit is None:
                kayit = {"id": sid, "created_at": depo._simdi()}
                db["templates"].append(kayit)
            kayit.update(name=ad, exercises=ex, hazir_slug=sablon[6:])
        else:
            kayit = next((x for x in db["templates"] if x["id"] == sid), None)
            if kayit is None:
                raise HTTPException(status_code=404, detail=M("fitness.sablon-yok"))
            kayit.update(name=ad, exercises=ex)
        son = _son_yapilma(db, {sid})
        return {**kayit, "son_yapilma": son.get(sid)}


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(template_id: str):
    if not depo.delete_template(template_id):
        raise HTTPException(status_code=404, detail=M("fitness.sablon-yok"))


class SablonYukle(BaseModel):
    """Yalnız hazır (ön yüz sabiti) şablonlar için; depodaki şablon gövdesiz yüklenir."""
    ad: Optional[str] = Field(default=None, max_length=80)
    exercises: list[dict] = Field(default_factory=list, max_length=30)


@router.post("/templates/{sablon}/yukle", status_code=201)
async def sablon_yukle(sablon: str, tarih: Optional[str] = None, yine: int = 0,
                       body: Optional[SablonYukle] = None):
    """Şablonu güne TEK istekte yükler. Aynı gün aynı şablon → 409 {zaten: n}; `yine=1` bilerek tekrar.
    Yüklenen setler öneridir: kullanıcı dokunana kadar sayılmaz."""
    try:
        sid, hazir = str(UUID(sablon)), False
    except ValueError:
        if not _HAZIR.match(sablon):
            _hata(400, "sablon-kimlik")
        if body is None or not body.exercises:
            _hata(400, "hazir-govde")
        sid, hazir = _hazir_id(sablon[6:]), True
    gun = _gun(tarih) or depo._bugun()
    with depo.islem() as db:
        if hazir:
            ad, exercises = body.ad, body.exercises
        else:
            kayit = next((x for x in db["templates"] if x["id"] == sid), None)
            if kayit is None:
                raise HTTPException(status_code=404, detail=M("fitness.sablon-yok"))
            ad, exercises = kayit["name"], kayit.get("exercises") or []
        w = depo.workout_kur(db, gun)
        zaten = sum(1 for e in depo.egzersizler(db, w["id"]) if e.get("sablon_id") == sid)
        if zaten and not yine:
            raise HTTPException(status_code=409, detail={"zaten": zaten})
        sonuc = []
        for ex in exercises:
            if not isinstance(ex, dict) or not str(ex.get("name") or "").strip():
                _hata(400, "egzersiz-ad")
            setler = []
            for s in (ex.get("sets") or [])[:20]:
                reps, weight, _ = _set_alanlari(s if isinstance(s, dict) else {})
                setler.append({"reps": reps, "weight": weight, "completed": False})
            sonuc.append(depo.egzersiz_ekle(db, gun, str(ex["name"]), setler, ad, sablon_id=sid))
        return {"workout_id": w["id"], "sablon_id": sid, "exercises": sonuc}


# ── hedefler + favori öğünler ─────────────────────────────────────────────────

@router.get("/config")
async def get_config():
    return depo.get_config()


@router.put("/config")
async def update_config(body: ConfigUpdate):
    return depo.update_config(**body.model_dump())


class FavoriOgun(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    meal: str = "ara"
    cal: float = 0
    protein: float = 0
    carb: float = 0
    fat: float = 0


class FavoriListe(BaseModel):
    favoriler: list[FavoriOgun] = Field(default_factory=list, max_length=12)


@router.get("/favoriler")
async def favori_ogunler():
    v = depo.cfg_oku("favoriOgunler")
    return v if isinstance(v, list) else []


@router.put("/favoriler")
async def favori_ogunler_yaz(body: FavoriListe):
    veri = [f.model_dump() for f in body.favoriler]
    depo.cfg_yaz("favoriOgunler", veri)
    return veri


# ── oyun katmanı ──────────────────────────────────────────────────────────────

@router.get("/durum")
async def oyun_durum():
    """Seviye, XP, stat'lar, lig, görevler, beceriler, bekleyen olaylar. ⚠ Yan etkili: yeni olayları yazar."""
    simdi = depo.simdi()
    sonuc = F.durum(simdi.date(), simdi)
    try:
        from app.services import fitnes_bildirim as B
        sonuc["bugun_kalan"] = max(0, B.GUNLUK_TAVAN - B.bugun_sayilan(depo.oku(), simdi.date()))
    except ImportError:
        pass
    return sonuc


@router.post("/olaylar/{olay_id}/goruldu", status_code=204)
async def olay_goruldu(olay_id: str):
    with depo.islem() as db:
        o = next((o for o in db["olaylar"] if o.get("id") == olay_id), None)
        if o is None:
            _hata(404, "olay-yok")
        o["goruldu"] = True


@router.get("/oyun/haftalik")
async def oyun_haftalik(hafta: str):
    try:
        return F.haftalik_ozet(_tarih(hafta))
    except ValueError:
        _hata(400, "pazartesi")


class UnvanSec(BaseModel):
    kod: Optional[str] = Field(default=None, max_length=60)


@router.put("/oyun/unvan")
async def unvan_sec(body: UnvanSec):
    """Seçili unvan tektir; kazanılmamış unvan seçilemez (404). kod=null seçimi kaldırır."""
    with depo.islem() as db:
        if body.kod is not None and body.kod not in db["unvanlar"]:
            _hata(404, "unvan-yok")
        for kod, u in db["unvanlar"].items():
            u["secili"] = kod == body.kod
    return {"secili": body.kod}


class HaftaTuru(BaseModel):
    hafta: str
    tur: Optional[str] = None  # deload | dondurma | None (sil)


@router.get("/hafta-turu")
async def hafta_turu_liste():
    return [{"hafta": h, "tur": x} for h, x in sorted((depo.oku().get("hafta_turu") or {}).items())]


@router.put("/hafta-turu")
async def hafta_turu_yaz(body: HaftaTuru):
    h = _tarih(body.hafta)
    if h is None or h.weekday() != 0:
        _hata(400, "pazartesi")
    if body.tur not in (None, "deload", "dondurma"):
        _hata(400, "hafta-tur")
    with depo.islem() as db:
        if body.tur is None:
            db["hafta_turu"].pop(h.isoformat(), None)
            return {"hafta": h.isoformat(), "tur": None}
        mevcut = {}
        for k, v in db["hafta_turu"].items():
            try:
                mevcut[_date.fromisoformat(k)] = v
            except ValueError:
                continue
        mevcut.pop(h, None)
        sebep = F.hafta_turu_kontrol(mevcut, h, body.tur)
        if sebep:
            raise HTTPException(status_code=400, detail=sebep)
        db["hafta_turu"][h.isoformat()] = body.tur
    return {"hafta": h.isoformat(), "tur": body.tur}


# ── JSON ayarlar: bildirim + hareket ──────────────────────────────────────────
# Sunucu temizler: sınır dışı sayı kırpılır, bilinmeyen anahtar atılır, bozuk tür kayıtlı değerde kalır
# (400 değil — istemcinin eski önbelleği kırılmasın). PUT kısmidir; dönüş her zaman tam nesne.

def _kirp(v, alt: float, ust: float, yedek: float) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return yedek
    return round(min(ust, max(alt, float(v))), 2)


BILDIRIM_VARSAYILAN = {"push": True, "sessiz": [23, 8], "hatirlatma": True}


def bildirim_temizle(ham, taban: dict | None = None) -> dict:
    v = {**BILDIRIM_VARSAYILAN, **(taban or {})}
    v["sessiz"] = list(v["sessiz"])
    if not isinstance(ham, dict):
        return v
    for k in ("push", "hatirlatma"):
        if isinstance(ham.get(k), bool):
            v[k] = ham[k]
    s = ham.get("sessiz")
    if (isinstance(s, list) and len(s) == 2
            and all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 23 for x in s)):
        v["sessiz"] = list(s)
    return {k: v[k] for k in BILDIRIM_VARSAYILAN}


@router.get("/bildirim-ayar")
async def bildirim_ayar_oku():
    return bildirim_temizle(depo.cfg_oku("bildirim"))


@router.put("/bildirim-ayar")
async def bildirim_ayar_yaz(body: dict = Body(...)):
    with depo.islem() as db:
        yeni = bildirim_temizle(body, bildirim_temizle(depo.cfg_oku("bildirim", db)))
        depo.cfg_yaz("bildirim", yeni, db)
    return yeni


# Hareket ayarı: an başına GÖRELİ hız (süreler değişince eskimez) + eğri + 3 kademe yoğunluk.
HAREKET_ANLAR = ("seviye", "rekor", "lig", "beceri", "evrim")
HAREKET_EGRILER = ("yumusak", "keskin", "yorunge", "dogrusal")
HAREKET_YOGUNLUK = ("tam", "sade", "kapali")
HAREKET_HIZ = (0.5, 2.0)
HAREKET_AN_HIZ = (0.25, 4.0)


def hareket_varsayilan() -> dict:
    return {"surum": 1, "hiz": 1.0, "yogunluk": "tam",
            "anlar": {a: {"acik": True, "hiz": 1.0, "egri": "yumusak"} for a in HAREKET_ANLAR}}


def hareket_temizle(ham, taban: dict | None = None) -> dict:
    v = hareket_varsayilan()
    if isinstance(taban, dict):  # kayıtlı değer de temizlenerek taban olur (bozuk kayıt sızmasın)
        v = hareket_temizle(taban)
    v["surum"] = 1
    if not isinstance(ham, dict):
        return v
    if "hiz" in ham:
        v["hiz"] = _kirp(ham["hiz"], *HAREKET_HIZ, v["hiz"])
    if ham.get("yogunluk") in HAREKET_YOGUNLUK:
        v["yogunluk"] = ham["yogunluk"]
    anlar = ham.get("anlar")
    if isinstance(anlar, dict):
        for a in HAREKET_ANLAR:
            x = anlar.get(a)
            if not isinstance(x, dict):
                continue
            if isinstance(x.get("acik"), bool):
                v["anlar"][a]["acik"] = x["acik"]
            if "hiz" in x:
                v["anlar"][a]["hiz"] = _kirp(x["hiz"], *HAREKET_AN_HIZ, v["anlar"][a]["hiz"])
            if x.get("egri") in HAREKET_EGRILER:
                v["anlar"][a]["egri"] = x["egri"]
    return v


@router.get("/ayar/hareket")
async def hareket_ayar_oku():
    return hareket_temizle(depo.cfg_oku("hareket"))


@router.put("/ayar/hareket")
async def hareket_ayar_yaz(body: dict = Body(...)):
    with depo.islem() as db:
        yeni = hareket_temizle(body, depo.cfg_oku("hareket", db))
        depo.cfg_yaz("hareket", yeni, db)
    return yeni


# ── özet (Yuki aracı + ön yüz) ────────────────────────────────────────────────

@router.get("/summary")
@limiter.limit("100/minute")
async def get_summary(request: Request):
    return depo.get_summary()

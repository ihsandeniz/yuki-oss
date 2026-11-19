"""Fitnes gömülü deposu (v2) — tek kaynak: `DATA_DIR/fitness_store.json`.

Neden tek kaynak (2026-11-12, G3 Fitnes v2):
Fitnes v1'de her uç iki dallıydı (Postgres varsa SQL, yoksa bu JSON). v2'de uç sayısı 15'ten 33'e
çıktı, oyun katmanı (olay günlüğü, beceri, unvan, hafta türü) geldi. Her şeyi iki depoda eşit
tutmak, iki depoda iki ayrı kusur demekti. Paketli kurulumda Postgres zaten yok. Bu yüzden v2
yalnız bu depoyu kullanır. Postgres'li eski kurulumdaki v1 verisi kaybolmasın diye açılışta
`pg_ice_aktar()` ile BİR KEZ içeri alınır (yalnız depo boşken).

Yapı (şema 2):
    meals · workouts · exercises · sets · templates · config   (v1'den)
    olaylar (tekil `anahtar`) · hafta_turu {pazartesi: tur} · beceriler {kod: {durum, zaman}}
    unvanlar {kod: {kazanildi, secili}}

Her değişiklik `islem()` içinde yapılır: tek kilit, iş bitince tek atomik yazma. İş yarıda hata
verirse dosyaya hiçbir şey yazılmaz.
"""
from __future__ import annotations

import copy
import json
import logging
import math
import os
import threading
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any, Iterator, Optional

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

_STORE_FILE = DATA_DIR / "fitness_store.json"
_lock = threading.RLock()
_SCHEMA_VERSION = 2

MEALS = ("kahvalti", "ogle", "aksam", "ara")
VARSAYILAN_CONFIG = {"calGoal": 2000, "proteinGoal": 150, "carbGoal": 200, "fatGoal": 65}
VARSAYILAN_PLAN = "1,3,5"   # antrenman günleri (ISO hafta günü)
DROP_EN_COK = 10

# Kayıt başına v2'de eklenen alanlar ve varsayılanları — eski dosya açılınca doldurulur.
_V2_ALANLAR = {
    "workouts": {"notes": None, "baslangic": None, "bitis": None},
    "exercises": {"sablon_id": None},
    "sets": {"girildi": None, "drops": None, "created_at": None},
    "templates": {"hazir_slug": None},
}


# ══════════════════════════════════════════════════════════════════════════════
# Zaman — kullanıcının günü (SCHEDULER_TIMEZONE), sunucu saatinin değil
# ══════════════════════════════════════════════════════════════════════════════

def _tz():
    from zoneinfo import ZoneInfo
    from app import config
    try:
        return ZoneInfo(config.SCHEDULER_TIMEZONE)
    except Exception:  # noqa: BLE001 — bozuk ayar günü kaydırmasın, UTC'ye düşsün
        return ZoneInfo("UTC")


def simdi() -> datetime:
    return datetime.now(_tz())


def bugun() -> date:
    return simdi().date()


def _simdi() -> str:
    return simdi().isoformat()


def _bugun() -> str:
    return bugun().isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


def _sayi(v: Any, varsayilan: float = 0.0) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return varsayilan
    return f if math.isfinite(f) else varsayilan


# ══════════════════════════════════════════════════════════════════════════════
# Dosya katmanı
# ══════════════════════════════════════════════════════════════════════════════

def _empty_db() -> dict:
    return {
        "_schema": _SCHEMA_VERSION,
        "meals": [], "workouts": [], "exercises": [], "sets": [], "templates": [],
        "config": {**VARSAYILAN_CONFIG, "antrenmanGunleri": VARSAYILAN_PLAN},
        "olaylar": [], "hafta_turu": {}, "beceriler": {}, "unvanlar": {},
    }


def _yukselt(db: dict) -> dict:
    """Eksik anahtar/alan toleransı + şema 1 → 2. Var olan değere dokunmaz."""
    for k, v in _empty_db().items():
        if k == "config":
            cfg = db.setdefault("config", {})
            if not isinstance(cfg, dict):
                db["config"] = cfg = {}
            for ck, cv in v.items():
                cfg.setdefault(ck, cv)
        else:
            db.setdefault(k, v)
    for tablo, alanlar in _V2_ALANLAR.items():
        for kayit in db[tablo]:
            for alan, varsayilan in alanlar.items():
                kayit.setdefault(alan, varsayilan)
    db["_schema"] = _SCHEMA_VERSION
    return db


def _load() -> dict:
    with _lock:
        if not _STORE_FILE.exists():
            db = _empty_db()
            _save(db)
            return db
        try:
            db = json.loads(_STORE_FILE.read_text(encoding="utf-8"))
            if not isinstance(db, dict):
                raise ValueError("kök nesne değil")
        except (ValueError, OSError) as e:
            # Bozuk dosyayı SİLME — yedekle. Kullanıcının verisi olabilir.
            logger.error("fitness_store.json okunamadı (%s) — .bozuk olarak yedeklendi", e)
            try:
                _STORE_FILE.replace(_STORE_FILE.with_suffix(".json.bozuk"))
            except OSError:
                pass
            db = _empty_db()
            _save(db)
            return db
        return _yukselt(db)


def _save(db: dict) -> None:
    """Atomik yazma — yarım dosya bırakmaz."""
    with _lock:
        _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STORE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(db, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        os.replace(tmp, _STORE_FILE)


@contextmanager
def islem() -> Iterator[dict]:
    """Yazma işlemi: kilit + oku + (hata yoksa) yaz. İç içe çağrı aynı nesneyi paylaşır."""
    with _lock:
        acik = getattr(_yerel, "db", None)
        if acik is not None:
            yield acik
            return
        db = _load()
        _yerel.db = db
        try:
            yield db
        except BaseException:
            _yerel.db = None
            raise
        _yerel.db = None
        _save(db)


_yerel = threading.local()


def oku() -> dict:
    """Salt okuma kopyası (açık bir işlem varsa onun güncel hali)."""
    with _lock:
        acik = getattr(_yerel, "db", None)
        return copy.deepcopy(acik) if acik is not None else _load()


# ══════════════════════════════════════════════════════════════════════════════
# Yardımcılar
# ══════════════════════════════════════════════════════════════════════════════

def drop_listesi(ham) -> list:
    """drops → [{kg, tekrar}]; bozuk öğe atlanır, en çok DROP_EN_COK."""
    if not isinstance(ham, list):
        return []
    sonuc = []
    for d in ham[:DROP_EN_COK]:
        try:
            kg, tk = float(d["kg"]), int(d["tekrar"])
        except (TypeError, ValueError, KeyError):
            continue
        if math.isfinite(kg) and kg >= 0 and tk >= 0:
            sonuc.append({"kg": kg, "tekrar": tk})
    return sonuc


def set_json(s: dict) -> dict:
    return {**s, "drops": drop_listesi(s.get("drops"))}


def yapildi_mi(s: dict) -> bool:
    """Tek kural: kullanıcı değere dokundu (girildi) ya da bitişte onayladı (completed).
    Şablondan gelip dokunulmamış set — kilosu ne olursa olsun — yapılmadı sayılır."""
    return s.get("girildi") is not None or bool(s.get("completed"))


def workout_bul(db: dict, gun: str) -> Optional[dict]:
    return next((w for w in db["workouts"] if w.get("session_date") == gun), None)


def workout_kur(db: dict, gun: str) -> dict:
    w = workout_bul(db, gun)
    if w:
        return w
    w = {"id": _uid(), "session_date": gun, "notes": None, "baslangic": None, "bitis": None,
         "created_at": _simdi()}
    db["workouts"].append(w)
    return w


def egzersizler(db: dict, workout_id: str) -> list[dict]:
    return sorted((e for e in db["exercises"] if e.get("workout_id") == workout_id),
                  key=lambda e: e.get("position", 0))


def setler(db: dict, exercise_id: str) -> list[dict]:
    return sorted((s for s in db["sets"] if s.get("exercise_id") == exercise_id),
                  key=lambda s: s.get("position", 0))


def _yeni_set(exercise_id: str, reps: int, weight: float, completed: bool, pos: int,
              girildi: Optional[str] = None, drops: Optional[list] = None) -> dict:
    return {"id": _uid(), "exercise_id": exercise_id, "reps": int(reps), "weight": float(weight),
            "completed": bool(completed), "position": float(pos), "created_at": _simdi(),
            "girildi": girildi, "drops": drops or None}


def egzersiz_ekle(db: dict, gun: str, ad: str, sets: list[dict], oturum_adi: Optional[str] = None,
                  sablon_id: Optional[str] = None) -> dict:
    w = workout_kur(db, gun)
    mevcut = egzersizler(db, w["id"])
    # Oturum adı günün İLK egzersiziyle gelir: gün boşsa bu ekleme başlığı yeniden belirler (şablonsuzsa
    # siler) — yoksa şablonu silinip boşalan günde eski ad kalıyordu. Dolu günde yalnız ad boşsa yazılır.
    if not mevcut:
        w["notes"] = str(oturum_adi)[:80] if oturum_adi else None
    elif oturum_adi and not w.get("notes"):
        w["notes"] = str(oturum_adi)[:80]
    eg = {"id": _uid(), "workout_id": w["id"], "name": (ad or "").strip()[:120],
          "position": max([e.get("position", 0) for e in mevcut], default=0) + 1,
          "sablon_id": sablon_id, "created_at": _simdi()}
    db["exercises"].append(eg)
    yeni = []
    for i, s in enumerate(sets or []):
        k = _yeni_set(eg["id"], int(_sayi(s.get("reps"))), _sayi(s.get("weight")),
                      bool(s.get("completed", False)), i)
        db["sets"].append(k)
        yeni.append(k)
    return {**eg, "sets": [set_json(s) for s in yeni]}


# ══════════════════════════════════════════════════════════════════════════════
# Öğünler
# ══════════════════════════════════════════════════════════════════════════════

def list_meals(entry_date: Optional[str] = None) -> list[dict]:
    hedef = entry_date or _bugun()
    return sorted((m for m in oku()["meals"] if m.get("entry_date") == hedef),
                  key=lambda m: m.get("created_at", ""))


def meals_gunluk(bitis: str, gun: int = 7) -> list[dict]:
    """`bitis` dahil son `gun` günün toplamı; kaydı olmayan gün listede YOK (boşluğu arayüz doldurur)."""
    son = date.fromisoformat(bitis)
    ilk = str(son - timedelta(days=gun - 1))
    toplam: dict[str, dict] = {}
    for m in oku()["meals"]:
        t = str(m.get("entry_date", ""))
        if not (ilk <= t <= bitis):
            continue
        g = toplam.setdefault(t, {"tarih": t, "cal": 0.0, "protein": 0.0, "carb": 0.0, "fat": 0.0})
        for alan in ("cal", "protein", "carb", "fat"):
            g[alan] += _sayi(m.get(alan))
    return [toplam[t] for t in sorted(toplam)]


def create_meal(meal: str, name: str, cal: float = 0, protein: float = 0, carb: float = 0,
                fat: float = 0, entry_date: Optional[str] = None) -> dict:
    with islem() as db:
        kayit = {"id": _uid(), "entry_date": entry_date or _bugun(),
                 "meal": meal if meal in MEALS else "ara", "name": (name or "").strip()[:200],
                 "cal": _sayi(cal), "protein": _sayi(protein), "carb": _sayi(carb), "fat": _sayi(fat),
                 "created_at": _simdi()}
        db["meals"].append(kayit)
        return kayit


def delete_meal(meal_id: str) -> bool:
    with islem() as db:
        once = len(db["meals"])
        db["meals"] = [m for m in db["meals"] if m.get("id") != meal_id]
        return len(db["meals"]) != once


# ══════════════════════════════════════════════════════════════════════════════
# Antrenman
# ══════════════════════════════════════════════════════════════════════════════

def get_workout(session_date: Optional[str] = None) -> dict:
    db = oku()
    w = workout_bul(db, session_date or _bugun())
    if not w:
        return {"session_date": session_date or "today", "exercises": []}
    cikti = [{**e, "sets": [set_json(s) for s in setler(db, e["id"])]} for e in egzersizler(db, w["id"])]
    return {"session_date": w["session_date"], "id": w["id"], "notes": w.get("notes"),
            "baslangic": w.get("baslangic"), "bitis": w.get("bitis"), "exercises": cikti}


def add_exercise(name: str, sets: Optional[list[dict]] = None, session_date: Optional[str] = None,
                 oturum_adi: Optional[str] = None) -> dict:
    with islem() as db:
        return egzersiz_ekle(db, session_date or _bugun(), name, sets or [], oturum_adi)


def onceki_setler(once: str, adlar: list[str]) -> dict:
    """`once`'den ÖNCEKİ en son oturumda her adın setleri ("geçen sefer 90 × 5").
    Aynı gün aynı ad iki kez varsa sıradaki İLKİ alınır."""
    db = oku()
    istenen = {a.lower() for a in adlar if a}
    gunler = {w["id"]: w["session_date"] for w in db["workouts"] if str(w.get("session_date", "")) < once}
    adaylar = sorted((e for e in db["exercises"]
                      if e.get("workout_id") in gunler and (e.get("name") or "").lower() in istenen),
                     key=lambda e: (gunler[e["workout_id"]], -float(e.get("position", 0))), reverse=True)
    sonuc: dict = {}
    for e in adaylar:
        ad = e["name"].lower()
        if ad not in sonuc:
            sonuc[ad] = {"tarih": gunler[e["workout_id"]],
                         "sets": [{"reps": int(_sayi(s.get("reps"))), "weight": _sayi(s.get("weight")),
                                   "completed": bool(s.get("completed"))} for s in setler(db, e["id"])]}
    return sonuc


def update_exercise_sets(exercise_id: str, sets: list[dict]) -> Optional[dict]:
    """Upsert: id'li set yerinde güncellenir (id + created_at korunur), id'siz eklenir, listede
    olmayan silinir. `dokunuldu: true` → girildi bir kez damgalanır; açık `"girildi": null` damgayı
    kaldırır (GERİ AL). Gövdede `drops` yoksa eski değer kalır. Doğrulama çağıranın işi (API)."""
    with islem() as db:
        ex = next((e for e in db["exercises"] if e.get("id") == exercise_id), None)
        if ex is None:
            return None
        mevcut = {s["id"]: s for s in db["sets"] if s.get("exercise_id") == exercise_id}
        tutulan: list[str] = []
        cikti = []
        dokunuldu_var = False
        for i, s in enumerate(sets or []):
            kaldir = "girildi" in s and s["girildi"] is None
            dokundu = bool(s.get("dokunuldu")) and not kaldir
            dokunuldu_var |= dokundu
            sid = s.get("id")
            reps, weight, tamam = int(_sayi(s.get("reps"))), _sayi(s.get("weight")), bool(s.get("completed"))
            if sid in mevcut and sid not in tutulan:
                k = mevcut[sid]
                k.update(reps=reps, weight=weight, completed=tamam, position=float(i))
                if kaldir:
                    k["girildi"] = None
                elif dokundu and not k.get("girildi"):
                    k["girildi"] = _simdi()
                if "drops" in s:
                    k["drops"] = s["drops"] or None
            else:
                k = _yeni_set(exercise_id, reps, weight, tamam, i, _simdi() if dokundu else None,
                              s.get("drops") or None)
                db["sets"].append(k)
            tutulan.append(k["id"])
            cikti.append(k)
        db["sets"] = [x for x in db["sets"] if x.get("exercise_id") != exercise_id or x["id"] in tutulan]
        if dokunuldu_var:
            w = next((w for w in db["workouts"] if w["id"] == ex["workout_id"]), None)
            if w is not None and not w.get("baslangic"):
                w["baslangic"] = _simdi()
        return {"exercise_id": exercise_id, "sets": [set_json(k) for k in cikti]}


def delete_exercise(exercise_id: str) -> bool:
    with islem() as db:
        once = len(db["exercises"])
        db["exercises"] = [e for e in db["exercises"] if e.get("id") != exercise_id]
        if len(db["exercises"]) == once:
            return False
        db["sets"] = [s for s in db["sets"] if s.get("exercise_id") != exercise_id]  # öksüz set kalmasın
        return True


# ══════════════════════════════════════════════════════════════════════════════
# Şablonlar
# ══════════════════════════════════════════════════════════════════════════════

def list_templates() -> list[dict]:
    return sorted(oku()["templates"], key=lambda t: t.get("created_at", ""))


def create_template(name: str, exercises: Optional[list[dict]] = None) -> dict:
    with islem() as db:
        kayit = {"id": _uid(), "name": (name or "").strip()[:80], "exercises": exercises or [],
                 "hazir_slug": None, "created_at": _simdi()}
        db["templates"].append(kayit)
        return kayit


def delete_template(template_id: str) -> bool:
    with islem() as db:
        once = len(db["templates"])
        db["templates"] = [t for t in db["templates"] if t.get("id") != template_id]
        return len(db["templates"]) != once


# ══════════════════════════════════════════════════════════════════════════════
# Ayarlar (config)
# ══════════════════════════════════════════════════════════════════════════════

def get_config() -> dict:
    cfg = oku().get("config") or {}
    cikti = {}
    for anahtar, varsayilan in VARSAYILAN_CONFIG.items():
        try:
            cikti[anahtar] = int(cfg.get(anahtar, varsayilan))
        except (TypeError, ValueError):
            cikti[anahtar] = varsayilan
    return cikti


def update_config(**alanlar) -> dict:
    with islem() as db:
        cfg = db["config"]
        for anahtar, deger in alanlar.items():
            if deger is None or anahtar not in VARSAYILAN_CONFIG:
                continue
            try:
                cfg[anahtar] = int(deger)
            except (TypeError, ValueError):
                continue
    return get_config()


def cfg_oku(anahtar: str, db: Optional[dict] = None):
    return copy.deepcopy((db or oku())["config"].get(anahtar))


def cfg_yaz(anahtar: str, deger, db: Optional[dict] = None) -> None:
    if db is not None:
        db["config"][anahtar] = copy.deepcopy(deger)
        return
    with islem() as d:
        d["config"][anahtar] = copy.deepcopy(deger)


def plan_gunleri(db: dict) -> list[int]:
    ham = str(db["config"].get("antrenmanGunleri") or VARSAYILAN_PLAN)
    try:
        gunler = sorted({int(x) for x in ham.split(",") if x.strip()})
    except ValueError:
        return [1, 3, 5]
    return [g for g in gunler if 1 <= g <= 7] or [1, 3, 5]


# ══════════════════════════════════════════════════════════════════════════════
# Özet (Yuki aracı + ön yüz)
# ══════════════════════════════════════════════════════════════════════════════

def get_summary() -> dict:
    db = oku()
    gun = _bugun()
    ogunler = sorted((m for m in db["meals"] if m.get("entry_date") == gun),
                     key=lambda m: m.get("created_at", ""))
    toplam = {"cal": 0.0, "protein": 0.0, "carb": 0.0, "fat": 0.0}
    for m in ogunler:
        for alan in toplam:
            toplam[alan] += _sayi(m.get(alan))
    w = workout_bul(db, gun)
    return {"date": gun, "meals": ogunler, "totals": toplam, "config": get_config(),
            "workout_exercises": len(egzersizler(db, w["id"])) if w else 0}


# ══════════════════════════════════════════════════════════════════════════════
# Postgres'ten tek seferlik içe aktarma (v1 PG kurulumu → v2 depo)
# ══════════════════════════════════════════════════════════════════════════════

def _metin(v) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return str(v)


async def pg_ice_aktar(conn) -> int:
    """v1 Postgres tablolarını depoya kopyalar. YALNIZ depo boşken (öğün/antrenman/şablon yok) ve bir
    kez (`_pg_aktarildi`) çalışır; dolu depoyu ezmez. Dönüş: aktarılan kayıt sayısı."""
    with _lock:
        db = _load()
        if db.get("_pg_aktarildi") or db["meals"] or db["workouts"] or db["templates"]:
            return 0
        n = 0
        for r in await conn.fetch("SELECT * FROM fitness_meals"):
            db["meals"].append({"id": str(r["id"]), "entry_date": _metin(r["entry_date"]), "meal": r["meal"],
                                "name": r["name"], "cal": _sayi(r["cal"]), "protein": _sayi(r["protein"]),
                                "carb": _sayi(r["carb"]), "fat": _sayi(r["fat"]),
                                "created_at": _metin(r.get("created_at")) or _simdi()})
            n += 1
        for r in await conn.fetch("SELECT * FROM fitness_workouts"):
            db["workouts"].append({"id": str(r["id"]), "session_date": _metin(r["session_date"]),
                                   "notes": r.get("notes"), "baslangic": None, "bitis": None,
                                   "created_at": _metin(r.get("created_at")) or _simdi()})
            n += 1
        for r in await conn.fetch("SELECT * FROM fitness_exercises"):
            db["exercises"].append({"id": str(r["id"]), "workout_id": str(r["workout_id"]), "name": r["name"],
                                    "position": float(r.get("position") or 0), "sablon_id": None,
                                    "created_at": _metin(r.get("created_at")) or _simdi()})
            n += 1
        for r in await conn.fetch("SELECT * FROM fitness_sets"):
            # v1'de "yapıldı" ayrımı yoktu: completed=TRUE olan set yapılmış sayılır, gerisi plan.
            db["sets"].append({"id": str(r["id"]), "exercise_id": str(r["exercise_id"]),
                               "reps": int(_sayi(r["reps"])), "weight": _sayi(r["weight"]),
                               "completed": bool(r["completed"]), "position": float(r.get("position") or 0),
                               "created_at": _metin(r.get("created_at")), "girildi": None, "drops": None})
            n += 1
        for r in await conn.fetch("SELECT * FROM fitness_templates"):
            ex = r["exercises"]
            if isinstance(ex, str):
                try:
                    ex = json.loads(ex)
                except ValueError:
                    ex = []
            db["templates"].append({"id": str(r["id"]), "name": r["name"], "exercises": ex or [],
                                    "hazir_slug": None, "created_at": _metin(r.get("created_at")) or _simdi()})
            n += 1
        for r in await conn.fetch("SELECT key, value FROM fitness_config"):
            try:
                db["config"][r["key"]] = int(r["value"])
            except (TypeError, ValueError):
                db["config"][r["key"]] = r["value"]
        db["_pg_aktarildi"] = _simdi()
        _save(db)
        return n

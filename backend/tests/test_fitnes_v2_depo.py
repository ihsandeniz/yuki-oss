"""Fitnes v2 — gömülü depo katmanı (P1).

Korunan şeyler:
  ① v1 dosyası (şema 1) açılınca v2 alanları eksiksiz eklenir, veri kaybolmaz
  ② `islem()` tek kilit + tek atomik yazma: hata olursa dosya DEĞİŞMEZ
  ③ set upsert: id'li set yerinde güncellenir (created_at korunur), id'siz eklenir, listede olmayan silinir
  ④ `girildi` damgası: dokunuldu → bir kez basılır, açık null → kalkar
  ⑤ egzersiz silinince setleri de gider (öksüz set kalmaz)
  ⑥ Postgres'ten tek seferlik içe aktarma yalnız depo BOŞKEN olur
Ağa çıkmaz, Postgres istemez.
"""
import json
from datetime import date

import pytest


@pytest.fixture()
def depo(tmp_path, monkeypatch):
    from app.services import fitness_store as fs
    monkeypatch.setattr(fs, "_STORE_FILE", tmp_path / "fitness_store.json")
    return fs


def test_v1_dosyasi_v2ye_yukseltilir_veri_korunur(depo):
    v1 = {"_schema": 1, "meals": [{"id": "m1", "entry_date": "2026-11-01", "meal": "ara", "name": "elma",
                                    "cal": 50, "protein": 0, "carb": 12, "fat": 0, "created_at": "x"}],
          "workouts": [{"id": "w1", "session_date": "2026-11-01", "notes": None, "created_at": "x"}],
          "exercises": [{"id": "e1", "workout_id": "w1", "name": "Squat", "position": 1, "created_at": "x"}],
          "sets": [{"id": "s1", "exercise_id": "e1", "reps": 5, "weight": 100, "completed": True, "position": 0}],
          "templates": [], "config": {"calGoal": 2100}}
    depo._STORE_FILE.write_text(json.dumps(v1), encoding="utf-8")
    db = depo._load()
    assert db["_schema"] == depo._SCHEMA_VERSION >= 2
    assert db["meals"][0]["name"] == "elma"
    s = db["sets"][0]
    assert s["girildi"] is None and s["drops"] is None and "created_at" in s
    assert db["workouts"][0]["baslangic"] is None and db["workouts"][0]["bitis"] is None
    assert db["exercises"][0]["sablon_id"] is None
    for k in ("olaylar", "hafta_turu", "beceriler", "unvanlar"):
        assert k in db
    assert db["config"]["calGoal"] == 2100 and db["config"]["antrenmanGunleri"] == "1,3,5"


def test_islem_hata_olursa_dosyaya_yazmaz(depo):
    depo.create_meal("ara", "elma", cal=50)
    once = depo._STORE_FILE.read_text(encoding="utf-8")
    with pytest.raises(RuntimeError):
        with depo.islem() as db:
            db["meals"].clear()
            raise RuntimeError("yarıda")
    assert depo._STORE_FILE.read_text(encoding="utf-8") == once


def _egzersiz(depo, gun="2026-11-10"):
    return depo.add_exercise("Bench Press", [{"reps": 8, "weight": 60}, {"reps": 8, "weight": 60}], session_date=gun)


def test_set_upsert_id_korur_eksigi_siler(depo):
    ex = _egzersiz(depo)
    s0, s1 = ex["sets"]
    sonuc = depo.update_exercise_sets(ex["id"], [
        {"id": s0["id"], "reps": 10, "weight": 62.5, "completed": False},
        {"reps": 6, "weight": 70},
    ])
    yeni = sonuc["sets"]
    assert yeni[0]["id"] == s0["id"] and yeni[0]["created_at"] == s0["created_at"]
    assert yeni[0]["reps"] == 10 and yeni[0]["weight"] == 62.5
    assert yeni[1]["id"] not in (s0["id"], s1["id"])
    kalan = {s["id"] for s in depo._load()["sets"]}
    assert s1["id"] not in kalan, "listede olmayan set silinmeli"


def test_girildi_damgasi_bir_kez_basilir_null_ile_kalkar(depo):
    ex = _egzersiz(depo)
    sid = ex["sets"][0]["id"]
    a = depo.update_exercise_sets(ex["id"], [{"id": sid, "reps": 8, "weight": 60, "dokunuldu": True}])["sets"][0]
    assert a["girildi"]
    b = depo.update_exercise_sets(ex["id"], [{"id": sid, "reps": 9, "weight": 60, "dokunuldu": True}])["sets"][0]
    assert b["girildi"] == a["girildi"], "ilk damga korunur"
    c = depo.update_exercise_sets(ex["id"], [{"id": sid, "reps": 9, "weight": 60, "girildi": None,
                                              "dokunuldu": True}])["sets"][0]
    assert c["girildi"] is None, "açık null damgayı kaldırır (GERİ AL)"
    w = depo._load()["workouts"][0]
    assert w["baslangic"], "ilk dokunuş antrenmanı başlatır"


def test_drops_yoksa_korunur_bos_listeyse_silinir(depo):
    ex = _egzersiz(depo)
    sid = ex["sets"][0]["id"]
    depo.update_exercise_sets(ex["id"], [{"id": sid, "reps": 8, "weight": 60, "drops": [{"kg": 40, "tekrar": 6}]}])
    s = depo.update_exercise_sets(ex["id"], [{"id": sid, "reps": 8, "weight": 60}])["sets"][0]
    assert s["drops"] == [{"kg": 40.0, "tekrar": 6}], "gövdede drops yoksa eski değer kalır"
    s = depo.update_exercise_sets(ex["id"], [{"id": sid, "reps": 8, "weight": 60, "drops": []}])["sets"][0]
    assert s["drops"] == [], "yanıtta drops her zaman liste"
    assert depo._load()["sets"][0]["drops"] is None, "boş liste depoda None"


def test_egzersiz_silinince_setleri_gider(depo):
    ex = _egzersiz(depo)
    assert depo.delete_exercise(ex["id"]) is True
    assert depo._load()["sets"] == []


def test_config_json_anahtari_yazilir_okunur(depo):
    depo.cfg_yaz("favoriOgunler", [{"name": "yulaf"}])
    assert depo.cfg_oku("favoriOgunler") == [{"name": "yulaf"}]
    assert depo.cfg_oku("yok") is None
    # hedefler hâlâ tamsayı sözlüğü
    assert depo.get_config()["calGoal"] == 2000


class _SahteConn:
    def __init__(self, tablolar):
        self.t = tablolar

    async def fetch(self, sql, *a):
        for ad, satirlar in self.t.items():
            if f"FROM {ad}" in sql:
                return satirlar
        return []


@pytest.mark.asyncio
async def test_pg_ice_aktarma_yalniz_bos_depoda(depo):
    tablolar = {
        "fitness_meals": [{"id": "m", "entry_date": date(2026, 11, 1), "meal": "ara", "name": "elma",
                           "cal": 50.0, "protein": 0.0, "carb": 0.0, "fat": 0.0, "created_at": None}],
        "fitness_workouts": [], "fitness_exercises": [], "fitness_sets": [], "fitness_templates": [],
        "fitness_config": [{"key": "calGoal", "value": "1800"}],
    }
    n = await depo.pg_ice_aktar(_SahteConn(tablolar))
    assert n == 1
    db = depo._load()
    assert db["meals"][0]["entry_date"] == "2026-11-01" and db["config"]["calGoal"] == 1800
    assert db.get("_pg_aktarildi")
    tablolar["fitness_meals"].append(dict(tablolar["fitness_meals"][0], id="m2"))
    assert await depo.pg_ice_aktar(_SahteConn(tablolar)) == 0, "dolu depoya ikinci kez aktarılmaz"

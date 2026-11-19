"""PLAN · beslenme/antrenman geçmişi sunucudan (2026-09-26).

Kişisel AliceAi'de iki salt-okur uç eklendi (7f136ed · b39ba03); ürün bunları
hem Postgres dalıyla hem JSON dalıyla (satılan paket = JSON) alıyor:
  ① GET /api/fitness/meals/gunluk   — son N günün toplamı, tek istek
  ② GET /api/fitness/workouts/onceki — "geçen sefer" setleri
  ③ POST /workouts/exercise oturum_adi → notes · GET /workouts notes döner
  ④ PG dalında tarih `date` nesnesi gider (asyncpg metni kabul etmez → 500);
     geçersiz tarih 400.

Ağa çıkmaz, Postgres istemez — PG dalı sahte bağlantıyla ölçülür.
"""
from datetime import date

import pytest

pytestmark = pytest.mark.usefixtures("fitnes_acik")  # bayrak varsayılan kapalı (test_ozellik_bayrak.py)


@pytest.fixture()
def depo(tmp_path, monkeypatch):
    from app.services import fitness_store as fs
    monkeypatch.setattr(fs, "_STORE_FILE", tmp_path / "fitness_store.json")
    return fs


# ── JSON deposu ──────────────────────────────────────────────────────────────

def test_gunluk_toplam_aralik_ve_bos_gun(depo):
    depo.create_meal("ogle", "a", cal=500, protein=30, entry_date="2026-09-20")
    depo.create_meal("aksam", "b", cal=250.5, entry_date="2026-09-20")
    depo.create_meal("ogle", "c", cal=100, entry_date="2026-09-14")   # aralık dışı (7 gün: 15..21)
    depo.create_meal("ogle", "d", cal=300, entry_date="2026-09-21")
    depo.create_meal("ogle", "e", cal=999, entry_date="2026-09-22")   # bitişten sonra

    sonuc = depo.meals_gunluk("2026-09-21", 7)
    assert [g["tarih"] for g in sonuc] == ["2026-09-20", "2026-09-21"], "boş gün listede olmamalı, sıra artan"
    assert sonuc[0]["cal"] == 750.5 and sonuc[0]["protein"] == 30.0
    assert sonuc[1]["cal"] == 300.0


def test_onceki_setler_en_son_oturum_harf_duyarsiz(depo):
    depo.add_exercise("Bench Press", [{"reps": 10, "weight": 80}], "2026-09-10")
    depo.add_exercise("bench press", [{"reps": 5, "weight": 90, "completed": True}], "2026-09-17")
    depo.add_exercise("BENCH PRESS", [{"reps": 1, "weight": 200}], "2026-09-24")   # 'once' günü: sayılmaz
    depo.add_exercise("Squat", [{"reps": 8, "weight": 100}], "2026-09-17")

    s = depo.onceki_setler("2026-09-24", ["Bench Press", "Deadlift"])
    assert set(s) == {"bench press"}, "hiç yapılmamış ad sözlükte yer almamalı; istenmeyen ad da"
    assert s["bench press"]["tarih"] == "2026-09-17"
    assert s["bench press"]["sets"] == [{"reps": 5, "weight": 90.0, "completed": True}]


def test_onceki_setler_ayni_gun_ilk_pozisyon(depo):
    """PG `ORDER BY ... e.position` ile aynı gündeki İLK egzersizi alır; depo da."""
    depo.add_exercise("curl", [{"reps": 12, "weight": 10}], "2026-09-17")
    depo.add_exercise("curl", [{"reps": 6, "weight": 20}], "2026-09-17")
    assert depo.onceki_setler("2026-09-18", ["curl"])["curl"]["sets"][0]["reps"] == 12


def test_oturum_adi_yalniz_bossa_yazilir(depo):
    depo.add_exercise("bench", [], "2026-09-17", oturum_adi="Göğüs Günü")
    depo.add_exercise("fly", [], "2026-09-17", oturum_adi="Başka Ad")
    w = depo.get_workout("2026-09-17")
    assert w["notes"] == "Göğüs Günü", "ikinci egzersiz ilk adı ezmemeli"
    assert len(w["exercises"]) == 2


def test_bosalan_gunde_oturum_adi_yeniden_belirlenir(depo):
    """Şablon yüklenip egzersizleri silinen gün eski adı taşımamalı (ANTRENMAN · ODAK ölçümü,
    09-26: 0 egzersizli günde başlık "Göğüs Günü" kalıyordu, Sırt yüklense de değişmiyordu)."""
    e = depo.add_exercise("bench", [], "2026-09-17", oturum_adi="Göğüs Günü")
    depo.delete_exercise(e["id"])
    e = depo.add_exercise("deadlift", [], "2026-09-17", oturum_adi="Sırt Günü")
    assert depo.get_workout("2026-09-17")["notes"] == "Sırt Günü"
    depo.delete_exercise(e["id"])
    depo.add_exercise("curl", [], "2026-09-17")
    assert depo.get_workout("2026-09-17")["notes"] is None, "şablonsuz ilk egzersiz eski adı silmeli"
    depo.add_exercise("row", [], "2026-09-17", oturum_adi="Sırt Günü")
    assert depo.get_workout("2026-09-17")["notes"] == "Sırt Günü", "dolu günde ad boşsa yazılır"


# ── HTTP (JSON dalı, kapı açık) ──────────────────────────────────────────────

@pytest.fixture()
def istemci(depo):
    from starlette.testclient import TestClient

    from app.api.todo import require_planner
    from app.main import app
    app.dependency_overrides[require_planner] = lambda: None
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(require_planner, None)


def test_uclar_postgressiz_cevap_veriyor(istemci):
    r = istemci.post("/api/fitness/meals", json={"meal": "ogle", "name": "x", "cal": 400,
                                                 "entry_date": "2026-09-20"})
    assert r.status_code == 201
    r = istemci.get("/api/fitness/meals/gunluk", params={"bitis": "2026-09-21", "gun": 7})
    assert r.status_code == 200 and r.json() == [
        {"tarih": "2026-09-20", "cal": 400.0, "protein": 0.0, "carb": 0.0, "fat": 0.0}]

    r = istemci.post("/api/fitness/workouts/exercise",
                     json={"name": "Squat", "sets": [{"reps": 5, "weight": 100}],
                           "session_date": "2026-09-20", "oturum_adi": "Bacak"})
    assert r.status_code == 201
    r = istemci.get("/api/fitness/workouts", params={"date": "2026-09-20"})
    assert r.json()["notes"] == "Bacak"
    r = istemci.get("/api/fitness/workouts/onceki", params=[("once", "2026-09-21"), ("adlar", "squat")])
    assert r.status_code == 200 and r.json()["squat"]["sets"][0]["weight"] == 100.0
    assert istemci.get("/api/fitness/workouts/onceki", params={"once": "2026-09-21"}).json() == {}


@pytest.mark.parametrize("yol,params", [
    ("/api/fitness/meals/gunluk", {"bitis": "dün"}),
    ("/api/fitness/workouts/onceki", {"once": "2026-13-40", "adlar": "x"}),
    ("/api/fitness/meals", {"date": "bozuk"}),
    ("/api/fitness/workouts", {"date": "bozuk"}),
])
def test_gecersiz_tarih_400(istemci, yol, params):
    r = istemci.get(yol, params=params)
    assert r.status_code == 400, f"{yol}: geçersiz tarih 400 olmalı, {r.status_code} geldi"


# PG dalı (tarih tipi) testi 2026-11-12'de kalktı: Fitnes v2 Postgres dalını taşımıyor, tek kaynak
# gömülü depo (bkz. app/services/fitness_store.py modül notu). PG v1 verisinin içe aktarımı:
# tests/test_fitnes_v2_depo.py::test_pg_ice_aktarma_yalniz_bos_depoda.

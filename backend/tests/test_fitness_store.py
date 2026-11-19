"""Fitness gömülü deposu + API kapısı testleri (2026-08-23).

Neden var: `api/fitness.py` router'ı main.py'ye HİÇ kaydedilmemişti ve yalnız
asyncpg biliyordu. Planner'da FİTNES sekmesi duruyor, ekran açılıyor, backend
404 dönüyordu — sessiz başarısızlık. Bu testler iki şeyi birden korur:
  ① depo Postgres'siz çalışıyor (satılan paketin normali)
  ② uçlar kayıtlı ve Pro kapısının arkasında

Ağa çıkmaz, Postgres istemez.
"""
import importlib
import json

import pytest

pytestmark = pytest.mark.usefixtures("fitnes_acik")  # bayrak varsayılan kapalı (test_ozellik_bayrak.py)


@pytest.fixture()
def depo(tmp_path, monkeypatch):
    """Her test kendi dosyasında koşar — testler birbirinin verisini görmez."""
    from app.services import fitness_store as fs
    monkeypatch.setattr(fs, "_STORE_FILE", tmp_path / "fitness_store.json")
    return fs


# ══════════════════════════════════════════════════════════════════════════════
# Depo
# ══════════════════════════════════════════════════════════════════════════════

def test_bos_depo_varsayilan_hedeflerle_kurulur(depo):
    cfg = depo.get_config()
    assert cfg == {"calGoal": 2000, "proteinGoal": 150, "carbGoal": 200, "fatGoal": 65}, \
        "fitness_init.sql'deki tohum değerlerle aynı olmalı"


def test_ogun_ekle_listele_sil(depo):
    k = depo.create_meal("kahvalti", "yumurta", cal=155, protein=13)
    assert k["meal"] == "kahvalti" and k["cal"] == 155.0
    assert len(depo.list_meals()) == 1
    assert depo.delete_meal(k["id"]) is True
    assert depo.list_meals() == []
    assert depo.delete_meal(k["id"]) is False, "olmayan kayıt False dönmeli (404 üretir)"


def test_bilinmeyen_ogun_adi_araya_duser(depo):
    """SQL'de CHECK (meal IN (...)) var — depo da aynı kısıtı uygulamalı."""
    k = depo.create_meal("brunch", "tost")
    assert k["meal"] == "ara"


def test_ogun_tarihe_gore_suzulur(depo):
    depo.create_meal("ogle", "bugünkü")
    depo.create_meal("ogle", "dünkü", entry_date="2020-01-01")
    assert len(depo.list_meals()) == 1
    assert len(depo.list_meals("2020-01-01")) == 1
    assert depo.list_meals("2020-01-01")[0]["name"] == "dünkü"


def test_egzersiz_ekleyince_antrenman_kendiliginden_acilir(depo):
    """SQL'deki _ensure_workout karşılığı: session_date UNIQUE, yoksa yaratılır."""
    e1 = depo.add_exercise("bench", [{"reps": 8, "weight": 60}])
    e2 = depo.add_exercise("squat", [])
    w = depo.get_workout()
    assert len(w["exercises"]) == 2
    assert e1["position"] < e2["position"], "sıra korunmalı"
    assert w["exercises"][0]["sets"][0]["reps"] == 8


def test_setler_yeniden_yazilir(depo):
    e = depo.add_exercise("bench", [{"reps": 8, "weight": 60}])
    s = depo.update_exercise_sets(e["id"], [{"reps": 5, "weight": 80, "completed": True}])
    assert len(s["sets"]) == 1 and s["sets"][0]["weight"] == 80.0
    assert s["sets"][0]["completed"] is True
    assert depo.update_exercise_sets("yok-boyle-id", []) is None


def test_egzersiz_silinince_setleri_de_gider(depo):
    """SQL'de ON DELETE CASCADE var; JSON'da elle uygulanmalı, yoksa öksüz set kalır."""
    e = depo.add_exercise("bench", [{"reps": 8}, {"reps": 6}])
    depo.delete_exercise(e["id"])
    ham = json.loads(depo._STORE_FILE.read_text(encoding="utf-8"))
    assert ham["sets"] == [], "öksüz set kaldı — CASCADE uygulanmamış"


def test_sablon_yasam_dongusu(depo):
    t = depo.create_template("push günü", [{"name": "bench", "sets": [{"reps": 8}]}])
    assert len(depo.list_templates()) == 1
    assert depo.delete_template(t["id"]) is True
    assert depo.list_templates() == []


def test_hedefler_guncellenir_ve_kalici(depo):
    depo.update_config(calGoal=2500, proteinGoal=None)
    cfg = depo.get_config()
    assert cfg["calGoal"] == 2500
    assert cfg["proteinGoal"] == 150, "None gönderilen alan DEĞİŞMEMELİ"


def test_bilinmeyen_config_anahtari_yok_sayilir(depo):
    depo.update_config(calGoal=1800, birSeyUydurma=42)
    assert "birSeyUydurma" not in depo.get_config()


def test_ozet_gunun_toplamini_verir(depo):
    depo.create_meal("kahvalti", "yumurta", cal=155, protein=13, carb=1, fat=11)
    depo.create_meal("ogle", "tavuk", cal=250, protein=30, carb=0, fat=14)
    depo.add_exercise("bench", [{"reps": 8}])
    o = depo.get_summary()
    assert o["totals"]["cal"] == 405.0
    assert o["totals"]["protein"] == 43.0
    assert o["workout_exercises"] == 1
    assert len(o["meals"]) == 2


def test_bozuk_dosya_silinmez_yedeklenir(depo, tmp_path):
    """Kullanıcının verisi olabilir — bozuk JSON'u silmek veri imhasıdır."""
    depo._STORE_FILE.write_text("{bu gecerli json degil", encoding="utf-8")
    depo.get_config()   # patlamamalı
    assert depo._STORE_FILE.with_suffix(".json.bozuk").exists(), "bozuk dosya yedeklenmedi"


def test_eksik_anahtar_patlatmaz(depo):
    """Elle düzenlenmiş / eski sürüm dosyası KeyError ile ölmemeli."""
    depo._STORE_FILE.write_text(json.dumps({"meals": []}), encoding="utf-8")
    assert depo.get_config()["calGoal"] == 2000
    assert depo.list_templates() == []


# ══════════════════════════════════════════════════════════════════════════════
# API kaydı + kademe kapısı
# ══════════════════════════════════════════════════════════════════════════════

def test_router_main_e_kayitli():
    """🔴 ASIL REGRESYON: bu satır yoktu, /api/fitness/* 404 dönüyordu."""
    from app.main import app
    yollar = {r.path for r in app.routes if getattr(r, "path", "").startswith("/api/fitness")}
    assert yollar, "fitness router main.py'ye kayıtlı değil — sekme yine sessizce ölür"
    for beklenen in ("/api/fitness/meals", "/api/fitness/workouts",
                     "/api/fitness/templates", "/api/fitness/config",
                     "/api/fitness/summary"):
        assert beklenen in yollar, f"{beklenen} kayıtlı değil"


def test_pro_kapisi_router_duzeyinde():
    """PLAN ekranının modu → planner ile aynı kapı. Free'de 403 dönmeli."""
    from app.api import fitness as fapi
    from app.api.todo import require_planner
    bagimliliklar = [d.dependency for d in fapi.router.dependencies]
    assert require_planner in bagimliliklar, \
        "Pro kapısı yok — Free kullanıcı fitness uçlarına erişir"


def test_postgressiz_uclar_gercekten_cevap_veriyor(tmp_path, monkeypatch):
    """🔴 ASIL SORU: Postgres YOKKEN uçlar çalışıyor mu? (satılan paketin normali)

    Eski `_pool()` 503 fırlatıyordu → tüm fitness yüzeyi ölüydü.

    ⚠️ Bu test iki kez yeniden yazıldı, ikisi de ders:
      1. `"503" not in inspect.getsource(...)` → kendi docstring'indeki "503"e
         takıldı. Kod doğruyken kırmızı yandı: METİN ölçmek DAVRANIŞ ölçmek değildir.
      2. Uç fonksiyonunu doğrudan `get_config(None)` diye çağırmak → slowapi
         "request must be a Request" diye patladı. Dekoratörlü uç, düz fonksiyon gibi
         çağrılamaz.
    Artık gerçek HTTP isteği yapılıyor: uç + kapı + depo zinciri bir arada ölçülüyor.
    """
    from starlette.testclient import TestClient

    from app.api.todo import require_planner
    from app.main import app
    from app.services import fitness_store as fs

    monkeypatch.setattr(fs, "_STORE_FILE", tmp_path / "fitness_store.json")
    # Kademe kapısını aç: burada ölçtüğümüz şey lisans değil, Postgres'siz yol.
    app.dependency_overrides[require_planner] = lambda: None
    try:
        with TestClient(app) as c:
            r = c.get("/api/fitness/config")
            assert r.status_code == 200, f"Postgres yokken 200 bekleniyordu, {r.status_code} geldi"
            assert r.json()["calGoal"] == 2000

            r = c.post("/api/fitness/meals", json={"meal": "kahvalti", "name": "yumurta", "cal": 155})
            assert r.status_code == 201, "öğün eklenemedi — gömülü depo yolu kırık"

            r = c.get("/api/fitness/summary")
            assert r.status_code == 200
            assert r.json()["totals"]["cal"] == 155.0, "eklenen öğün özete yansımadı"
    finally:
        app.dependency_overrides.pop(require_planner, None)



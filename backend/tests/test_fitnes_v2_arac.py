"""Fitnes v2 — Yuki araçları ekranla AYNI depoya yazar (P3).

Kusur (2026-11-12 ölçüldü): araçlar yalnız Postgres'e yazıyordu, ekran gömülü depodan okuyordu →
Yuki "öğün eklendi" diyor, ekranda görünmüyordu (Postgres'siz kurulumda araç hata veriyordu).
"""
import asyncio

import pytest


@pytest.fixture()
def depo(tmp_path, monkeypatch):
    from app.services import fitness_store as fs
    monkeypatch.setattr(fs, "_STORE_FILE", tmp_path / "fitness_store.json")
    return fs


def test_arac_ogunu_ekranin_deposuna_yazar(depo):
    from app.services.tools import fitness_tools as A
    out = asyncio.run(A.log_meal("yulaf", 300, meal="kahvalti", protein=10, entry_date="2026-11-09"))
    assert out.startswith("Öğün eklendi"), out
    assert depo.list_meals("2026-11-09")[0]["name"] == "yulaf"
    assert "1 öğün" in asyncio.run(A.get_fitness_summary("2026-11-09"))


def test_arac_egzersizi_yapilmis_set_olarak_yazar(depo):
    from app.services.tools import fitness_tools as A
    out = asyncio.run(A.log_workout_exercise("Squat", sets=2, reps=5, weight=100, session_date="2026-11-09"))
    assert out.startswith("Egzersiz eklendi"), out
    ex = depo.get_workout("2026-11-09")["exercises"][0]
    assert len(ex["sets"]) == 2 and all(depo.yapildi_mi(s) for s in ex["sets"])
    assert "[2/2 set]" in asyncio.run(A.list_workout("2026-11-09"))


def test_arac_sablon_ve_hedef(depo):
    from app.services.tools import fitness_tools as A
    out = asyncio.run(A.save_fitness_template("Bacak", '[{"name": "Squat", "sets": [{"reps": 5, "weight": 100}]}]'))
    tid = out.split("[id: ")[1].rstrip("]")
    assert "Bacak" in asyncio.run(A.list_fitness_templates())
    assert asyncio.run(A.delete_fitness_template(tid)).startswith("Şablon silindi")
    asyncio.run(A.update_fitness_config(cal_goal=1800))
    assert depo.get_config()["calGoal"] == 1800

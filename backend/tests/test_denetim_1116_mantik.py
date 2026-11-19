"""Denetim 2026-11-16 mantık bulguları (MNT-F004, MNT-F001).

MNT-F004: saat dilimi ofsetli ISO hatırlatıcı (`2026-12-01T10:00:00+03:00`) `reminders.json`'a aware yazılıyor,
yeniden başlatmada `rd <= now` aware/naive TypeError veriyor, `except` yutuyor ve kayıt diskten SİLİNİYORDU.
MNT-F001: bütçe tutarı NaN/sonsuz kabul ediliyordu (`NaN <= 0` False) → o ayın özeti kalıcı 500.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient


# ── MNT-F004 ──────────────────────────────────────────────────────────── #
@pytest.fixture
def hatirlatici(tmp_path, monkeypatch):
    from app.services import scheduler as s
    yol = tmp_path / "reminders.json"
    monkeypatch.setattr(s, "_REMINDERS_PATH", yol)
    monkeypatch.setattr(s, "SCHEDULER_ENABLED", True)
    eklenen = []

    class _Sahte:
        def add_job(self, *a, **k):
            eklenen.append(k)

    monkeypatch.setattr(s, "get_scheduler", lambda: _Sahte())
    return s, yol, eklenen


def test_ofsetli_iso_naif_yerel_saate_cevrilir(hatirlatici):
    s, _, _ = hatirlatici
    dt = s.parse_when("2026-12-01T10:00:00+03:00")
    assert dt is not None and dt.tzinfo is None
    beklenen = datetime.fromisoformat("2026-12-01T10:00:00+03:00").astimezone().replace(tzinfo=None)
    assert dt == beklenen


def test_eski_kayitta_ofsetli_hatirlatici_yeniden_baslatmada_SILINMEZ(hatirlatici):
    """Düzeltmeden önce yazılmış (aware) kayıt da kurtulmalı — dosyadakiler kullanıcının verisi."""
    s, yol, eklenen = hatirlatici
    ileri = (datetime.now().astimezone() + timedelta(days=2)).isoformat()
    kayitlar = [{"id": "reminder_ofset", "kind": "once", "message": "ilaç", "run_date": ileri},
                {"id": "reminder_naif", "kind": "once", "message": "su",
                 "run_date": (datetime.now() + timedelta(days=1)).isoformat()}]
    yol.write_text(json.dumps(kayitlar), encoding="utf-8")
    s.register_reminders()
    kalan = [r["id"] for r in json.loads(yol.read_text(encoding="utf-8"))]
    assert kalan == ["reminder_ofset", "reminder_naif"], kalan
    assert len(eklenen) == 2
    assert all(k["run_date"].tzinfo is None for k in eklenen)


def test_ofsetli_hatirlatici_ekle_ve_yeniden_baslat_ucu_uca(hatirlatici):
    s, yol, eklenen = hatirlatici
    ne_zaman = s.parse_when((datetime.now().astimezone() + timedelta(hours=3)).isoformat())
    s.add_reminder("toplantı", ne_zaman)
    s.register_reminders()
    assert [r["message"] for r in json.loads(yol.read_text(encoding="utf-8"))] == ["toplantı"]


# ── MNT-F001 ──────────────────────────────────────────────────────────── #
@pytest.fixture
def butce(tmp_path, monkeypatch):
    from app.api import todo
    from app.limiter import limiter
    from app.services import todo_store

    async def _havuzsuz():
        return None

    monkeypatch.setattr(todo, "_pool", _havuzsuz)
    monkeypatch.setattr(todo_store, "_STORE_FILE", tmp_path / "todo_store.json")
    monkeypatch.setattr(todo_store, "_LEGACY_FILE", tmp_path / "todos.json")
    limiter.reset()
    from app.main import app
    yield TestClient(app, client=("127.0.0.1", 5555), base_url="http://127.0.0.1:8791")
    limiter.reset()


@pytest.mark.parametrize("tutar", ["NaN", "Infinity", "-Infinity", "1e400"])
def test_butce_sayi_olmayan_tutari_REDDEDER_ozet_bozulmaz(butce, tutar):
    c = butce
    gun = datetime.now().date().isoformat()
    r = c.post("/api/todo/budget", content='{"type":"expense","amount":%s,"category":"market","entry_date":"%s"}'
               % (tutar, gun), headers={"content-type": "application/json"})
    assert 400 <= r.status_code < 500, (r.status_code, r.text)
    ay = gun[:7]
    assert c.get(f"/api/todo/budget/summary?month={ay}").status_code == 200
    assert c.get(f"/api/todo/budget/entries?month={ay}").status_code == 200


def test_butce_gecerli_tutar_hala_kabul(butce):
    r = butce.post("/api/todo/budget", json={"type": "expense", "amount": 12.5, "category": "market"})
    assert r.status_code == 200, r.text

"""Bütçe kaydının günü ve varsayılan ayı YEREL saatle.

Panelden tarihsiz eklenen gider UTC gününe yazılıyordu: İstanbul'da 1 Aralık 01:30'da girilen
harcama 30 Kasım'a düşüyor, Aralık toplamında görünmüyordu; varsayılan ay görünümü (özet ve
liste) ilk 3 saat önceki ayı gösteriyordu. Yuki'nin bütçe aracı ve todo_store zaten yerel
`date.today()` kullanıyor — iki yüzey farklı toplam veriyordu. Kişisel Yuki'deki düzeltmenin
yeniden yazımı (SQLite yolu: pool=None).
"""
import time
from datetime import datetime, timezone

import pytest

from app.api import todo


class _Saat(datetime):
    """Sabit an: 2026-11-30 22:30 UTC = 2026-12-01 01:30 İstanbul."""
    AN = datetime(2026, 11, 30, 22, 30, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.AN.astimezone(tz) if tz else cls.AN.astimezone().replace(tzinfo=None)


@pytest.fixture
def istanbul(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Istanbul")
    time.tzset()
    monkeypatch.setattr(todo, "datetime", _Saat)

    async def _yok():
        return None
    monkeypatch.setattr(todo, "_pool", _yok)
    kayit = {}
    monkeypatch.setattr(todo.todo_store, "add_budget_entry",
                        lambda t, a, c, n, d: kayit.setdefault("gun", d) and {"ok": 1})
    monkeypatch.setattr(todo.todo_store, "get_budget_entries",
                        lambda m, limit: kayit.setdefault("ay", m) and [])
    monkeypatch.setattr(todo.todo_store, "get_budget_summary",
                        lambda m: kayit.setdefault("ozet_ay", m) and {})
    yield kayit
    monkeypatch.undo()
    time.tzset()


async def test_gece_girilen_gider_yerel_gune_yazilir(istanbul, client):
    r = await client.post("/api/todo/budget", json={"type": "expense", "amount": 120.0})
    assert r.status_code == 200, r.text
    assert istanbul["gun"] == "2026-12-01"


async def test_varsayilan_ay_yerel_ay(istanbul, client):
    await client.get("/api/todo/budget/entries")
    await client.get("/api/todo/budget/summary")
    assert istanbul["ay"] == "2026-12"
    assert istanbul["ozet_ay"] == "2026-12"


async def test_verilen_tarih_aynen_kalir(istanbul, client):
    await client.post("/api/todo/budget",
                      json={"type": "income", "amount": 5.0, "entry_date": "2026-10-03"})
    assert istanbul["gun"] == "2026-10-03"

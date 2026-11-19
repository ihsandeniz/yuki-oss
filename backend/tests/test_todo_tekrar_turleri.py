"""Tekrarlı görevin HER tekrar türü tamamlanınca sonraki kopyayı açar — her yoldan.

① `_VALID_REPEATS` hafta içi / 2 haftada / yıllık / özel (custom:N) kabul ediyordu ama
   klonlama yalnız daily/weekly/monthly biliyordu: bu türler ilk tamamlamada zinciri
   sessizce kaybediyordu (SQLite ve Postgres yolu).
② Yuki'nin `complete_todo` aracı Postgres yolunda hiç klonlamıyordu: sesle tamamlanan
   günlük görevin ertesi günü açılmıyordu (panel ucu açıyordu).
Kişisel Yuki'deki iki düzeltmenin yeniden yazımı; tarih kuralı tek yerde (`sonraki_tarih`).
"""
import asyncio
from datetime import date

import pytest

from app.api import todo as todo_api
from app.services import todo_store
from tests.test_todo_tekrar_gizli import _SahteConn, _SahteHavuz


@pytest.fixture(autouse=True)
def izole_depo(tmp_path, monkeypatch):
    monkeypatch.setattr(todo_store, "_STORE_FILE", tmp_path / "todo_store.json")
    monkeypatch.setattr(todo_store, "_LEGACY_FILE", tmp_path / "todos.json")

    async def _yok():
        return None
    monkeypatch.setattr(todo_api, "get_pool", _yok)


TURLER = [
    ("daily", "2026-11-13", "2026-11-14"),
    ("weekdays", "2026-11-13", "2026-11-16"),   # Cuma → Pazartesi
    ("weekdays", "2026-11-11", "2026-11-12"),
    ("weekly", "2026-11-13", "2026-11-20"),
    ("biweekly", "2026-11-13", "2026-11-27"),
    ("monthly", "2026-01-31", "2026-02-28"),
    ("yearly", "2026-11-13", "2027-11-13"),
    ("yearly", "2028-02-29", "2029-02-28"),
    ("custom:3", "2026-11-13", "2026-11-16"),
]


@pytest.mark.parametrize("tekrar, gun, beklenen", TURLER)
def test_sqlite_her_tekrar_turu_klonlanir(tekrar, gun, beklenen):
    t = todo_store.create_task(todo_store.INBOX_ID, title="ilaç", due_date=gun, repeat=tekrar)
    todo_store.complete_task(t["id"])
    acik = [g for g in todo_store.get_tasks(todo_store.INBOX_ID)["tasks"] if not g.get("completed_at")]
    assert [g["due_date"] for g in acik] == [beklenen]


class _Conn(_SahteConn):
    """Araç yolu `SET completed_at = NOW()` yazar (parametresiz): sahte de tamamlandı işaretler."""
    async def fetchrow(self, sql, *a):
        r = self.g.get(a[0])
        if sql.lstrip().startswith("UPDATE"):
            if not r or ("completed_at IS NULL" in sql and r["completed_at"]):
                return None
            r["completed_at"] = a[1] if len(a) > 1 else "şimdi"
        return dict(r) if r else None


def _pg(monkeypatch, tekrar, gun):
    g = {"id": "t1", "list_id": "l1", "title": "ilaç", "notes": None, "priority": "mid",
         "repeat": tekrar, "tags": [], "completed_at": None, "due_date": date.fromisoformat(gun)}
    conn = _Conn({"t1": g})
    havuz = _SahteHavuz(conn)

    async def _h():
        return havuz
    monkeypatch.setattr(todo_api, "get_pool", _h)
    return conn


@pytest.mark.parametrize("tekrar, gun, beklenen", TURLER)
def test_pg_panel_ucu_her_tekrar_turu_klonlanir(monkeypatch, tekrar, gun, beklenen):
    conn = _pg(monkeypatch, tekrar, gun)
    tamamla = getattr(todo_api.complete_task, "__wrapped__", todo_api.complete_task)
    asyncio.run(tamamla(type("R", (), {})(), "t1"))
    assert conn.eklenen == [date.fromisoformat(beklenen)]


@pytest.mark.parametrize("tekrar, gun, beklenen", [TURLER[0], TURLER[1], TURLER[4]])
def test_pg_yuki_araci_ile_tamamlama_da_klonlar(monkeypatch, tekrar, gun, beklenen):
    from app.services.tools import todo_tools
    conn = _pg(monkeypatch, tekrar, gun)

    async def _h():
        return await todo_api.get_pool()
    monkeypatch.setattr(todo_tools, "_pool", _h)
    sonuc = asyncio.run(todo_tools.complete_todo("t1"))
    assert "ilaç" in sonuc
    assert conn.eklenen == [date.fromisoformat(beklenen)]
    asyncio.run(todo_tools.complete_todo("t1"))            # ikinci kez: ikinci klon yok
    assert len(conn.eklenen) == 1


def test_bilinmeyen_tekrar_none():
    assert todo_store.sonraki_tarih(date(2026, 11, 13), "her-salı") is None
    assert todo_store.sonraki_tarih(date(2026, 11, 13), "custom:0") is None

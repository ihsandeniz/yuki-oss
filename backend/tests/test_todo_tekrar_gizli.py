"""Tekrarlı görev — testlerin kaçırdığı sessiz kusurlar (2026-11-10 gizli hata turu).

① Aynı görev iki kez tamamlanırsa (çift tık, ağ tekrarı) ya da tamamla→geri al→tamamla
   yapılırsa bir sonraki tekrar İKİ KEZ açılır.
② Toplu tamamlama tekrarı hiç klonlamaz → günlük görev zinciri sessizce biter.
③ Ayın 29/30/31'indeki aylık görev, o günü olmayan aya gelince tekrar SESSİZCE biter.
"""
import pytest

from app.api import todo as todo_api
from app.services import todo_store


@pytest.fixture(autouse=True)
def izole_depo(tmp_path, monkeypatch):
    monkeypatch.setattr(todo_store, "_STORE_FILE", tmp_path / "todo_store.json")
    monkeypatch.setattr(todo_store, "_LEGACY_FILE", tmp_path / "todos.json")

    async def _yok():
        return None

    monkeypatch.setattr(todo_api, "get_pool", _yok)
    return tmp_path


def _acik():
    return todo_store.get_tasks(todo_store.INBOX_ID)["tasks"]


def _gorev(**kw):
    return todo_store.create_task(todo_store.INBOX_ID, title="ilaç", **kw)


def test_iki_kez_tamamlamak_IKINCI_tekrar_acmaz():
    t = _gorev(due_date="2026-08-03", repeat="daily")
    todo_store.complete_task(t["id"])
    todo_store.complete_task(t["id"])
    acik = _acik()
    assert [g["due_date"] for g in acik] == ["2026-08-04"], acik


def test_tamamla_geri_al_tamamla_IKINCI_tekrar_acmaz():
    t = _gorev(due_date="2026-08-03", repeat="weekly")
    todo_store.complete_task(t["id"])
    todo_store.uncomplete_task(t["id"])
    todo_store.complete_task(t["id"])
    acik = [g for g in _acik() if g["id"] != t["id"]]
    assert [g["due_date"] for g in acik] == ["2026-08-10"], acik


def test_ikinci_tamamlama_ilk_tamamlanma_zamanini_EZMEZ(monkeypatch):
    import itertools
    sayac = itertools.count()
    monkeypatch.setattr(todo_store, "_now_iso", lambda: f"2026-08-03T10:00:{next(sayac):02d}")
    t = _gorev()
    ilk = todo_store.complete_task(t["id"])["completed_at"]
    todo_store.complete_task(t["id"])
    assert todo_store.get_task(t["id"])["completed_at"] == ilk


def test_toplu_tamamlama_tekrari_KOPARMAZ_ve_GERCEK_sayiyi_doner():
    t = _gorev(due_date="2026-08-03", repeat="daily")
    n = todo_store.bulk_complete([t["id"], "olmayan-id"])
    assert n == 1, "olmayan kimlik de 'tamamlandı' sayıldı"
    assert [g["due_date"] for g in _acik()] == ["2026-08-04"], "toplu tamamlamada tekrar koptu"


@pytest.mark.parametrize("gun,beklenen", [
    ("2026-01-31", "2026-02-28"),
    ("2028-01-30", "2028-02-29"),
    ("2026-03-31", "2026-04-30"),
    ("2026-12-15", "2027-01-15"),
])
def test_aylik_tekrar_ay_sonunda_BITMEZ(gun, beklenen):
    t = _gorev(due_date=gun, repeat="monthly")
    todo_store.complete_task(t["id"])
    assert [g["due_date"] for g in _acik()] == [beklenen]


# ── Postgres yolu: aynı iki kusur (sahte havuz; SQL'in WHERE koşulu taklit edilir) ──

class _SahteConn:
    def __init__(self, gorevler):
        self.g = gorevler
        self.eklenen = []

    async def fetchrow(self, sql, *a):
        r = self.g.get(a[0])
        if sql.startswith("UPDATE"):
            if not r or ("completed_at IS NULL" in sql and r["completed_at"]):
                return None
            r["completed_at"] = a[1]
        return dict(r) if r else None

    async def fetchval(self, sql, *a):
        return 0

    async def execute(self, sql, *a):
        if sql.strip().startswith("INSERT"):
            self.eklenen.append(a[5])          # new_due


class _SahteHavuz:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        conn = self.conn

        class _C:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *e):
                return False
        return _C()


def _pg(monkeypatch, **gorev):
    from datetime import date
    g = {"id": "t1", "list_id": "l1", "title": "kira", "notes": None, "priority": "mid",
         "repeat": "monthly", "tags": [], "completed_at": None, "due_date": date(2026, 1, 31)}
    g.update(gorev)
    conn = _SahteConn({"t1": g})
    havuz = _SahteHavuz(conn)

    async def _h():
        return havuz
    monkeypatch.setattr(todo_api, "get_pool", _h)
    return conn


def test_PG_iki_kez_tamamlamak_tek_klon_ve_ay_sonu_500_DEGIL(monkeypatch):
    import asyncio
    from datetime import date
    conn = _pg(monkeypatch)
    istek = type("R", (), {})()
    tamamla = todo_api.complete_task.__wrapped__ if hasattr(todo_api.complete_task, "__wrapped__") \
        else todo_api.complete_task
    asyncio.run(tamamla(istek, "t1"))
    asyncio.run(tamamla(istek, "t1"))
    assert conn.eklenen == [date(2026, 2, 28)], conn.eklenen


# ── PG yolu: çöpteki görev filtre/arama/istatistiğe girmez; öncelik high önce ──

class _SqlYakala:
    def __init__(self):
        self.sqller = []

    async def fetch(self, sql, *a):
        self.sqller.append(sql)
        return []

    async def fetchrow(self, sql, *a):
        self.sqller.append(sql)
        return {}


def _yakala(monkeypatch):
    conn = _SqlYakala()
    havuz = _SahteHavuz(conn)

    async def _h():
        return havuz
    monkeypatch.setattr(todo_api, "get_pool", _h)
    return conn


def _cagir(fn, *a, **k):
    import asyncio
    fn = getattr(fn, "__wrapped__", fn)
    return asyncio.run(fn(type("R", (), {})(), *a, **k))


@pytest.mark.parametrize("filtre", ["today", "week", "overdue", "priority", "completed",
                                    "archived", "in_progress", "blocked"])
def test_PG_filtreleri_COPTEKI_gorevi_gostermez_ve_metin_sirasi_kullanmaz(monkeypatch, filtre):
    conn = _yakala(monkeypatch)
    _cagir(todo_api.filter_tasks, filtre)
    sql = conn.sqller[-1]
    assert "deleted_at IS NULL" in sql, f"{filtre}: silinen görev de listeleniyor"
    assert "priority DESC" not in sql, f"{filtre}: öncelik metin olarak sıralanıyor (mid>low>high)"


def test_PG_arama_ve_istatistik_COPTEKI_gorevi_saymaz(monkeypatch):
    conn = _yakala(monkeypatch)
    _cagir(todo_api.search_tasks, "fatura")
    _cagir(todo_api.get_stats)
    assert all("deleted_at IS NULL" in s for s in conn.sqller), conn.sqller


def test_oncelik_sirasi_ifadesi_high_mid_low_dizer():
    """CASE ifadesi standart SQL — sqlite'ta koşturup sırayı ölç (metin DESC: mid, low, high)."""
    import sqlite3
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE t (priority TEXT)")
    c.executemany("INSERT INTO t VALUES (?)", [("low",), ("high",), ("mid",)])
    sira = [r[0] for r in c.execute(f"SELECT priority FROM t ORDER BY {todo_api._ONCELIK_SIRA.replace('t.', '')}")]
    assert sira == ["high", "mid", "low"]
    assert [r[0] for r in c.execute("SELECT priority FROM t ORDER BY priority DESC")] == ["mid", "low", "high"]

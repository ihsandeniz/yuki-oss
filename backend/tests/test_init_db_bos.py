"""init_db: boş veritabanında göçler atlanır, init.sql tam şemayı kurar (2026-11-14).

Gerçek Postgres ölçümü (tek kullanımlık pgvector:pg16): göçler var olan `memories` tablosunu
değiştirdiği için boş DB'de `relation "memories" does not exist` ile düşüyor, init.sql'e sıra
gelmiyordu → şema hiç kurulmuyordu. Bu test aynı sırayı sahte bağlantıyla ölçer (CI'da Postgres yok).
"""
import asyncio

import app.db.connection as c


class _Baglanti:
    def __init__(self, tablo_var):
        self.tablo_var, self.kosulan = tablo_var, []

    async def fetchval(self, sql):
        assert "to_regclass('memories')" in sql
        return "memories" if self.tablo_var else None

    async def execute(self, sql):
        self.kosulan.append(sql)


class _Havuz:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        havuz = self

        class _Ctx:
            async def __aenter__(self):
                return havuz.conn

            async def __aexit__(self, *a):
                return False
        return _Ctx()


def _kos(monkeypatch, tablo_var):
    conn = _Baglanti(tablo_var)

    async def _pool():
        return _Havuz(conn)
    monkeypatch.setattr(c, "get_pool", _pool)
    asyncio.run(c.init_db())
    return conn.kosulan


def _ad(sql):
    for yol in (c._MIGRATE_SCOPE_SQL, c._MIGRATE_CHAR_SQL, c._INIT_SQL):
        if sql == yol.read_text(encoding="utf-8"):
            return yol.name
    return "?"


def test_bos_veritabaninda_yalniz_init_sql(monkeypatch):
    assert [_ad(s) for s in _kos(monkeypatch, tablo_var=False)] == ["init.sql"]


def test_var_olan_tabloda_gocler_sonra_init_sql(monkeypatch):
    assert [_ad(s) for s in _kos(monkeypatch, tablo_var=True)] == [
        "migrate_scope.sql", "migrate_character.sql", "init.sql"]

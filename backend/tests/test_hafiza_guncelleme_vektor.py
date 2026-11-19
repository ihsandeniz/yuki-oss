"""Anı metni düzenlenince (PUT /api/memory/{id}) vektör de yenilenmeli (pgvector yolu).

Eskiden yalnız `content` değişiyordu; `embedding` eski metne ait kalıyordu: arama düzeltilmiş
anıyı eski anlamıyla buluyor, kopya birleştirme eski vektöre göre karar veriyordu.
SQLite yolu (memory_sqlite) bunu zaten yapıyor; bu test pgvector yolunu sınar.
Kişisel Yuki'deki aynı düzeltmenin yeniden yazımı. DB yok: sahte havuz.
"""
import asyncio

import pytest

import app.services.memory as M


class _Baglanti:
    def __init__(self, kayit):
        self.kayit = kayit

    async def execute(self, sql, *args):
        self.kayit.append((sql, args))
        return "UPDATE 1"


class _Havuz:
    def __init__(self):
        self.kayit = []

    def acquire(self):
        havuz = self

        class _Ctx:
            async def __aenter__(self_):
                return _Baglanti(havuz.kayit)

            async def __aexit__(self_, *a):
                return False
        return _Ctx()


@pytest.fixture
def havuz(monkeypatch):
    h = _Havuz()

    async def _get_pool():
        return h
    monkeypatch.setattr(M, "get_pool", _get_pool)
    monkeypatch.setattr(M, "_get_active_character", lambda: "yuki")
    return h


def test_icerik_degisince_vektor_yenilenir(havuz, monkeypatch):
    async def _embed(metin):
        assert metin == "Çay sevmem, kahve severim"
        return [0.5] * 384
    monkeypatch.setattr(M, "_embed", _embed)
    assert asyncio.run(M.MemoryService().update(7, content="Çay sevmem, kahve severim"))
    sql, args = havuz.kayit[-1]
    assert "embedding = $" in sql
    vek = [a for a in args if isinstance(a, str) and a.startswith("[")]
    assert len(vek) == 1 and vek[0].count(",") + 1 == 384


def test_yalniz_onem_degisince_vektor_dokunulmaz(havuz, monkeypatch):
    async def _embed(metin):
        raise AssertionError("önem güncellemesinde gömme çağrılmamalı")
    monkeypatch.setattr(M, "_embed", _embed)
    assert asyncio.run(M.MemoryService().update(7, importance=0.9))
    sql, _ = havuz.kayit[-1]
    assert "embedding" not in sql


def test_model_duserse_icerik_eski_vektorle_yazilmaz(havuz, monkeypatch):
    async def _embed(metin):
        raise OSError("model yok")
    monkeypatch.setattr(M, "_embed", _embed)
    assert asyncio.run(M.MemoryService().update(7, content="yeni metin")) is False
    assert havuz.kayit == []          # yeni metin + eski vektör çifti hiç oluşmaz

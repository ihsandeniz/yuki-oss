"""Gömülü sqlite-vec hafıza arka ucu testleri (gerçek embedding, izole tmp DB).

MemoryService (pgvector) ile arayüz paritesi + KNN doğruluğu + karakter izolasyonu
+ hibrit skor + CRUD + dedup + cleanup + consolidate.
"""
from __future__ import annotations

import pytest

from app.services import memory_sqlite as ms


@pytest.fixture
def svc(tmp_path, monkeypatch):
    """Her test için taze sqlite-vec DB (tmp) + sıfırlanmış bağlantı."""
    monkeypatch.setattr(ms, "MEMORY_DB_PATH", str(tmp_path / "mem.db"))
    ms._conn = None  # yeni DB'ye bağlan
    yield ms.SqliteVecMemoryService()
    try:
        if ms._conn:
            ms._conn.close()
    finally:
        ms._conn = None


async def test_add_count_recent(svc):
    i1 = await svc.add("Merhaba nasılsın", role="user", character_key="yuki")
    i2 = await svc.add("İyiyim teşekkürler", role="assistant", character_key="yuki")
    assert i1 and i2 and i2 > i1
    assert await svc.count(character_key="yuki") == 2
    recent = await svc.get_recent(character_key="yuki")
    assert [m.content for m in recent] == ["Merhaba nasılsın", "İyiyim teşekkürler"]  # kronolojik


async def test_search_semantic_ranking(svc):
    await svc.add("İpek bir yazılım geliştiricisi ve Arch Linux kullanıyor",
                  category="fact", scope="fact", importance=0.8, character_key="yuki")
    await svc.add("Bugün hava çok güzel ve güneşli", character_key="yuki")
    res = await svc.search("İpek'in mesleği nedir", limit=2, min_similarity=0.0, character_key="yuki")
    assert res, "arama sonuç döndürmeli"
    assert "geliştirici" in res[0].content  # en alakalı ilk sırada
    assert 0.0 < res[0].similarity <= 1.0


async def test_character_isolation(svc):
    await svc.add("Yuki'nin özel anısı", character_key="yuki")
    # başka bir karakter anahtarıyla arama → yuki'nin anısını GÖRMEZ
    res_diger = await svc.search("özel anı", min_similarity=0.0, character_key="diger")
    assert res_diger == []
    # cross_character=True → tüm karakterler taranır
    res_all = await svc.search("özel anı", min_similarity=0.0, character_key="diger", cross_character=True)
    assert any("Yuki" in m.content for m in res_all)


async def test_min_similarity_filter(svc):
    await svc.add("Kuantum fiziği ve kara delikler", character_key="yuki")
    # tamamen alakasız sorgu + yüksek eşik → boş
    res = await svc.search("makarna tarifi nasıl yapılır", min_similarity=0.95, character_key="yuki")
    assert res == []


async def test_update_reembed(svc):
    mid = await svc.add("eski içerik", importance=0.5, character_key="yuki")
    ok = await svc.update(mid, importance=0.9, content="tamamen yeni içerik hakkında", character_key="yuki")
    assert ok
    # güncellenen içerik aranınca bulunmalı (yeni embedding)
    res = await svc.search("yeni içerik", min_similarity=0.0, character_key="yuki")
    assert res and res[0].content == "tamamen yeni içerik hakkında"
    assert res[0].importance == 0.9


async def test_delete_removes_from_both_tables(svc):
    mid = await svc.add("silinecek anı", character_key="yuki")
    assert await svc.delete(mid, character_key="yuki")
    assert await svc.count(character_key="yuki") == 0
    # vec tablosundan da gitti → arama boş
    res = await svc.search("silinecek", min_similarity=0.0, character_key="yuki")
    assert res == []
    # tekrar silme False
    assert await svc.delete(mid, character_key="yuki") is False


async def test_add_batch_dedup(svc):
    ids = await svc.add_batch([
        {"content": "tekrar eden", "role": "user"},
        {"content": "tekrar eden", "role": "user"},   # in-batch dup
        {"content": "farklı olan", "role": "user"},
    ], character_key="yuki")
    assert len(ids) == 2
    assert await svc.count(character_key="yuki") == 2


async def test_cleanup_preserves_facts(svc):
    from datetime import datetime, timedelta
    # eski + düşük önem conversation (silinmeli) — created_at'i elle geçmişe çek
    cid = await svc.add("önemsiz eski sohbet", importance=0.1, character_key="yuki")
    fid = await svc.add("kalıcı gerçek", importance=0.1, category="fact", scope="fact", character_key="yuki")
    old = (datetime.now() - timedelta(days=30)).isoformat()
    ms._conn.execute("UPDATE memories SET created_at=? WHERE id IN (?,?)", (old, cid, fid))
    ms._conn.commit()
    removed = await svc.cleanup(importance_threshold=0.35, days_old=7, character_key="yuki")
    assert removed == 1  # sadece conversation
    remaining = await svc.list_all(character_key="yuki")
    assert len(remaining) == 1 and remaining[0].scope == "fact"


async def test_clear_conversations_keeps_facts_and_vectors_clean(svc):
    """clear_history'nin sqlite yolu: conversation gider, fact kalır, vec yetim kalmaz."""
    await svc.add("bugün hava güzel", character_key="yuki")
    await svc.add("dün sinemaya gittik", character_key="yuki")
    await svc.add("kullanıcının kedisi Pamuk", category="fact", scope="fact", character_key="yuki")
    removed = await svc.clear_conversations(character_key="yuki")
    assert removed == 2
    remaining = await svc.list_all(character_key="yuki")
    assert len(remaining) == 1 and remaining[0].category == "fact"
    # vec tablosunda yetim vektör kalmamalı (memories ile birebir)
    n_vec = ms._conn.execute("SELECT COUNT(*) FROM vec_memories").fetchone()[0]
    n_mem = ms._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    assert n_vec == n_mem == 1
    # silinen içerik artık aramada dönmemeli
    hits = await svc.search("sinema", limit=5, min_similarity=0.0, character_key="yuki")
    assert all("sinema" not in h.content for h in hits)


async def test_consolidate_facts(svc):
    await svc.add("İpek Arch Linux kullanıyor", category="fact", scope="fact", character_key="yuki")
    await svc.add("İpek Arch Linux kullanıyor", category="fact", scope="fact", character_key="yuki")  # ~aynı
    await svc.add("İpek kahveyi severmiş", category="preference", scope="preference", character_key="yuki")
    removed = await svc.consolidate_facts(threshold=0.9, character_key="yuki")
    assert removed == 1  # bir yinelenen silindi
    assert await svc.count(character_key="yuki") == 2


async def test_stats(svc):
    await svc.add("a", scope="fact", category="fact", importance=0.8, character_key="yuki")
    await svc.add("b", scope="conversation", importance=0.4, character_key="yuki")
    st = await svc.stats(character_key="yuki")
    assert st["total"] == 2
    assert st["scopes"]["fact"]["count"] == 1
    assert st["character_key"] == "yuki"


async def test_reinforce(svc):
    mid = await svc.add("güçlenecek", importance=0.5, character_key="yuki")
    await svc.reinforce([mid], delta=0.2, character_key="yuki")
    res = await svc.list_all(character_key="yuki")
    assert abs(res[0].importance - 0.7) < 1e-6

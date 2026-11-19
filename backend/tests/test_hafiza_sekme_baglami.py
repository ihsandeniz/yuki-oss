"""Sekme bağlamı hafızaya girmez + Yuki'nin cevabı/soru "bilgi" sayılmaz (2026-09-27).

Arayüz her mesaja Yuki için gizli [TAB_CONTEXT …] bloğu ekliyor (`uptime-display` hep dolu →
blok HER mesajda). Ölçüldü: müşteri yolunda (sqlite-vec) 3 kullanıcı kaydının 3'ü blokla
yazılıyordu, blok "naber"i bile 20 karakter eşiğinin üstüne çıkarıp her mesajda ek bir fact
çıkarım LLM çağrısı tetikliyordu; soru "tercih", Yuki'nin onayı "bilgi" diye kaydediliyordu.
Kişisel AliceAi 4f6d9a6 + cbbc581'in ürün karşılığı — üründe kapı İKİ serviste olmalı.
"""
from __future__ import annotations

import inspect

import pytest

from app.api import websocket
from app.services import llm, memory, memory_sqlite as ms
from app.services.memory import sekme_baglamini_ayikla

BLOK = "\n\n[TAB_CONTEXT — sadece sen gör, yanıtta açıkça söyleme]\nSistem: Uptime=00:06:35\n[/TAB_CONTEXT]"


def test_blok_cikarilir_mesaj_kalir():
    assert sekme_baglamini_ayikla("naber yuki" + BLOK) == "naber yuki"


def test_kapanmamis_blok_da_cikarilir():
    assert sekme_baglamini_ayikla("benim adım Deniz\n\n[TAB_CONTEXT — x]\nSistem: CPU=") == "benim adım Deniz"


def test_blok_disi_metne_dokunulmaz():
    for m in ("normal mesaj", "çok\nsatırlı\nmesaj", "", "TAB_CONTEXT kelimesi köşeli parantezsiz"):
        assert sekme_baglamini_ayikla(m) == m


def test_llm_ayiklayicisi_ayni_kaynak():
    # Lite geçmiş temizliği ile hafıza kapısı aynı deseni kullanmalı — ayrışırsa biri kaçırır
    assert llm._strip_tab_context("x" + BLOK) == "x"
    assert "sekme_baglamini_ayikla" in inspect.getsource(llm._strip_tab_context)


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "MEMORY_DB_PATH", str(tmp_path / "mem.db"))
    ms._conn = None
    yield ms.SqliteVecMemoryService()
    try:
        if ms._conn:
            ms._conn.close()
    finally:
        ms._conn = None


async def test_sqlite_add_bloksuz_yazar(svc):
    rid = await svc.add("Yuki benim adım Deniz" + BLOK, character_key="yuki")
    assert rid
    assert [m.content for m in await svc.get_recent(character_key="yuki")] == ["Yuki benim adım Deniz"]
    assert await svc.add(BLOK.strip(), character_key="yuki") is None  # yalnız bloktan oluşan: yazılmaz


async def test_sqlite_add_batch_bloksuz_yazar(svc):
    await svc.add_batch([
        {"content": "merhaba" + BLOK, "role": "user"},
        {"content": BLOK.strip(), "role": "user"},
    ], character_key="yuki")
    assert [m.content for m in await svc.get_recent(character_key="yuki")] == ["merhaba"]


def test_pgvector_iki_yazma_yolu_da_ayikliyor():
    # Yapı testi: pgvector yolu testte sahte havuzla koşuyor; kapı unutulursa sızıntı sessizce döner
    assert "sekme_baglamini_ayikla(content)" in inspect.getsource(memory.MemoryService.add)
    assert "sekme_baglamini_ayikla(" in inspect.getsource(memory.MemoryService.add_batch)


def test_ogren_dali_bloku_kesiyor():
    kaynak = inspect.getsource(websocket)
    assert kaynak.index("sekme_baglamini_ayikla(user_text)") < kaynak.index("startswith(_OGREN_ONEKLERI)")


async def test_save_exchange_kapsamlari(svc, monkeypatch):
    cikarim: list[str] = []

    async def _say(msg):
        cikarim.append(msg)

    monkeypatch.setattr(llm, "_semantic_active", lambda: True)
    monkeypatch.setattr(llm, "_extract_facts_background", _say)
    monkeypatch.setattr(memory, "get_memory_service", lambda: svc)
    monkeypatch.setattr(ms, "_get_active_character", lambda: "yuki")

    await llm._save_exchange("naber" + BLOK, "İyiyim, sen?")
    await llm._save_exchange("En sevdiğim renk ne?" + BLOK, "Bilmiyorum, söyler misin?")
    await llm._save_exchange("benim adım Deniz" + BLOK, "Adını kaydettim, Deniz!")

    # get_recent yalnız 'conversation' kategorisini döndürür — tabloyu doğrudan oku
    kayit = [tuple(r) for r in ms._get_conn().execute(
        "SELECT role, scope, content FROM memories ORDER BY id").fetchall()]
    assert kayit == [
        ("user", "conversation", "naber"),
        ("assistant", "conversation", "İyiyim, sen?"),
        ("user", "conversation", "En sevdiğim renk ne?"),        # soru bilgi değil
        ("assistant", "conversation", "Bilmiyorum, söyler misin?"),
        ("user", "fact", "benim adım Deniz"),                     # gerçek bilgi hâlâ fact
        ("assistant", "conversation", "Adını kaydettim, Deniz!"),  # onay bilgi değil
    ]
    assert cikarim == []  # blok "naber"i 20 karakter eşiğinin üstüne taşımıyor


# ── Eski kayıtların tek seferlik temizliği (müşteri memory.db'si, açılışta) ──────────

async def _eski_surum_yazar(svc, satirlar):
    """1e508d4 öncesi sürümün yazdığı gibi: içerik olduğu gibi, vektör o içerikten."""
    conn = ms._get_conn()
    for rol, kat, kapsam, onem, icerik in satirlar:
        vec = await ms._embed(icerik)
        cur = conn.execute(
            "INSERT INTO memories (session_id, role, content, category, importance, created_at, scope, character_key) "
            "VALUES ('default',?,?,?,?,'2026-09-01T10:00:00',?,'yuki')",
            (rol, icerik, kat, onem, kapsam),
        )
        conn.execute("INSERT INTO vec_memories(memory_id, character_key, embedding) VALUES (?,?,?)",
                     (cur.lastrowid, "yuki", ms._serialize(vec)))
    conn.commit()


ESKI = [
    ("user", "fact", "fact", 0.75, "benim adım Deniz" + BLOK),            # blok kesilir, fact kalır
    ("user", "conversation", "conversation", 0.5, BLOK.strip()),           # yalnız blok → silinir
    ("assistant", "fact", "fact", 0.7, "Adını kaydettim, Deniz!"),         # cevap → konuşma
    ("user", "preference", "preference", 0.8, "En sevdiğim renk ne?" + BLOK),  # blok gidince soru → konuşma
    ("user", "conversation", "skill", 0.8, "git rebase nasıl yapılır?"),   # /öğren satırı: DOKUNULMAZ
    ("user", "preference", "preference", 0.85, "Kullanıcı kahveyi sever"), # fact çıkarımı: DOKUNULMAZ
]


def _tablo():
    return [tuple(r) for r in ms._get_conn().execute(
        "SELECT role, category, scope, content FROM memories ORDER BY id").fetchall()]


async def test_temizlik_eski_kayitlari_duzeltir(svc, tmp_path):
    await _eski_surum_yazar(svc, ESKI)
    sonuc = await svc.sekme_baglami_temizle()

    assert _tablo() == [
        ("user", "fact", "fact", "benim adım Deniz"),
        ("assistant", "conversation", "conversation", "Adını kaydettim, Deniz!"),
        ("user", "conversation", "conversation", "En sevdiğim renk ne?"),
        ("user", "conversation", "skill", "git rebase nasıl yapılır?"),
        ("user", "preference", "preference", "Kullanıcı kahveyi sever"),
    ]
    assert (sonuc["blok_temizlendi"], sonuc["silindi"], sonuc["cevap_konusma"], sonuc["soru_konusma"]) == (2, 1, 1, 1)
    conn = ms._get_conn()
    assert conn.execute("SELECT COUNT(*) FROM vec_memories").fetchone()[0] == 5  # silinenin vektörü de gitti
    # Vektör temiz metinden: kendi metniyle aranınca ~1 benzerlik
    bulunan = await svc.search("benim adım Deniz", limit=1, min_similarity=0.0, character_key="yuki")
    assert bulunan[0].content == "benim adım Deniz" and bulunan[0].similarity > 0.99

    # Yedek: değişiklikten önceki tam kopya
    import sqlite3
    yedekler = list((tmp_path / "yedek").glob("hafiza-sekme-*.db"))
    assert len(yedekler) == 1
    eski = sqlite3.connect(yedekler[0]).execute("SELECT COUNT(*) FROM memories WHERE content LIKE '%[TAB_CONTEXT%'").fetchone()[0]
    assert eski == 3  # Deniz · yalnız-blok · soru

    # Tekrarsız: ikinci açılış hiçbir şey yazmaz, yeni yedek almaz
    assert await svc.sekme_baglami_temizle() == {}
    assert len(list((tmp_path / "yedek").glob("*.db"))) == 1


async def test_hafizasiz_kurulumda_veritabani_yaratmaz(tmp_path, monkeypatch):
    yol = tmp_path / "yok.db"
    monkeypatch.setattr(ms, "MEMORY_DB_PATH", str(yol))
    ms._conn = None
    assert await ms.SqliteVecMemoryService().sekme_baglami_temizle() == {}
    assert not yol.exists()


async def test_yazim_yarida_kalirsa_geri_alinir(svc, monkeypatch):
    await _eski_surum_yazar(svc, ESKI)
    once = _tablo()

    def _patla(_v):
        raise RuntimeError("yazım ortasında hata")

    monkeypatch.setattr(ms, "_serialize", _patla)
    with pytest.raises(RuntimeError):
        await svc.sekme_baglami_temizle()
    monkeypatch.undo()
    ms._get_conn().commit()  # sıradan bir sonraki yazım: yarım temizliği diske işlememeli
    assert _tablo() == once


def test_iki_arka_uc_da_acilista_temizleniyor():
    # pgvector yolu testte sahte havuzla koşuyor (canlı ölçüm: olcum/hafiza_uctan_uca_olc.py).
    # Yapı kapısı: iki servis de temizliği taşımalı, açılış çağrısı arka uca göre süzülmemeli.
    from app import main
    assert inspect.iscoroutinefunction(memory.MemoryService.sekme_baglami_temizle)
    assert inspect.iscoroutinefunction(ms.SqliteVecMemoryService.sekme_baglami_temizle)
    kaynak = inspect.getsource(main)
    blok = kaynak[kaynak.index("async def _warm_embedding_task"):kaynak.index("_warm_embedding_task())")]
    assert "sekme_baglami_temizle()" in blok and 'MEMORY_BACKEND == "sqlite"' not in blok

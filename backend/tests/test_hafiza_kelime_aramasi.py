"""HAFIZA · DOSYA — kelime araması (`GET /api/memory?q=`) ve konuşma sırası.

Anlamca arama (`/search`, eşik 0.3) kısa satırlara ("sa", "selam") her sorguda
yüksek benzerlik veriyordu (kişiselde ölçüldü 09-26: "programlama dili" → 50 sonuç,
çoğu selam). Panel önce içerikte birebir geçenlere bakar.

Müşteri yolu sqlite: `LIKE` yalnız ASCII'de harf duyarsız — "İstanbul" "istanbul"
ile eşleşmezdi. Kural `memory.arama_katla`'da tek yerde, iki backend de onu kullanır.
"""
from __future__ import annotations

import inspect

import pytest

from app.api import memory as memory_api
from app.services import memory, memory_sqlite as ms
from app.services.memory import arama_kalibi, arama_katla


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


@pytest.mark.parametrize("girdi,beklenen", [
    ("İstanbul", "istanbul"), ("ISTANBUL", "istanbul"), ("ılık IŞIK", "ilik isik"), ("Çay Şeker Süt Öğle", "cay seker sut ogle"),
])
def test_katlama_turkce_harfleri_esitler(girdi, beklenen):
    assert arama_katla(girdi) == beklenen


def test_kalip_joker_harfleri_kacirir():
    assert arama_kalibi("%50_x") == r"%\%50\_x%"


async def _doldur(svc):
    for metin in ("İstanbul'da yaşıyorum", "%100 eminim bundan", "selam", "sa", "Işık açık kalsın"):
        await svc.add(metin, category="fact", character_key="yuki")


@pytest.mark.parametrize("q,beklenen", [
    ("istanbul", ["İstanbul'da yaşıyorum"]),     # İ ↔ i
    ("ISTANBUL", ["İstanbul'da yaşıyorum"]),     # I ↔ i
    ("ışık", ["Işık açık kalsın"]),              # I ↔ ı
    ("ISIK", ["Işık açık kalsın"]),              # aksansız klavye: S ↔ Ş (09-27 canlıda bulunamıyordu)
    ("yasiyorum", ["İstanbul'da yaşıyorum"]),
    ("%1", ["%100 eminim bundan"]),              # % joker değil
    ("programlama", []),                          # anlamca yakın "sa"/"selam" gelmez
])
async def test_sqlite_kelime_aramasi(svc, q, beklenen):
    await _doldur(svc)
    bulunan = [m.content for m in await svc.list_all(character_key="yuki", icerik=q)]
    assert bulunan == beklenen


async def test_sqlite_aramasiz_liste_degismedi(svc):
    await _doldur(svc)
    assert len(await svc.list_all(character_key="yuki")) == 5


def test_pgvector_ayni_kurali_ve_kacisi_kullaniyor():
    # pgvector yolu testte sahte havuzla koşuyor → yapı testi
    kaynak = inspect.getsource(memory.MemoryService.list_all)
    assert "arama_kalibi(icerik)" in kaynak
    assert "translate(content, '{_TR_HARF}', '{_TR_ASCII}')" in kaynak and "ESCAPE" in kaynak
    assert len(memory._TR_HARF) == len(memory._TR_ASCII)  # translate harf harf eşler


def test_pgvector_esit_zamanda_id_ile_siralar():
    """add_batch kullanıcı + Yuki satırını tek işlemde yazar → created_at eşit.
    İkinci sıralama yoksa sohbet geçmişinde soru ile cevap yer değiştirebilir."""
    for fn in (memory.MemoryService.list_all, memory.MemoryService.get_recent):
        assert "ORDER BY created_at DESC, id DESC" in inspect.getsource(fn), fn.__name__


def test_uc_q_parametresini_iletiyor():
    kaynak = inspect.getsource(memory_api.list_memories)
    assert "max_length=200" in kaynak and "icerik=" in kaynak

"""'/öğren' ve memory_search aracı gömme modeli yokken yalan söylemesin.

Model yokken (`MEMORY_BACKEND=sqlite`, `EMBED_ONNX_DIR` yok — README ve ./start.sh yolu)
`/öğren` komutu `add()` patlasa da "Öğrendim ✦" diyordu, hiçbir şey kaydedilmiyordu;
memory_search aracı da ham ModuleNotFoundError metnini dönüyordu.
"""
import inspect

import pytest

from app.api import websocket
from app.mesajlar import M
from app.services.tools import memory_tools


class _Servis:
    def __init__(self, hata=None):
        self.eklenen = []
        self.hata = hata

    async def add(self, fact, **kw):
        if self.hata:
            raise self.hata
        self.eklenen.append((fact, kw))
        return 1

    async def search(self, *a, **kw):
        raise AssertionError("model yokken aramaya inilmemeli")


@pytest.fixture
def servis(monkeypatch):
    s = _Servis()
    monkeypatch.setattr("app.services.memory.get_memory_service", lambda: s)
    return s


@pytest.mark.asyncio
async def test_modelsiz_ogren_ogrendim_demez(monkeypatch, servis):
    monkeypatch.setattr("app.services.llm._embedding_engine_ready", lambda: False)
    metin = await websocket._ogren_kaydet("kahveyi sade severim")
    assert metin == M("ogren.model-yok")
    assert "EMBED_ONNX_DIR" in metin
    assert servis.eklenen == [], "model yokken servise yazılmaya çalışıldı"


@pytest.mark.asyncio
async def test_kayit_patlarsa_ogrendim_demez(monkeypatch, servis):
    monkeypatch.setattr("app.services.llm._embedding_engine_ready", lambda: True)
    servis.hata = ModuleNotFoundError("No module named 'sentence_transformers'")
    metin = await websocket._ogren_kaydet("kahveyi sade severim")
    assert metin == M("ogren.kaydedilemedi")
    assert "Öğrendim" not in metin


@pytest.mark.asyncio
async def test_model_varken_kaydeder_ve_ogrendim_der(monkeypatch, servis):
    monkeypatch.setattr("app.services.llm._embedding_engine_ready", lambda: True)
    metin = await websocket._ogren_kaydet("kahveyi sade severim")
    assert metin == M("ogren.kaydedildi", bilgi="kahveyi sade severim")
    assert servis.eklenen[0][0] == "kahveyi sade severim"
    assert servis.eklenen[0][1]["scope"] == "skill"


def test_ogren_dali_yardimciyi_kullaniyor():
    """WS döngüsü kendi add() çağrısını yeniden yazarsa kapı sessizce devre dışı kalır."""
    kaynak = inspect.getsource(websocket)
    dal = kaynak[kaynak.index("_ut.lower().startswith(_OGREN_ONEKLERI)"):]
    dal = dal[:dal.index("continue")]
    assert "_ogren_kaydet(fact)" in dal
    assert "ogren.kaydedildi" not in dal, "başarı metni kapının dışında üretiliyor"


@pytest.mark.asyncio
async def test_modelsiz_memory_search_ham_hata_dondurmez(monkeypatch, servis):
    monkeypatch.setattr("app.config.MEMORY_ENABLED", True)
    monkeypatch.setattr("app.services.llm._embedding_engine_ready", lambda: False)
    sonuc = await memory_tools.memory_search("kedi")
    assert "EMBED_ONNX_DIR" in sonuc
    assert "Hata" not in sonuc and "ModuleNotFoundError" not in sonuc

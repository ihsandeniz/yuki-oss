"""Yüz: aynı adın farklı yazımı ikinci "kişi" olmaz · sahip karşılaştırması yazımdan bağımsız ·
sahibi silmek açık onay ister (2026-09-27).

Kişisel AliceAi 295059d + 517e975'in ürün karşılığı. Ürün kodunda (09-27 okundu) kayıt ve sahip
doğrulaması adı birebir `==` ile, silme `.lower()` ile karşılaştırıyordu — `"İpek".lower()` =
"i̇pek" ≠ "ipek". Sahibi silmek tek dokunuşla yüzle girişi SESSİZCE kapatıyordu.
Depo conftest'te geçici dizinde (canli_dosyaya_yazmasin).
"""
import numpy as np
import pytest
from starlette.testclient import TestClient

from app.services import face_multi_auth as fma
from app.services import face_store


@pytest.fixture(autouse=True)
def temiz():
    face_store._sifirla()
    yield
    face_store._sifirla()


def _emb(tohum: int) -> np.ndarray:
    v = np.random.default_rng(tohum).normal(size=512).astype(np.float32)
    return v / np.linalg.norm(v)


@pytest.mark.parametrize("a,b", [("ipek", "İpek"), ("İPEK", "ipek"), ("  İpek ", "ipek"), ("Işık", "ışık")])
def test_ayni_ad_farkli_yazim_ayni_anahtar(a, b):
    assert fma.ad_anahtari(a) == fma.ad_anahtari(b)


def test_farkli_adlar_ayrisir():
    assert fma.ad_anahtari("Işık") != fma.ad_anahtari("isik"), "Türkçe'de ı ile i ayrı harf"
    assert fma.ad_anahtari("ipek") != fma.ad_anahtari("ipeke")


@pytest.mark.anyio
async def test_kayit_var_olan_yazima_ekler(monkeypatch):
    """Davranış: 'İpek' kayıtlıyken 'ipek' adıyla gelen kare İpek'e eklenir, ikinci kişi olmaz.
    (Kişiseldeki kapı kaynak metne bakıyordu — `if esi:` bozulsa da yeşildi, 09-27 mutasyonla görüldü.)"""
    face_store.ekle("İpek", _emb(5))

    async def _analiz(_veri):
        return type("A", (), {"embedding": _emb(6), "yuz_sayisi": 1, "bbox": None})()
    monkeypatch.setattr(fma, "analiz_et", _analiz)
    r = await fma.register_face("ipek", b"\xff\xd8sahte")
    assert face_store.benzersiz_kisiler() == {"İpek"}, "ikiz kişi oluştu"
    assert r["name"] == "İpek" and face_store.kisi_kayit_sayisi("İpek") == 2


def test_sahip_kayitli_sayimi_yazimdan_bagimsiz():
    face_store.ekle("ipek", _emb(1))
    face_store.sahip_yaz("İpek")
    assert fma.owner_enrolled() is True


@pytest.mark.anyio
async def test_sahip_girisi_yazimdan_bagimsiz(monkeypatch):
    monkeypatch.setattr(fma, "get_owner", lambda: "İpek")
    import app.config as cfg
    monkeypatch.setattr(cfg, "FACE_LIVENESS_REQUIRED", False, raising=False)

    async def _analiz(_veri):
        return object()
    monkeypatch.setattr(fma, "analiz_et", _analiz)
    monkeypatch.setattr(fma, "_tani", lambda a: {"known": True, "name": "ipek", "verdict": "high",
                                                 "distance": 0.2, "margin": 0.3})
    r = await fma.verify_owner([b"\xff\xd8sahte"], None, "127.0.0.1")
    assert r["ok"] is True, r


@pytest.mark.anyio
async def test_sahibi_silmek_onay_ister_yazim_farkli_olsa_da():
    face_store.ekle("ipek", _emb(2))
    face_store.sahip_yaz("İpek")
    with pytest.raises(fma.SahipSilmeOnayi):
        await fma.delete_face("ipek")
    assert face_store.kisi_kayit_sayisi("ipek") == 1 and fma.get_owner() == "İpek", "onaysız hiçbir şey silinmemeli"
    await fma.delete_face("ipek", sahip_onay=True)
    assert not fma.get_owner() and face_store.kisi_kayit_sayisi("ipek") == 0


def test_uc_sahip_icin_409_onayla_siler(monkeypatch):
    from app.api import face_api
    from app.main import app
    monkeypatch.setattr(face_api, "_kapali_mi", lambda: None)
    face_store.ekle("sahip", _emb(3))
    face_store.ekle("misafir", _emb(4))
    face_store.sahip_yaz("sahip")
    c = TestClient(app)
    assert c.delete("/api/face/misafir").status_code == 200, "sahip olmayan onaysız silinir"
    assert c.delete("/api/face/sahip").status_code == 409
    assert c.delete("/api/face/sahip?sahip=1").status_code == 200
    assert not fma.get_owner()

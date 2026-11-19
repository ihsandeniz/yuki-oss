"""HARİTA › GÜNDEM kümeleme — aynı olayın farklı kaynaklardaki başlıkları tek satır olur.

Saf fonksiyon (`services/gundem_kume.py`) + `/api/map/news` ucuna bağlantısı. Ağ yok: RSS çekimi
sahte `resilient` ile değiştirilir. Ölçülen kurallar:
- aynı olay → tek küme, temsilci akıştaki İLK başlık, kaynaklar tekrarsız sayılır
- yalnız tek sık kelime ("dolar") ortak olan iki haber birleşmez
- kümeleme çökerse ya da `GUNDEM_KUME=0` ise ham liste döner (haber kaybolmaz)
- uçtaki `limit` kümelemeden SONRA uygulanır (aynı olay 6 satırın 3'ünü yemez)
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import gundem_kume as G

FAIZ = [
    "Merkez Bankası faiz kararını açıkladı: politika faizi yüzde 40'ta sabit - Haber A",
    "Merkez Bankası politika faizini yüzde 40'ta sabit bıraktı - Haber B",
    "Merkez Bankası faiz kararı belli oldu, politika faizi sabit kaldı - Haber C",
]
BASKA = [
    "İstanbul'da yarın yoğun kar yağışı bekleniyor - Hava D",
    "Deplasmanda 2-1 kazanan takım liderliğe yükseldi - Spor E",
]


# ── saf fonksiyon ──────────────────────────────────────────────────────────

def test_ayni_olay_tek_kume_ve_kaynaklar_sayilir():
    k = G.kumele(FAIZ + BASKA)
    assert len(k) == 3, [x["title"] for x in k]
    assert k[0]["title"] == FAIZ[0], "temsilci akıştaki ilk başlık olmalı"
    assert k[0]["kaynaklar"] == ["Haber A", "Haber B", "Haber C"]
    assert k[0]["kaynak_sayisi"] == 3
    assert k[0]["basliklar"] == FAIZ


def test_sira_korunur():
    k = G.kumele([BASKA[0]] + FAIZ + [BASKA[1]])
    assert [x["title"] for x in k] == [BASKA[0], FAIZ[0], BASKA[1]]


def test_tek_sik_kelime_birlestirmez():
    k = G.kumele([
        "Dolar kritik eşiği aştı - Ekonomi F",
        "Otomotiv ihracatı 4 milyar dolar eşiğini aştı - Ekonomi G",
    ])
    assert len(k) == 2


def test_iki_ortak_kok_yetmez_oran_yuksek_olsa_da():
    """Kısa iki başlık 2 kökü paylaşınca Dice eşiği aşar (≈0,67); ayrı olaydır, en az 3 ortak kök şart."""
    k = G.kumele(["Altın fiyatları yükseldi - Ekonomi H", "Konut fiyatları yükseldi - Ekonomi I"])
    assert len(k) == 2


def test_kaynak_eki_yoksa_kaynak_bos_sayi_bir():
    k = G.kumele(["Kaynak eki olmayan uzun bir haber başlığı burada"])
    assert k[0]["kaynaklar"] == [] and k[0]["kaynak_sayisi"] == 1


def test_ayni_kaynak_iki_kez_sayilmaz():
    k = G.kumele([FAIZ[0], FAIZ[1].replace("Haber B", "Haber A")])
    assert len(k) == 1
    assert k[0]["kaynaklar"] == ["Haber A"] and k[0]["kaynak_sayisi"] == 1


def test_bos_ve_cop_girdi():
    assert G.kumele([]) == []
    assert len(G.kumele([None, "", "  "])) == 3   # düşürmez; süzgeç ön yüzün işi


def test_baslik_ayir_ve_turkce_kucuk_harf():
    assert G.baslik_ayir("Bir olay oldu - Kaynak X") == ("Bir olay oldu", "Kaynak X")
    assert G.baslik_ayir("Kaynaksız bir başlık") == ("Kaynaksız bir başlık", "")
    assert "istan" in G.kokler("İSTANBUL'DA büyük toplantı")
    assert "ırmak" in G.kokler("IRMAK taştı")


def test_kesme_eki_kokten_atilir():
    assert G.kokler("Ankara'dan") == G.kokler("Ankara")


# ── uç: /api/map/news ──────────────────────────────────────────────────────

@pytest.fixture
def istemci(monkeypatch):
    from app.api import map as map_api
    akis = {"items": [{"title": t} for t in FAIZ + BASKA + [
        "Belediye otobüs hatlarında yeni tarife yürürlüğe girdi - K1",
        "Üniversite sınavı başvuru tarihleri duyuruldu - K2",
        "Ege açıklarında 4,1 büyüklüğünde deprem - K3",
        "Ulusal parkta yangın kontrol altına alındı - K4",
        "Müze kartı fiyatlarına zam geldi - K5",
        "Köprü bakım çalışması nedeniyle trafik akışı değişti - K6"]]}
    akis["count"] = len(akis["items"])

    async def _sahte(anahtar, ttl, fetcher, **k):
        return dict(akis)
    monkeypatch.setattr(map_api, "resilient", _sahte)
    app = FastAPI()
    app.include_router(map_api.router)
    app.dependency_overrides[map_api.require_map] = lambda: None
    with TestClient(app) as c:
        yield c


def test_uc_kumeli_doner_limit_kumeden_sonra(istemci, monkeypatch):
    monkeypatch.delenv("GUNDEM_KUME", raising=False)
    d = istemci.get("/api/map/news?limit=6").json()
    assert d["count"] == 6 == len(d["items"])
    assert d["items"][0]["title"] == FAIZ[0]
    assert d["items"][0]["kaynak_sayisi"] == 3
    assert d["items"][0]["kaynaklar"] == ["Haber A", "Haber B", "Haber C"]
    basliklar = [i["title"] for i in d["items"]]
    assert FAIZ[1] not in basliklar and FAIZ[2] not in basliklar
    assert BASKA[0] in basliklar and BASKA[1] in basliklar


def test_uc_bayrak_kapaliyken_ham_liste(istemci, monkeypatch):
    monkeypatch.setenv("GUNDEM_KUME", "0")
    d = istemci.get("/api/map/news?limit=6").json()
    assert [i["title"] for i in d["items"]][:3] == FAIZ
    assert "kaynak_sayisi" not in d["items"][0]


def test_uc_kumeleme_cokerse_ham_liste(istemci, monkeypatch):
    monkeypatch.delenv("GUNDEM_KUME", raising=False)

    def _patla(*a, **k):
        raise ValueError("bozuk")
    monkeypatch.setattr(G, "kumele", _patla)
    r = istemci.get("/api/map/news?limit=6")
    assert r.status_code == 200
    assert [i["title"] for i in r.json()["items"]][:3] == FAIZ


def test_uc_hata_sozlugunu_bozmaz(monkeypatch):
    """resilient hata sözlüğü dönerse (items yok) uç onu olduğu gibi geçirir."""
    from app.api import map as map_api

    async def _hata(*a, **k):
        return {"error": "x"}
    monkeypatch.setattr(map_api, "resilient", _hata)
    app = FastAPI()
    app.include_router(map_api.router)
    app.dependency_overrides[map_api.require_map] = lambda: None
    with TestClient(app) as c:
        assert c.get("/api/map/news").json() == {"error": "x"}

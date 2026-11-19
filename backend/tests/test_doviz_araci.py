"""`get_exchange_rate` — Frankfurter v2 cevap şekli testleri.

Kusur (2026-08-05 geliştiricinin Free turunda bulundu, 2026-08-09'da kapandı):
Frankfurter `/v2/rates` **liste** döndürüyor (`[{date, base, quote, rate}, …]`),
kod ise v1'in `{"rates": {…}}` sözlüğünü okuyordu → `'list' object has no
attribute 'get'`. Müşteri "dolar kaç TL" diye sorunca cevap alamıyordu —
**Free sürümün ilan ettiği 20 araçtan biri ölüydü.**

Ölçüm (2026-08-09, gerçek API):
  v2 → [{"date":"2026-08-08","base":"USD","quote":"EUR","rate":0.86612}, …]
  v1 → {"amount":1.0,"base":"USD","date":"2026-08-07","rates":{"EUR":0.86693}}
v1 hâlâ ayakta ama bir gün bayat → URL v2'de kalıyor, iki şekil de kabul ediliyor.

Testler ağa ÇIKMAZ (httpx.AsyncClient taklit edilir).
"""

import pytest

from app.services.tools.data import get_exchange_rate


# ── httpx taklidi (desen: tests/test_yerel_saglayici.py) ─────────────────────

class _SahteYanit:
    def __init__(self, govde):
        self._govde = govde

    def raise_for_status(self):
        return None

    def json(self):
        return self._govde


def _sahte_httpx(monkeypatch, govde):
    import httpx

    class _Istemci:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            assert "frankfurter" in url, url
            return _SahteYanit(govde)

    monkeypatch.setattr(httpx, "AsyncClient", _Istemci)


_V2_GOVDE = [
    {"date": "2026-08-08", "base": "USD", "quote": "EUR", "rate": 0.86612},
    {"date": "2026-08-08", "base": "USD", "quote": "TRY", "rate": 47.646},
]


# ── ① Asıl regresyon: v2 listesi ─────────────────────────────────────────────

async def test_v2_listesi_kur_dondurur(monkeypatch):
    """Gerçek v2 gövdesiyle araç ÇALIŞMALI.

    Düzeltme geri alınırsa burası kırmızı yanar: eski kod `data.get` çağırır,
    AttributeError dış `except`e düşer ve çıktı "Hata:" ile başlar.
    """
    _sahte_httpx(monkeypatch, _V2_GOVDE)
    out = await get_exchange_rate("USD", "TRY,EUR")

    assert not out.startswith("Hata:"), out
    assert "47.6460 TRY" in out
    assert "0.8661 EUR" in out
    assert "2026-08-08" in out


async def test_istenen_sira_korunur(monkeypatch):
    """API EUR'yu önce döndürse de kullanıcı TRY istediyse TRY üstte olmalı.

    "Dolar kaç TL" sorusunun cevabı ilk satırda görünsün diye; sıra API'nin
    keyfine bırakılmaz.
    """
    _sahte_httpx(monkeypatch, _V2_GOVDE)
    out = await get_exchange_rate("USD", "TRY,EUR")
    satirlar = out.splitlines()

    assert "TRY" in satirlar[1], satirlar
    assert "EUR" in satirlar[2], satirlar


# ── ② Geriye dönük: v1 sözlüğü ───────────────────────────────────────────────

async def test_v1_sozlugu_da_calisir(monkeypatch):
    """API eski şekle dönerse (ya da v1 URL'i kullanılırsa) araç ölmemeli."""
    _sahte_httpx(monkeypatch, {
        "amount": 1.0, "base": "USD", "date": "2026-08-07",
        "rates": {"EUR": 0.86693, "TRY": 47.706},
    })
    out = await get_exchange_rate("USD", "TRY,EUR")

    assert not out.startswith("Hata:"), out
    assert "47.7060 TRY" in out
    assert "2026-08-07" in out


# ── ③ Bozuk/eksik cevaplar — çökmeden anlaşılır mesaj ────────────────────────

async def test_bos_liste_temiz_hata(monkeypatch):
    """Boş cevapta ham istisna değil, TR hata mesajı dönmeli."""
    _sahte_httpx(monkeypatch, [])
    out = await get_exchange_rate("USD", "TRY")

    assert out.startswith("Hata:")
    assert "kur döndürmedi" in out


async def test_eksik_kur_veri_yok_der(monkeypatch):
    """İstenen para birimi cevapta yoksa yalnız o satır 'veri yok' olur.

    Tek eksik kur yüzünden tüm cevap çöpe gitmez (kripto aracının deseni).
    """
    _sahte_httpx(monkeypatch, _V2_GOVDE)
    out = await get_exchange_rate("USD", "TRY,XYZ")

    assert "47.6460 TRY" in out
    assert "XYZ: veri yok" in out


async def test_beklenmeyen_bicim_temiz_hata(monkeypatch):
    """Sağlayıcı düz metin/sayı döndürürse araç çökmez."""
    _sahte_httpx(monkeypatch, "bakım çalışması")
    out = await get_exchange_rate("USD", "TRY")

    assert out.startswith("Hata:")
    assert "biçim" in out


@pytest.mark.parametrize("bozuk", [
    [{"quote": "TRY", "rate": None}],
    [{"quote": "TRY", "rate": "yok"}],
])
async def test_bozuk_kur_degeri_satiri_dusurur(monkeypatch, bozuk):
    """`rate` null/metin gelirse `float()` patlamasın, o satır 'veri yok' olsun."""
    _sahte_httpx(monkeypatch, bozuk)
    out = await get_exchange_rate("USD", "TRY")

    assert "TRY: veri yok" in out

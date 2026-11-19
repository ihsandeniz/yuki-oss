"""Harness H0 — sağlayıcı kopmasında görev kurtarma.

Kabul (HARNESS-TASARIM § 10, H0):
  H0-a  geçici hata (zaman aşımı, bağlantı, 5xx/529, akış ortası kopma
        geçici arıza) → 1/5/15 dk arayla en çok 3 otomatik yeniden deneme, son kayıtlı
        adımdan; hepsi tükenirse `durdu/saglayici_gecici` → DEVAM aynı adımdan sürer.
  H0-b  kalıcı hata (ValueError, 4xx, kimlik) → `hata`, yeniden deneme YOK; kota → `durdu/kota`.
  + bekleme DURDUR ile ≤2 sn kesilir · restart beklemede de `durdu` (karar 3) ·
    her deneme `olaylar.jsonl`'a yazılır.

Önceki kanıt (L6 Faz 2, `reports/…/L6/kanit_api_kopmasi_test.py`) bugünkü davranışı
sabitliyordu: geçici hata → `hata`, DEVAM red. Burada TERSİ ölçülür.
Bekleme sahte saatle: `gorev._uyu` değiştirilir, gerçek 15 dk beklenmez.
"""
import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import openai
import pytest

from app.services import gorev as gorev_mod
from app.services.gorev import GorevHatasi, GorevServisi
from app.services.atolye.baglam import yerel_baglam
from tests.atolye_yardimci import _arac_akisi, _icerik_akisi, kota_hatasi

GID = "deneme/kopma"
_REQ = httpx.Request("POST", "https://sahte.invalid/v1")


def _router(create, saglayici="openai"):
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=create)
    r = MagicMock()
    r.get_client = AsyncMock(return_value=(client, "gpt-5.6-luna"))
    r.record_failure = MagicMock()
    return r


@pytest.fixture
def sahte_saat(monkeypatch):
    """Her bekleme tek `_uyu` çağrısı olsun ve süresi kaydedilsin (gerçek bekleme yok)."""
    beklenen: list[float] = []

    async def _uyu(sn):
        beklenen.append(sn)

    monkeypatch.setattr(gorev_mod, "_uyu", _uyu)
    monkeypatch.setattr(gorev_mod, "_BEKLEME_ADIMI", 10_000)
    return beklenen


def _senaryo(*adimlar):
    """Sırayla: 'arac' → alan_yaz adımı · 'bitir' → içerik (bitti) · istisna → fırlat ·
    ('kopuk', istisna) → akış bir parça verip ORTADA kopar."""
    kayit = {"n": 0, "mesajlar": []}

    async def _create(**kw):
        i = kayit["n"]
        kayit["n"] += 1
        kayit["mesajlar"].append([dict(m) for m in kw.get("messages", [])])
        a = adimlar[min(i, len(adimlar) - 1)]
        if a == "arac":
            return _arac_akisi([(f"c{i}", "alan_yaz", {"yol": f"adim-{i}.txt", "icerik": "x"})])
        if a == "bitir":
            return _icerik_akisi("tamam bitti")
        if isinstance(a, tuple) and a[0] == "kopuk":
            hata = a[1]

            async def _aiter():
                yield SimpleNamespace(choices=[SimpleNamespace(
                    delta=SimpleNamespace(content="yarım ", tool_calls=None))])
                raise hata
            akis = MagicMock()
            akis.__aiter__ = lambda self: _aiter()
            return akis
        raise a
    return _create, kayit


async def _kos(tmp_path, create, saglayici="openai"):
    s = GorevServisi(tmp_path, bildir=lambda *a: None)
    with patch("app.services.llm_router.get_router", return_value=_router(create, saglayici)), \
            yerel_baglam():
        await s.baslat("deneme", "kopma", "notları yaz")
        d = await s.bekle(GID, zaman_asimi=20)
    return s, d


def _olaylar(tmp_path):
    satirlar = (tmp_path / "deneme/kopma/.gorev/olaylar.jsonl").read_text().splitlines()
    return [json.loads(x) for x in satirlar]


# ── H0-a: geçici → yeniden dene, aynı adımdan ────────────────────────────────

@pytest.mark.parametrize("hata", [
    openai.APITimeoutError(request=_REQ),
    openai.APIConnectionError(request=_REQ),
    openai.InternalServerError("529", response=httpx.Response(529, request=_REQ), body=None),
    httpx.ReadTimeout("okuma zaman aşımı", request=_REQ),
    asyncio.TimeoutError(),
], ids=["zaman_asimi", "baglanti", "529", "httpx_okuma", "asyncio_timeout"])
def test_gecici_hata_yeniden_denenir_ve_ayni_adimdan_biter(tmp_path, sahte_saat, hata):
    create, kayit = _senaryo("arac", hata, "bitir")
    _, d = asyncio.run(_kos(tmp_path, create))
    assert d["durum"] == "bitti", d
    assert d["adim"] == 2 and kayit["n"] == 3
    assert sahte_saat == [60]                                 # 1. bekleme 1 dk
    # yeniden deneme son kayıtlı adımdan: 3. çağrı 1. adımın araç sonucunu görür
    assert any(m.get("role") == "tool" for m in kayit["mesajlar"][2])
    assert (tmp_path / "deneme/kopma/adim-0.txt").exists()
    ol = [o for o in _olaylar(tmp_path) if o["olay"] == "yeniden_deneme"]
    assert len(ol) == 1 and ol[0]["deneme"] == 1 and ol[0]["bekle_sn"] == 60 and ol[0]["adim"] == 1
    assert "yeniden_deneme" not in d                          # son kayıtta bekleme izi kalmaz


def test_akis_ortasinda_kopma_yeniden_denenir(tmp_path, sahte_saat):
    """Asıl açık şuydu: ilk parçadan SONRA kopma runner'dan istisna olarak çıkar."""
    kopma = ("kopuk", httpx.RemoteProtocolError("bağlantı koptu", request=_REQ))
    create, kayit = _senaryo("arac", kopma, "bitir")
    _, d = asyncio.run(_kos(tmp_path, create))
    assert d["durum"] == "bitti", d
    assert sahte_saat == [60] and kayit["n"] == 3


def test_uc_deneme_tukenince_durdu_saglayici_gecici_ve_devam_ayni_adimdan(tmp_path, sahte_saat):
    kopuk = openai.APIConnectionError(request=_REQ)
    create, kayit = _senaryo("arac", kopuk, kopuk, kopuk, kopuk)
    s = GorevServisi(tmp_path, bildir=lambda *a: None)
    r = _router(create)
    with patch("app.services.llm_router.get_router", return_value=r), yerel_baglam():
        async def _akis():
            await s.baslat("deneme", "kopma", "notları yaz")
            d1 = await s.bekle(GID, zaman_asimi=20)
            # sağlayıcı düzeldi → kullanıcı DEVAM eder
            ikinci, kayit2 = _senaryo("bitir")
            r.get_client.return_value[0].chat.completions.create = AsyncMock(side_effect=ikinci)
            await s.devam(GID, onay=True)
            return d1, await s.bekle(GID, zaman_asimi=20), kayit2
        d1, d2, kayit2 = asyncio.run(_akis())
    assert (d1["durum"], d1["neden"]) == ("durdu", "saglayici_gecici"), d1
    assert d1["adim"] == 1
    assert sahte_saat == [60, 300, 900]                       # HK3 b: 1 / 5 / 15 dk
    assert kayit["n"] == 1 + 1 + 3                            # adım + ilk kopma + 3 deneme
    # aynı adımdan sürdü: DEVAM'ın ilk çağrısı 1. adımın araç sonucunu görür, adım 1 + kapanış
    assert d2["durum"] == "bitti" and d2["adim"] == 2, d2
    assert any(m.get("role") == "tool" for m in kayit2["mesajlar"][0])
    ol = [o["olay"] for o in _olaylar(tmp_path)]
    assert ol.count("yeniden_deneme") == 3 and "yeniden_deneme_bitti" in ol


# ── H0-b: kalıcı → yeniden deneme yok ────────────────────────────────────────

@pytest.mark.parametrize("hata,beklenen", [
    (ValueError("bozuk argüman"), ("hata", "ValueError")),
    (openai.BadRequestError("400", response=httpx.Response(400, request=_REQ), body=None),
     ("hata", "BadRequestError")),
    (openai.AuthenticationError("401", response=httpx.Response(401, request=_REQ), body=None),
     ("hata", "AuthenticationError")),
    # 429: kota beklemesi yeniden denemeyle geçmez → durdu/kota
    (kota_hatasi(), ("durdu", "kota")),
], ids=["valueerror", "400", "401", "kota"])
def test_kalici_hata_yeniden_denenmez(tmp_path, sahte_saat, hata, beklenen):
    create, kayit = _senaryo("arac", hata, "bitir")
    _, d = asyncio.run(_kos(tmp_path, create))
    assert (d["durum"], d["neden"]) == beklenen, d
    assert sahte_saat == [] and kayit["n"] == 2
    assert not [o for o in _olaylar(tmp_path) if o["olay"] == "yeniden_deneme"]


def test_gecici_mi_siniflandirmasi():
    g = gorev_mod._gecici_mi
    assert g(httpx.ConnectError("x", request=_REQ)) and g(asyncio.TimeoutError())
    assert not g(kota_hatasi())                               # 429 geçici değil: kota
    assert not g(None) and not g(RuntimeError("?"))           # bilinmeyen → kalıcı (fail-closed)
    assert gorev_mod._kota_mi(kota_hatasi()) and not gorev_mod._kota_mi(RuntimeError("?"))


# ── bekleme sırasında DURDUR ve restart ──────────────────────────────────────

def test_beklemede_durdur_iki_saniyede(tmp_path, monkeypatch):
    monkeypatch.setattr(gorev_mod, "YENIDEN_DENEME_SN", (30,))   # gerçek saat, uzun bekleme
    create, kayit = _senaryo("arac", openai.APITimeoutError(request=_REQ), "bitir")
    s = GorevServisi(tmp_path, bildir=lambda *a: None)
    with patch("app.services.llm_router.get_router", return_value=_router(create)), yerel_baglam():
        async def _akis():
            await s.baslat("deneme", "kopma", "notları yaz")
            for _ in range(200):
                if (s.durum(GID).get("neden") or "").startswith("yeniden_deneme"):
                    break
                await asyncio.sleep(0.02)
            t0 = time.monotonic()
            d = await s.durdur(GID)
            return d, time.monotonic() - t0
        d, sure = asyncio.run(_akis())
    assert (d["durum"], d["neden"]) == ("durdu", "durdur"), d
    # ≤2 sn şart; ≤1 sn: beklemenin KENDİSİ DURDUR'u görüyor (servisin 1,5 sn sonraki zorla
    # iptal yedeğine kalmadan) — mutasyon 'bekleme_iptali_gormez' bunu ölçer
    assert sure <= 1.0, sure
    assert kayit["n"] == 2                                    # bekleme sonrası çağrı YOK


def test_beklemede_restart_kendiliginden_devam_etmez(tmp_path, monkeypatch):
    """Karar 3: bekleme diskte `kosuyor` görünür → yeni süreç `durdu` yapar, BAŞLATMAZ."""
    monkeypatch.setattr(gorev_mod, "YENIDEN_DENEME_SN", (30,))
    create, _ = _senaryo("arac", openai.APITimeoutError(request=_REQ), "bitir")
    s = GorevServisi(tmp_path, bildir=lambda *a: None)
    with patch("app.services.llm_router.get_router", return_value=_router(create)), yerel_baglam():
        async def _akis():
            await s.baslat("deneme", "kopma", "notları yaz")
            for _ in range(200):
                if (s.durum(GID).get("neden") or "").startswith("yeniden_deneme"):
                    break
                await asyncio.sleep(0.02)
            yeni = GorevServisi(tmp_path, bildir=lambda *a: None)   # "restart": yeni süreç
            d = yeni.durum(GID)
            await s.durdur(GID)                                      # eski görevi temizle
            return d, len(yeni._kosan)
        d, kosan = asyncio.run(_akis())
    assert (d["durum"], d["neden"]) == ("durdu", "yeniden_baslatma")
    assert kosan == 0


def test_sohbet_yolu_etkilenmez():
    """H0 yalnız görev servisinde: runner'ın sohbet kipi (gorev=None) istisnayı tutmaz."""
    from app.services.runner import LLMRunner
    r = LLMRunner(MagicMock(), "m", [])
    assert r.sonuc is None

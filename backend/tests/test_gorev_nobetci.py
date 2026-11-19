"""Harness H2 — görev nöbetçisi + `.gorev/nabiz`.

Kabul (§ 10, H2):
  H2-a  sahte "asılan LLM" (çağrı hiç dönmez, akış parçası gelmez) → son nabızdan en geç
        `ASILMA_ESIGI + NOBET_ARALIK` sonra `durdu/asildi`.
  H2-b  koşan görev yokken nöbetçi 0 iş yapar (sayaç) — döngü hiç doğmaz, görev bitince ölür.
  + yanlış alarm yok: uzun ama akan cevap ve H0'ın 15 dk'lık yeniden deneme beklemesi
    asılma SAYILMAZ · elle DURDUR `durdur` kalır · asılan görev DEVAM ile aynı adımdan sürer.

Saat sahte (`gorev._nabiz_saat`, `gorev_nobetci._uyu`): gerçek 180 sn beklenmez. Bir test
de küçültülmüş eşikle GERÇEK saatte uçtan uca koşar. Model gerçek değil (sahte yönlendirici).
"""
import asyncio
import dataclasses
import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services import gorev as gorev_mod
from app.services import gorev_nobetci as nob_mod
from app.services.atolye.turler import TURLER
from app.services.gorev import GorevServisi
from app.services.gorev_nobetci import Nobetci, nobetciyi_bagla
from app.services.atolye.baglam import yerel_baglam
from tests.atolye_yardimci import _arac_akisi, _icerik_akisi
from tests.test_gorev_kopma import _router

GID = "deneme/nobet"


class _Saat:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def saat(monkeypatch):
    s = _Saat()
    monkeypatch.setattr(gorev_mod, "_nabiz_saat", s)
    return s


def _asili_llm():
    """İlk çağrı araç adımı (nabız atar), ikinci çağrı HİÇ dönmez — asılan LLM."""
    durum = {"n": 0, "asili": asyncio.Event(), "son_nabiz": None}

    async def _create(**kw):
        durum["n"] += 1
        if durum["n"] == 1:
            return _arac_akisi([("c1", "alan_yaz", {"yol": "a.txt", "icerik": "x"})])
        durum["asili"].set()
        await asyncio.Event().wait()            # sonsuza dek — iptal jetonunu görmez
    return _create, durum


def _servis(tmp_path, nobetci=True, turler=None):
    s = GorevServisi(tmp_path, turler=turler, bildir=lambda *a: None)
    if nobetci:
        nobetciyi_bagla(s)
    return s


def _olaylar(tmp_path, gid=GID):
    yol = tmp_path / gid / ".gorev/olaylar.jsonl"
    return [json.loads(x) for x in yol.read_text().splitlines()]


# ── H2-a: asılan LLM → eşik + aralık içinde durdu/asildi ─────────────────────

def test_h2a_asilan_llm_esik_arti_aralik_icinde_durdu_asildi(tmp_path, saat, monkeypatch):
    create, dur = _asili_llm()
    duruldugu_an: list[float] = []

    async def _uyu(sn):                       # nöbetçinin beklemesi: sahte saati ilerlet
        await dur["asili"].wait()
        saat.t += sn
        await asyncio.sleep(0)

    monkeypatch.setattr(nob_mod, "_uyu", _uyu)

    async def senaryo():
        s = _servis(tmp_path)
        asil = s.asildi_durdur

        async def _kaydet(gid, sessiz, esik):
            duruldugu_an.append(saat.t)
            return await asil(gid, sessiz, esik)
        s.asildi_durdur = _kaydet
        with patch("app.services.llm_router.get_router", return_value=_router(create)), \
                yerel_baglam():
            await s.baslat("deneme", "nobet", "yaz")
            await dur["asili"].wait()
            dur["son_nabiz"] = s._kosan[GID].iptal.son_nabiz
            d = await asyncio.wait_for(s.bekle(GID), timeout=10)
        return s, d

    s, d = asyncio.run(senaryo())
    assert (d["durum"], d["neden"]) == ("durdu", "asildi"), d
    assert len(duruldugu_an) == 1
    gecen = duruldugu_an[0] - dur["son_nabiz"]
    assert nob_mod.ASILMA_ESIGI <= gecen <= nob_mod.ASILMA_ESIGI + nob_mod.NOBET_ARALIK, gecen
    assert d["adim"] == 1 and dur["n"] == 2                  # 1. adım kayıtlı, LLM 2 kez
    assert s.nobetci.sayac["asildi"] == 1
    asildi = [o for o in _olaylar(tmp_path) if o["olay"] == "asildi"]
    assert len(asildi) == 1 and asildi[0]["esik_sn"] == nob_mod.ASILMA_ESIGI
    assert _olaylar(tmp_path)[-1]["olay"] == "son"


def test_h2a_esikten_once_durdurmaz_esikte_durdurur(tmp_path, saat):
    """Sınır: eşik − 0,5 sn → dokunmaz; eşik → durdurur. Nöbetçi elle çevrilir."""
    create, dur = _asili_llm()

    async def senaryo():
        s = _servis(tmp_path, nobetci=False)
        n = Nobetci(s)
        with patch("app.services.llm_router.get_router", return_value=_router(create)), \
                yerel_baglam():
            await s.baslat("deneme", "nobet", "yaz")
            await dur["asili"].wait()
            son = s._kosan[GID].iptal.son_nabiz
            saat.t = son + nob_mod.ASILMA_ESIGI - 0.5
            once = await n.tur()
            hala = s._oku(GID)["durum"]
            saat.t = son + nob_mod.ASILMA_ESIGI
            sonra = await n.tur()
            d = await asyncio.wait_for(s.bekle(GID), timeout=5)
        return once, hala, sonra, d

    once, hala, sonra, d = asyncio.run(senaryo())
    assert once == [] and hala == "kosuyor"
    assert sonra == [GID] and (d["durum"], d["neden"]) == ("durdu", "asildi")


def test_h2a_gercek_saat_kucuk_esik_uctan_uca(tmp_path, monkeypatch):
    """Sahte saat YOK: eşik 0,6 sn, aralık 0,2 sn — gerçek döngü, gerçek bekleme.
    Eşik `max(ASILMA_ESIGI, 3 × arac_zaman_asimi)` → türün araç zaman aşımı da küçültülür."""
    monkeypatch.setattr(nob_mod, "ASILMA_ESIGI", 0.6)
    monkeypatch.setattr(nob_mod, "NOBET_ARALIK", 0.2)
    t = TURLER["deneme"]
    turler = dict(TURLER)
    turler["deneme"] = dataclasses.replace(
        t, tavanlar=dataclasses.replace(t.tavanlar, arac_zaman_asimi=0.1))
    create, dur = _asili_llm()

    async def senaryo():
        s = _servis(tmp_path, turler=turler)
        with patch("app.services.llm_router.get_router", return_value=_router(create)), \
                yerel_baglam():
            await s.baslat("deneme", "nobet", "yaz")
            await dur["asili"].wait()
            t0 = time.monotonic()
            d = await asyncio.wait_for(s.bekle(GID), timeout=10)
            return d, time.monotonic() - t0, s

    d, gecen, s = asyncio.run(senaryo())
    assert (d["durum"], d["neden"]) == ("durdu", "asildi"), d
    assert gecen <= 0.6 + 0.2 + 0.3, gecen                    # +0,3 sn zamanlama payı
    assert s.nobetci.sayac["asildi"] == 1


def test_esik_tur_arac_zaman_asimindan_turetilir(tmp_path, saat):
    """arac_zaman_asimi 100 sn olan türde eşik 300 sn: 200 sn sessizlik asılma değil."""
    t = TURLER["deneme"]
    turler = dict(TURLER)
    turler["deneme"] = dataclasses.replace(
        t, tavanlar=dataclasses.replace(t.tavanlar, arac_zaman_asimi=100.0))
    create, dur = _asili_llm()

    async def senaryo():
        s = _servis(tmp_path, nobetci=False, turler=turler)
        n = Nobetci(s)
        with patch("app.services.llm_router.get_router", return_value=_router(create)), \
                yerel_baglam():
            await s.baslat("deneme", "nobet", "yaz")
            await dur["asili"].wait()
            esik = n.esik(GID)
            son = s._kosan[GID].iptal.son_nabiz
            saat.t = son + 200
            once = await n.tur()
            saat.t = son + 300
            sonra = await n.tur()
            await asyncio.wait_for(s.bekle(GID), timeout=5)
        return esik, once, sonra

    esik, once, sonra = asyncio.run(senaryo())
    assert esik == 300.0 and once == [] and sonra == [GID]


# ── yanlış alarm yok ────────────────────────────────────────────────────────

def test_uzun_ama_akan_cevap_asilma_sayilmaz(tmp_path, saat):
    """10 parça × 50 sn = 500 sn (eşiğin ~3 katı) süren cevap: parçalar aktıkça nabız atar."""
    durdurulan: list[str] = []
    s = None

    async def _create(**kw):
        async def _aiter():
            for i in range(10):
                saat.t += 50
                durdurulan.extend(await s.nobetci.tur())
                yield SimpleNamespace(choices=[SimpleNamespace(
                    delta=SimpleNamespace(content=f"parça{i} ", tool_calls=None))])
        akis = MagicMock()
        akis.__aiter__ = lambda self: _aiter()
        return akis

    async def senaryo():
        nonlocal s
        s = _servis(tmp_path)
        with patch("app.services.llm_router.get_router", return_value=_router(_create)), \
                yerel_baglam():
            await s.baslat("deneme", "nobet", "yaz")
            return await asyncio.wait_for(s.bekle(GID), timeout=10)

    d = asyncio.run(senaryo())
    assert d["durum"] == "bitti", d
    assert durdurulan == [] and s.nobetci.sayac["tur"] == 10 and s.nobetci.sayac["asildi"] == 0


def test_h0_yeniden_deneme_beklemesi_asilma_sayilmaz(tmp_path, saat, monkeypatch):
    """H0: geçici hata → 15 dk bekleme. Bekleme döngüsü jetonu yokladıkça nabız atar."""
    monkeypatch.setattr(gorev_mod, "YENIDEN_DENEME_SN", (15 * 60,))
    monkeypatch.setattr(gorev_mod, "_BEKLEME_ADIMI", 30)
    durdurulan: list[str] = []
    s = None

    async def _uyu(sn):
        saat.t += sn
        durdurulan.extend(await s.nobetci.tur())

    monkeypatch.setattr(gorev_mod, "_uyu", _uyu)
    cagri = {"n": 0}

    async def _create(**kw):
        cagri["n"] += 1
        if cagri["n"] == 1:
            raise ConnectionError("kopuk")
        return _icerik_akisi("tamam")

    async def senaryo():
        nonlocal s
        s = _servis(tmp_path)
        with patch("app.services.llm_router.get_router", return_value=_router(_create)), \
                yerel_baglam():
            await s.baslat("deneme", "nobet", "yaz")
            return await asyncio.wait_for(s.bekle(GID), timeout=10)

    d = asyncio.run(senaryo())
    assert d["durum"] == "bitti", d
    assert durdurulan == [] and s.nobetci.sayac["tur"] == 30      # 900 sn / 30


def test_elle_durdur_asildi_olmaz(tmp_path, saat):
    create, dur = _asili_llm()

    async def senaryo():
        s = _servis(tmp_path)
        with patch("app.services.llm_router.get_router", return_value=_router(create)), \
                yerel_baglam():
            await s.baslat("deneme", "nobet", "yaz")
            await dur["asili"].wait()
            return await s.durdur(GID)

    d = asyncio.run(senaryo())
    assert (d["durum"], d["neden"]) == ("durdu", "durdur")


def test_asilan_gorev_devam_ile_ayni_adimdan_biter(tmp_path, saat):
    """durdu/asildi DEVAM edilebilir (karar 3: yalnız onayla) ve adım sayısı korunur."""
    create, dur = _asili_llm()
    cagri = {"n": 0}

    async def _bitir(**kw):
        cagri["n"] += 1
        cagri["mesajlar"] = kw.get("messages")
        return _icerik_akisi("bitti")

    async def senaryo():
        s = _servis(tmp_path, nobetci=False)
        n = Nobetci(s)
        with yerel_baglam():
            with patch("app.services.llm_router.get_router", return_value=_router(create)):
                await s.baslat("deneme", "nobet", "yaz")
                await dur["asili"].wait()
                saat.t += nob_mod.ASILMA_ESIGI + 1
                await n.tur()
                d1 = await asyncio.wait_for(s.bekle(GID), timeout=5)
            with patch("app.services.llm_router.get_router", return_value=_router(_bitir)):
                await s.devam(GID, onay=True)
                d2 = await asyncio.wait_for(s.bekle(GID), timeout=5)
        return d1, d2

    d1, d2 = asyncio.run(senaryo())
    assert (d1["durum"], d1["neden"], d1["adim"]) == ("durdu", "asildi", 1)
    assert d2["durum"] == "bitti" and d2["adim"] == 2 and cagri["n"] == 1
    assert any(m.get("role") == "tool" for m in cagri["mesajlar"])


# ── H2-b: koşan görev yokken 0 iş ───────────────────────────────────────────

def test_h2b_kosan_yokken_nobetci_sifir_is(tmp_path, monkeypatch):
    monkeypatch.setattr(nob_mod, "NOBET_ARALIK", 0.02)

    async def senaryo():
        s = _servis(tmp_path)
        n = s.nobetci
        await asyncio.sleep(0.3)                                # boşta: 15 aralık geçer
        bos = (dict(n.sayac), n._dongu_gorevi, await n.tur(), dict(n.sayac))
        with patch("app.services.llm_router.get_router",
                   return_value=_router(lambda **kw: _icerik_akisi("tamam"))), yerel_baglam():
            await s.baslat("deneme", "nobet", "yaz")
            await s.bekle(GID, zaman_asimi=5)
        await asyncio.sleep(0.1)
        bitis = dict(n.sayac)
        await asyncio.sleep(0.3)                                # görev bitti: yine 15 aralık
        return bos, bitis, dict(n.sayac), n._dongu_gorevi.done()

    bos, bitis, sonra, dongu_bitti = asyncio.run(senaryo())
    sayac0, dongu0, tur_sonucu, sayac1 = bos
    assert sayac0 == {"tur": 0, "denetlenen": 0, "asildi": 0, "gece": 0}   # H3: gece sayacı
    assert dongu0 is None, "görev yokken nöbet döngüsü doğdu"
    assert tur_sonucu == [] and sayac1 == sayac0, "boş turda iş sayıldı"
    assert dongu_bitti, "görev bittikten sonra nöbet döngüsü yaşıyor"
    assert sonra == bitis, "görev bittikten sonra nöbetçi iş yaptı"


def test_servis_nobetciyi_kendiliginden_baglar(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_ATOLYE_KOK", str(tmp_path))
    monkeypatch.setattr(gorev_mod, "_servis", None)
    s = gorev_mod.get_gorev_servisi()
    assert isinstance(s.nobetci, Nobetci) and nobetciyi_bagla(s) is s.nobetci


# ── nabız dosyası + özet ────────────────────────────────────────────────────

def test_nabiz_dosyasi_her_adimda_yazilir_ozette_gorunur(tmp_path):
    cagri = {"n": 0}

    async def _create(**kw):
        cagri["n"] += 1
        if cagri["n"] <= 2:
            return _arac_akisi([(f"c{cagri['n']}", "alan_yaz",
                                 {"yol": f"{cagri['n']}.txt", "icerik": "x"})])
        return _icerik_akisi("tamam")

    async def senaryo():
        s = _servis(tmp_path)
        with patch("app.services.llm_router.get_router", return_value=_router(_create)), \
                yerel_baglam():
            await s.baslat("deneme", "nobet", "yaz")
            return await s.bekle(GID, zaman_asimi=5)

    d = asyncio.run(senaryo())
    nabiz = json.loads((tmp_path / GID / ".gorev/nabiz").read_text())
    assert set(nabiz) == {"zaman", "ts", "adim"} and nabiz["adim"] == 2
    assert abs(nabiz["ts"] - time.time()) < 30
    assert gorev_mod.ozet(d)["son_nabiz"] == nabiz["zaman"]

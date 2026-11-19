"""Yuki Harness H3 — gündüz penceresi · açılış telafisi · günlük bütçe · kota bekleme
.

Kabul ölçüleri (hepsi SAHTE SAAT — gerçek 23:30 / 60 dk beklenmez):
  H3-a saat 23:31 → yeni görev başlamaz (onay kaydolur, model 0 çağrı)
  H3-b 23:30'da kuyruğun uzun işi → `durdu/gece` (kısa iş payla sürer, elle başlatılana dokunulmaz)
  H3-c açılış → telafi TEK satır, otomatik devam 0
  H3-d günlük token aşımı → sıradaki başlamaz (görev sayısı ve elle koşu da sayılır)
  H3-e `durdu/kota` → 60 dk yeni görev 0

LLM sahte, atölye kökü pytest'in geçici dizini — gerçek veri dizinine dokunulmaz.
"""
import asyncio
import dataclasses
import json
import time
from unittest.mock import patch

import pytest

from app.services import gorev as gorev_mod
from app.services import gorev_kapilari as kapi_mod
from app.services import gorev_kuyrugu as kuyruk_mod
from app.services.atolye.turler import TURLER
from app.services.gorev import GorevServisi
from app.services.gorev_kuyrugu import GorevKuyrugu
from app.services.gorev_nobetci import Nobetci
from app.services.atolye.baglam import yerel_baglam
from tests.atolye_yardimci import _arac_akisi, _icerik_akisi, kota_hatasi
from tests.test_gorev_servisi import SahteLLM


def _ts(gun, saat, dk, sn=0):
    return time.mktime((2026, 10, gun, saat, dk, sn, 0, 0, -1))


@pytest.fixture(autouse=True)
def gercek_bildirim_yok(monkeypatch):
    def _yasak(*a, **k):
        raise AssertionError("test gerçek masaüstü bildirimi göndermeye çalıştı")
    monkeypatch.setattr(gorev_mod, "_masaustu_bildir", _yasak)


@pytest.fixture(autouse=True)
def varsayilan_ayar(monkeypatch):
    """Ortamdaki ATOLYE_* ayarları ölçümü bozmasın — tasarım varsayılanları geçerli."""
    for ad in ("YUKI_ATOLYE_PENCERE", "YUKI_ATOLYE_GUNLUK_TOKEN", "YUKI_ATOLYE_GUNLUK_GOREV",
               "YUKI_ATOLYE_GUNLUK_SURE_DK", "YUKI_ATOLYE_KOTA_BEKLEME_DK"):
        monkeypatch.delenv(ad, raising=False)


@pytest.fixture
def saat(monkeypatch):
    """Tek sahte duvar saati: kapılar (`_zaman`) ve kayıt zaman damgaları (`_simdi`)."""
    s = {"t": _ts(22, 12, 0)}
    monkeypatch.setattr(kuyruk_mod, "_zaman", lambda: s["t"])
    monkeypatch.setattr(gorev_mod, "_simdi",
                        lambda: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(s["t"])))
    return s


@pytest.fixture
def kok(tmp_path):
    return tmp_path / "atolye"


def _uzun_turler():
    """`uzun`: süre tavanı 1 sa (gece payı 15 dk'ya sığmaz) — `deneme`'nin kopyası."""
    t = TURLER["deneme"]
    return {**TURLER, "uzun": dataclasses.replace(
        t, ad="uzun", tavanlar=dataclasses.replace(t.tavanlar, sure_sn=3600, adim=60))}


@pytest.fixture
def servis(kok):
    return GorevServisi(kok, turler=_uzun_turler(), bildir=lambda *a: None)


@pytest.fixture
def kuyruk(servis, saat):
    return GorevKuyrugu(servis)


def _asili():
    async def _y():
        await asyncio.sleep(60)
    return _y


def _yaz(i):
    return _arac_akisi([(f"c{i}", "alan_yaz", {"yol": f"{i}.txt", "icerik": "x"})])


async def _bekle(kosul, sure=5.0, mesaj="koşul gelmedi"):
    son = time.monotonic() + sure
    while not kosul():
        assert time.monotonic() < son, mesaj
        await asyncio.sleep(0.01)


def _durum(kuyruk, qid):
    k = next(k for k in kuyruk.liste() if k["id"] == qid)
    return k["durum"], k.get("neden")


def _olaylar(kok, olay=None):
    yol = kok / ".kuyruk" / "olaylar.jsonl"
    hepsi = [json.loads(s) for s in yol.read_text().splitlines()] if yol.exists() else []
    return [o for o in hepsi if olay is None or o["olay"] == olay]


def _oner_onayla(kuyruk, ad, tur="deneme"):
    with yerel_baglam():
        q = kuyruk.oner(tur, ad, "yap")["id"]
        kuyruk.onayla(q)
    return q


# ══════════════════════════════════════════════════════════════════════════
#  Pencere ölçüsü
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("saat_dk,beklenen", [
    ((8, 29), False), ((8, 30), True), ((12, 0), True), ((23, 29), True),
    ((23, 30), False), ((23, 31), False), ((0, 30), False), ((3, 0), False),
])
def test_pencere_sinirlari(saat_dk, beklenen):
    assert kapi_mod.pencerede_mi(_ts(22, *saat_dk)) is beklenen


def test_pencere_disi_sure_ve_ayar_okunamazsa_varsayilan(monkeypatch):
    assert kapi_mod.pencere_disi_sn(_ts(22, 23, 45)) == 15 * 60
    assert kapi_mod.pencere_disi_sn(_ts(23, 0, 30)) == 60 * 60
    assert kapi_mod.pencere_disi_sn(_ts(22, 12, 0)) == 0
    for bozuk in ("bozuk", "23:30-08:30", "08:30-25:00", "10:00-10:00"):
        monkeypatch.setenv("YUKI_ATOLYE_PENCERE", bozuk)
        assert kapi_mod.pencere() == (8 * 60 + 30, 23 * 60 + 30), bozuk
    monkeypatch.setenv("YUKI_ATOLYE_PENCERE", "09:00-18:00")
    assert kapi_mod.pencere() == (9 * 60, 18 * 60)
    monkeypatch.setenv("YUKI_ATOLYE_GUNLUK_TOKEN", "-5")
    assert kapi_mod.gunluk_tavanlar()["token"] == kapi_mod.GUNLUK_TOKEN


def test_kalan_tahmini():
    tav = {"adim": 40, "sure_sn": 900}
    assert kapi_mod.kalan_tahmini({"tavanlar": tav, "adim": 0, "sure_sn": 0}) == 900
    assert kapi_mod.kalan_tahmini({"tavanlar": tav, "adim": 10, "sure_sn": 100}) == 300
    assert kapi_mod.kalan_tahmini({"tavanlar": tav, "adim": 10, "sure_sn": 800}) == 100


# ══════════════════════════════════════════════════════════════════════════
#  H3-a  23:31 → yeni görev başlamaz
# ══════════════════════════════════════════════════════════════════════════

async def test_h3a_pencere_disinda_yeni_is_baslamaz(kuyruk, servis, saat, kok):
    llm = SahteLLM([_icerik_akisi("bitti")])
    saat["t"] = _ts(22, 23, 31)
    with patch("app.services.llm_router.get_router", return_value=llm.router()):
        q = _oner_onayla(kuyruk, "gece")
        with yerel_baglam():
            assert kuyruk.surdur() is None
            assert kuyruk.surdur() is None
        await asyncio.sleep(0.2)
        assert _durum(kuyruk, q) == ("sirada", None), "onay kaydolmalı, iş başlamamalı"
        assert llm.cagrilar == [] and not (kok / "deneme").exists()
        assert servis._kosan_sayisi() == 0
        assert [o["neden"] for o in _olaylar(kok, "bekletildi")] == ["pencere"], \
            "kapı kararı bir kez izlenmeli (gürültü yok)"
        # sabah: pencere açık → bir sonraki tetik başlatır
        saat["t"] = _ts(23, 8, 31)
        with yerel_baglam():
            assert kuyruk.surdur()["id"] == q
        await _bekle(lambda: _durum(kuyruk, q)[0] == "bitti")
    assert len(llm.cagrilar) == 1


async def test_h3a_elle_baslatma_pencereye_takilmaz(kuyruk, servis, saat):
    """Pencere harness kapısıdır: kullanıcının elle başlattığı görev gece de koşar."""
    llm = SahteLLM([_icerik_akisi("bitti")])
    saat["t"] = _ts(22, 23, 50)
    with patch("app.services.llm_router.get_router", return_value=llm.router()), yerel_baglam():
        await servis.baslat("deneme", "elle", "yap")
        d = await servis.bekle("deneme/elle", 5)
    assert d["durum"] == "bitti"


# ══════════════════════════════════════════════════════════════════════════
#  H3-b  23:30'da uzun iş → durdu/gece
# ══════════════════════════════════════════════════════════════════════════

async def test_h3b_pencere_sonunda_uzun_kuyruk_isi_durdu_gece(kuyruk, servis, saat, kok):
    llm = SahteLLM([_asili(), _asili()])
    saat["t"] = _ts(22, 23, 20)
    nob = Nobetci(servis)
    with patch("app.services.llm_router.get_router", return_value=llm.router()):
        a = _oner_onayla(kuyruk, "a", tur="uzun")
        b = _oner_onayla(kuyruk, "b")
        await llm.bekle(1)
        assert await nob.tur() == [], "pencere içinde dokunmamalı"
        saat["t"] = _ts(22, 23, 30)
        assert await nob.tur() == ["uzun/a"]
        await asyncio.sleep(0.2)
    assert (servis.durum("uzun/a")["durum"], servis.durum("uzun/a")["neden"]) == ("durdu", "gece")
    assert _durum(kuyruk, a) == ("durdu", "gece")
    assert _durum(kuyruk, b) == ("sirada", None), "gece duruşu sırayı ilerletmemeli"
    assert len(llm.cagrilar) == 1 and nob.sayac["gece"] == 1
    iz = [json.loads(s) for s in (kok / "uzun/a/.gorev/olaylar.jsonl").read_text().splitlines()]
    assert any(o["olay"] == "gece_durdur" and o["kalan_tahmini_sn"] > kapi_mod.GECE_PAYI for o in iz)


async def test_h3b_sigan_is_payla_surer_pay_bitince_durur(kuyruk, servis, saat):
    """Kalan tahmini ≤ 15 dk → 23:30'da sürer; pencere biteli 15 dk olunca yine durur."""
    llm = SahteLLM([_asili()])
    saat["t"] = _ts(22, 23, 20)
    nob = Nobetci(servis)
    with patch("app.services.llm_router.get_router", return_value=llm.router()):
        _oner_onayla(kuyruk, "kisa")                       # deneme: süre tavanı 5 dk
        await llm.bekle(1)
        saat["t"] = _ts(22, 23, 31)
        assert await nob.tur() == []
        saat["t"] = _ts(22, 23, 45)
        assert await nob.tur() == ["deneme/kisa"]
    assert servis.durum("deneme/kisa")["neden"] == "gece"


async def test_h3b_elle_baslatilan_ise_dokunulmaz(kuyruk, servis, saat):
    llm = SahteLLM([_asili()])
    saat["t"] = _ts(22, 23, 50)
    nob = Nobetci(servis)
    with patch("app.services.llm_router.get_router", return_value=llm.router()), yerel_baglam():
        await servis.baslat("uzun", "elle", "yap")
        await llm.bekle(1)
        assert await nob.tur() == []
        assert servis.durum("uzun/elle")["durum"] == "kosuyor"
        await servis.durdur("uzun/elle")


# ══════════════════════════════════════════════════════════════════════════
#  H3-c  Açılış → telafi tek satır, otomatik devam 0
# ══════════════════════════════════════════════════════════════════════════

async def test_h3c_acilis_telafi_tek_satir_otomatik_devam_yok(kok, saat):
    llm = SahteLLM([_asili(), _asili()])
    saat["t"] = _ts(22, 23, 20)
    with patch("app.services.llm_router.get_router", return_value=llm.router()):
        s1 = GorevServisi(kok, turler=_uzun_turler(), bildir=lambda *a: None)
        k1 = GorevKuyrugu(s1)
        assert not (kok / ".kuyruk" / "telafi.json").exists(), "boş açılışta telafi yazılmamalı"
        a = _oner_onayla(k1, "a", tur="uzun")
        b = _oner_onayla(k1, "b")
        await llm.bekle(1)
        saat["t"] = _ts(22, 23, 30)
        await Nobetci(s1).tur()                              # a → durdu/gece
        with yerel_baglam():                                 # elle görev; süreç "ölür"
            await s1.baslat("deneme", "elle", "yap")
        await llm.bekle(2)
        # ertesi sabah açılış: yeni süreç
        saat["t"] = _ts(23, 8, 40)
        s2 = GorevServisi(kok, turler=_uzun_turler(), bildir=lambda *a: None)
        k2 = GorevKuyrugu(s2)
        await asyncio.sleep(0.3)
        _h3c_olc(kok, llm, s2, k2, a, b)
        s1._kosan["deneme/elle"].task.cancel()


def _h3c_olc(kok, llm, s2, k2, a, b):
    t = json.loads((kok / ".kuyruk" / "telafi.json").read_text())
    assert "\n" not in t["satir"] and t["satir"].startswith("Atölye:")
    assert "yarım kalan 2 iş" in t["satir"] and "gece 1" in t["satir"] \
        and "yeniden başlatma 1" in t["satir"] and "sırada 1 iş" in t["satir"], t["satir"]
    assert sorted(t["isler"]) == ["deneme/elle", "uzun/a"]
    assert len(_olaylar(kok, "telafi")) == 1
    # otomatik devam 0: model çağrısı artmadı, hiçbir şey koşmuyor, kayıtlar olduğu gibi
    assert len(llm.cagrilar) == 2 and s2._kosan_sayisi() == 0
    assert _durum(k2, a) == ("durdu", "gece") and _durum(k2, b) == ("sirada", None)
    assert s2.durum("deneme/elle")["neden"] == "yeniden_baslatma"
    assert "ATOLYE" not in t["satir"] and "yap" not in t["satir"], "istek metni sızmamalı"


async def test_h3c_eski_durus_ve_elle_durdur_telafiye_girmez(kok, saat):
    llm = SahteLLM([_asili()])
    s = GorevServisi(kok, turler=_uzun_turler(), bildir=lambda *a: None)
    with patch("app.services.llm_router.get_router", return_value=llm.router()), yerel_baglam():
        await s.baslat("deneme", "elle", "yap")
        await llm.bekle(1)
        await s.durdur("deneme/elle")                      # elle DURDUR → sorulmaz
    assert GorevKuyrugu(s).acilis_telafisi() is None
    d = s.durum("deneme/elle")
    d["neden"], d["guncelleme"] = "gece", "2026-10-19 23:30:00"   # 3 gün önce
    gorev_mod._atomik_yaz(s._kayit("deneme/elle") / "durum.json", d)
    assert GorevKuyrugu(s).acilis_telafisi() is None


# ══════════════════════════════════════════════════════════════════════════
#  H3-d  Günlük bütçe
# ══════════════════════════════════════════════════════════════════════════

async def test_h3d_gunluk_token_asiminda_siradaki_baslamaz(kuyruk, servis, saat, kok, monkeypatch):
    monkeypatch.setenv("YUKI_ATOLYE_GUNLUK_TOKEN", "200")
    uzun = "kelime " * 300                                   # usage yok → ~karakter/4 tahmini
    llm = SahteLLM([_icerik_akisi(uzun), _icerik_akisi("b bitti")])
    with patch("app.services.llm_router.get_router", return_value=llm.router()):
        a = _oner_onayla(kuyruk, "a")
        b = _oner_onayla(kuyruk, "b")
        await _bekle(lambda: _durum(kuyruk, a)[0] == "bitti")
        await asyncio.sleep(0.2)
        k = kuyruk.kapi()
        assert k["token"] >= 200 and k["gorev"] == 1, k
        assert _durum(kuyruk, b) == ("sirada", None) and len(llm.cagrilar) == 1
        assert [o["neden"] for o in _olaylar(kok, "bekletildi")] == ["butce:token"]
        with yerel_baglam():
            assert kuyruk.surdur() is None
        # ertesi gün sayaçlar sıfır → sıra sürer
        saat["t"] = _ts(23, 9, 0)
        with yerel_baglam():
            assert kuyruk.surdur()["id"] == b
        await _bekle(lambda: _durum(kuyruk, b)[0] == "bitti")


async def test_h3d_gunluk_gorev_sayisi_ve_elle_kosu_sayilir(kuyruk, servis, saat, monkeypatch):
    llm = SahteLLM([_icerik_akisi("a"), _icerik_akisi("kelime " * 300), _icerik_akisi("c")])
    with patch("app.services.llm_router.get_router", return_value=llm.router()):
        monkeypatch.setenv("YUKI_ATOLYE_GUNLUK_GOREV", "1")
        a = _oner_onayla(kuyruk, "a")
        await _bekle(lambda: _durum(kuyruk, a)[0] == "bitti")
        b = _oner_onayla(kuyruk, "b")
        assert _durum(kuyruk, b) == ("sirada", None), "günlük görev sayısı dolu"
        # görev sayısı serbest, token dar: elle koşunun token'ı da bütçeye sayılır
        monkeypatch.setenv("YUKI_ATOLYE_GUNLUK_GOREV", "10")
        monkeypatch.setenv("YUKI_ATOLYE_GUNLUK_TOKEN", "200")
        with yerel_baglam():
            await servis.baslat("deneme", "elle", "yap")
            await servis.bekle("deneme/elle", 5)
            assert kuyruk.surdur() is None
        assert _durum(kuyruk, b) == ("sirada", None) and len(llm.cagrilar) == 2


def test_bozuk_kapi_dosyasi_butceyi_dolu_sayar(kuyruk, kok, saat):
    (kok / ".kuyruk").mkdir(parents=True, exist_ok=True)
    (kok / ".kuyruk" / "kapi.json").write_text('{"gun": "2026-10-22", "tok')
    assert kuyruk._engel().startswith("butce:")
    assert (kok / ".kuyruk" / "kapi.json").read_text() == '{"gun": "2026-10-22", "tok', \
        "bozuk dosya korunmalı"


# ══════════════════════════════════════════════════════════════════════════
#  H3-e  durdu/kota → 60 dk yeni görev yok
# ══════════════════════════════════════════════════════════════════════════

async def test_h3e_kota_sonrasi_60_dk_yeni_is_yok(kuyruk, servis, saat, kok):
    async def _kota():
        raise kota_hatasi()
    llm = SahteLLM([_kota, _icerik_akisi("b bitti")])
    with patch("app.services.llm_router.get_router", return_value=llm.router()):
        a = _oner_onayla(kuyruk, "a")
        await _bekle(lambda: _durum(kuyruk, a)[0] == "durdu")
        assert _durum(kuyruk, a) == ("durdu", "kota")
        t0 = saat["t"]
        saat["t"] = t0 + 59 * 60
        b = _oner_onayla(kuyruk, "b")                          # onay kaydolur, başlamaz
        with yerel_baglam():
            assert kuyruk.surdur() is None
        await asyncio.sleep(0.2)
        assert _durum(kuyruk, b) == ("sirada", None) and len(llm.cagrilar) == 1
        assert [o["neden"] for o in _olaylar(kok, "bekletildi")] == ["kota"]
        saat["t"] = t0 + 61 * 60
        with yerel_baglam():
            assert kuyruk.surdur()["id"] == b
        await _bekle(lambda: _durum(kuyruk, b)[0] == "bitti")
    assert len(_olaylar(kok, "kota_bekleme")) == 1


async def test_h3e_kota_beklemesi_restartta_kaybolmaz(kok, saat):
    async def _kota():
        raise kota_hatasi()
    llm = SahteLLM([_kota])
    with patch("app.services.llm_router.get_router", return_value=llm.router()), yerel_baglam():
        s1 = GorevServisi(kok, bildir=lambda *a: None)
        GorevKuyrugu(s1)
        await s1.baslat("deneme", "elle", "yap")            # elle koşunun kotası da sayılır
        await s1.bekle("deneme/elle", 5)
        saat["t"] += 30 * 60
        k2 = GorevKuyrugu(GorevServisi(kok, bildir=lambda *a: None))
        assert k2._engel() == "kota"

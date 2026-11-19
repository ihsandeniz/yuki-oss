"""Yuki Atölye v2 — Faz 0d: telefondan güvenli görev başlatma .

Kabul ölçüleri (Atölye v2 planı § 3):
  ⑩ dış bağlamdan onaysız başlatma → görev koşmaz, 5 dk'da düşer
  ⑪ dış bağlamlı görevde kabuk, genel dosya, panel, MCP çağrısı → red (her biri)
  ⑫ sohbetten dış bağlamla tür aracı çağrısı → red
  ⑬ telefondan tavan yükseltme → red
  ⑭ telefondan DURDUR ≤2 sn (gerçek HTTP, ikinci port)
  ⑮ yanlış/eksik token ve izinli adres dışı Origin → 401/403
⑯ (gerçek telefonda başlat→onayla→durdur) kullanıcının elle denemesidir — burada yok.

LLM sahte, atölye kökü pytest'in geçici dizini — gerçek veri dizinine dokunulmaz.
Masaüstü bildirimi sahte (kayda alınır, gönderilmez).
"""
import asyncio
import contextlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from starlette.testclient import TestClient

from app import config as cfg
from app import main as main_mod
from app.services import gorev as gorev_mod
from app.services.atolye import alan
from app.services.atolye.turler import GorevTuru, dis_yasak_mi, tur_dogrula
from app.services.gorev import GorevHatasi, GorevServisi
from app.services.runner import GorevTavanlari, LLMRunner
from app.services.atolye import baglam as tool_scope
from app.services.atolye.baglam import dis_mi as is_external, yerel_baglam
from tests.atolye_yardimci import dis_origin_izni, _arac_akisi, _icerik_akisi
from tests.test_gorev_servisi import SahteLLM

pytestmark = pytest.mark.usefixtures("atolye_acik")   # `ATOLYE` varsayılan kapalı → uçlar 404

TOKEN = "faz0d-test-anahtari-0123456789"          # ÖRNEK — sahte, yalnız bu süreçte
YETKI = {"Authorization": f"Bearer {TOKEN}"}
TS = "https://yuki.ornek.example"
@pytest.fixture(autouse=True)
def _dis_origin(monkeypatch):
    dis_origin_izni(monkeypatch, TS)
    # Varsayılan kip `masaustu` (dış onay kapalı); bu dosyanın ölçümleri `dokunus` kipinde — testler
    # kendi kipini `setenv` ile ezebilir.
    monkeypatch.setenv("YUKI_ATOLYE_DIS_ONAY", "dokunus")


TELEFON = {**YETKI, "X-Forwarded-For": "100.64.0.7", "Origin": TS}   # vekil/tünelden gelen
BACKEND = Path(__file__).resolve().parents[1]


@contextlib.contextmanager
def dis_baglam():
    tok = tool_scope._dis.set(True)
    try:
        yield
    finally:
        tool_scope._dis.reset(tok)


class Bildirimler(list):
    def __call__(self, baslik, govde):
        self.append((baslik, govde))


@pytest.fixture(autouse=True)
def gercek_bildirim_yok(monkeypatch):
    """Varsayılan bildirici (notify-send) bu dosyada ASLA çalışmaz — çalışırsa test kırmızı."""
    def _yasak(*a, **k):
        raise AssertionError("test gerçek masaüstü bildirimi göndermeye çalıştı")
    monkeypatch.setattr(gorev_mod, "_masaustu_bildir", _yasak)


@pytest.fixture
def kok(tmp_path):
    return tmp_path / "atolye"


@pytest.fixture
def bildir():
    return Bildirimler()


@pytest.fixture
def servis(kok, bildir):
    return GorevServisi(kok, bildir=bildir)


async def _taslak(servis, tur="deneme", ad="tel", istek="yap"):
    with dis_baglam():
        return await servis.baslat(tur, ad, istek, taslak=True)


# ══════════════════════════════════════════════════════════════════════════
#  ⑩ Onaysız başlatma koşmaz, düşer
# ══════════════════════════════════════════════════════════════════════════

async def test_dis_baglamdan_taslaksiz_baslatma_reddedilir(servis, kok):
    """`yerel_baglam` unutulmuş ayrı süreç (bugünkü öğrenim) hâlâ başlatamaz: taslak yolu açık değil."""
    with dis_baglam(), pytest.raises(GorevHatasi, match="dış bağlam"):
        await servis.baslat("deneme", "x", "yap")
    assert not (kok / "deneme" / "x").exists()


async def test_onaysiz_taslak_kosmaz_ve_suresinde_duser(servis, bildir, monkeypatch):
    monkeypatch.setattr(gorev_mod, "ONAY_SURESI", 0.4)
    llm = SahteLLM([_icerik_akisi("bitti")])
    with patch("app.services.llm_router.get_router", return_value=llm.router()):
        d = await _taslak(servis)
        assert d["durum"] == "bekliyor" and d["kaynak"] == "dis" and d["onay_kodu"]
        await asyncio.sleep(0.25)
        assert servis.durum("deneme/tel")["durum"] == "bekliyor"
        await asyncio.sleep(0.4)
        # Diskten DOĞRUDAN oku: `durum()` tembel denetimle kendisi düşürür, zamanlayıcıyı gölgeler.
        disk = json.loads((servis.kok / "deneme" / "tel" / alan.AYRILMIS / "durum.json").read_text())
        assert (disk["durum"], disk["neden"]) == ("dustu", "onay_suresi"), "zamanlayıcı düşürmedi"
        son = servis.durum("deneme/tel")
        assert (son["durum"], son["neden"]) == ("dustu", "onay_suresi")
        with dis_baglam(), pytest.raises(GorevHatasi):
            await servis.onayla("deneme/tel", kod=d["onay_kodu"])      # düşmüş taslak dirilmez
    assert llm.cagrilar == [], "onaysız taslakta LLM çağrıldı"
    assert len(bildir) == 1 and "deneme/tel" in bildir[0][1]          # masaüstü bildirimi


async def test_onay_suresi_bes_dakika(servis):
    assert gorev_mod.ONAY_SURESI == 300
    d = await _taslak(servis)
    assert abs(d["onay_son"] - (time.time() + 300)) < 5


async def test_zamanlayici_kacsa_da_sure_dolan_taslak_duser(servis):
    """Döngü kapanmış/zamanlayıcı kaçmış olsa bile okuma anında düşer (tembel denetim)."""
    await _taslak(servis)
    t = servis._taslaklar["deneme/tel"]
    t.zamanlayici.cancel()
    t.son = time.time() - 1
    assert servis.liste()[0]["durum"] == "dustu"


async def test_dogru_kodla_kosar_kod_tek_kullanimlik(servis):
    llm = SahteLLM([_icerik_akisi("bitti")])
    with patch("app.services.llm_router.get_router", return_value=llm.router()):
        d = await _taslak(servis)
        with dis_baglam():
            o = await servis.onayla("deneme/tel", kod=d["onay_kodu"])
        assert o["durum"] == "kosuyor"
        await servis.bekle("deneme/tel", 5)
        with dis_baglam(), pytest.raises(GorevHatasi, match="onaylanamaz"):
            await servis.onayla("deneme/tel", kod=d["onay_kodu"])
    assert servis.durum("deneme/tel")["durum"] == "bitti" and len(llm.cagrilar) == 1


async def test_yanlis_kod_reddedilir_uc_denemede_taslak_duser(servis):
    d = await _taslak(servis)
    for i in range(3):
        with dis_baglam(), pytest.raises(GorevHatasi) as e:
            await servis.onayla("deneme/tel", kod="yanlis" if i else None)
        assert e.value.http == 403
    son = servis.durum("deneme/tel")
    assert (son["durum"], son["neden"]) == ("dustu", "yanlis_kod")
    with dis_baglam(), pytest.raises(GorevHatasi):
        await servis.onayla("deneme/tel", kod=d["onay_kodu"])


async def test_masaustu_kipinde_telefon_onaylayamaz_masaustu_onaylar(servis, monkeypatch):
    monkeypatch.setenv("YUKI_ATOLYE_DIS_ONAY", "masaustu")
    llm = SahteLLM([_icerik_akisi("bitti")])
    with patch("app.services.llm_router.get_router", return_value=llm.router()):
        d = await _taslak(servis)
        with dis_baglam(), pytest.raises(GorevHatasi, match="masaüstü kipi") as e:
            await servis.onayla("deneme/tel", kod=d["onay_kodu"])     # kod doğru olsa bile
        assert e.value.http == 403
        assert servis.durum("deneme/tel")["durum"] == "bekliyor" and llm.cagrilar == []
        with yerel_baglam():
            assert (await servis.onayla("deneme/tel"))["durum"] == "kosuyor"
        await servis.bekle("deneme/tel", 5)


@pytest.mark.parametrize("deger", ["", "evet", "DOKUNUŞ", "kapali"])
def test_tanimsiz_onay_kipi_masaustu_sayilir(monkeypatch, deger):
    monkeypatch.setenv("YUKI_ATOLYE_DIS_ONAY", deger)
    assert gorev_mod.onay_kipi() == "masaustu"


async def test_restart_bekleyen_taslagi_dusurur(kok, bildir):
    s1 = GorevServisi(kok, bildir=bildir)
    d = await _taslak(s1)
    s2 = GorevServisi(kok, bildir=bildir)                 # yeni süreç: kod bellekte değil
    son = s2.durum("deneme/tel")
    assert (son["durum"], son["neden"]) == ("dustu", "yeniden_baslatma")
    with dis_baglam(), pytest.raises(GorevHatasi):
        await s2.onayla("deneme/tel", kod=d["onay_kodu"])


async def test_ayni_anda_tek_taslak(servis):
    await _taslak(servis, ad="bir")
    with pytest.raises(GorevHatasi, match="onay bekleyen") as e:
        await _taslak(servis, ad="iki")
    assert e.value.http == 409


async def test_iz_tek_satir_icerik_ve_kod_diske_yazilmaz(servis, kok):
    d = await _taslak(servis, istek="Luna için GİZLİ istek")
    with dis_baglam():
        await servis.durdur("deneme/tel")                    # taslağı iptal
    olaylar = [json.loads(s) for s in
               (kok / "deneme" / "tel" / alan.AYRILMIS / "olaylar.jsonl").read_text().splitlines()]
    assert [o["olay"] for o in olaylar] == ["taslak", "iptal", "dustu"]
    assert olaylar[0]["kaynak"] == "dis" and olaylar[1]["kaynak"] == "dis"
    assert all("GİZLİ" not in json.dumps(o, ensure_ascii=False) for o in olaylar)
    for f in kok.rglob("*"):
        if f.is_file():
            assert d["onay_kodu"] not in f.read_text(encoding="utf-8"), f"onay kodu diske yazıldı: {f}"
    assert servis.durum("deneme/tel")["durum"] == "dustu"


# ══════════════════════════════════════════════════════════════════════════
#  ⑪ Dış görevde genel dosya / uygulama / panel / MCP → red
# ══════════════════════════════════════════════════════════════════════════

# Bilerek GENİŞ bir tür: genel araçları açık. Yerelde bunlar call_tool kapısına gider;
# dışarıdan açılan görevde hiçbiri gitmemeli (kapı türün listesine değil KAYNAĞA bakar).
GENIS = GorevTuru(
    ad="genis", aciklama="test", araclar=("alan_agac", "alan_oku", "alan_yaz"),
    genel_araclar=("write_file", "append_file", "read_file", "open_application",
                   "open_panel", "panel_click", "web_search"),
    dis_araclar=("web_search",),
    tavanlar=GorevTavanlari(adim=5, sure_sn=60, token=100_000),
)
YASAKLILAR = ["write_file", "append_file", "read_file", "open_application",
              "open_panel", "panel_click", "mcp__fs__write_file"]


@pytest.fixture
def genis_servis(kok, bildir):
    return GorevServisi(kok, turler={"genis": GENIS}, bildir=bildir)


async def _dis_gorev_kos(servis, llm, onaylayan="dis"):
    with patch("app.services.llm_router.get_router", return_value=llm.router()):
        d = await _taslak(servis, tur="genis", ad="t")
        ctx = dis_baglam() if onaylayan == "dis" else yerel_baglam()
        with ctx:
            await servis.onayla("genis/t", kod=d["onay_kodu"] if onaylayan == "dis" else None)
        return await servis.bekle("genis/t", 5)


def _arac_sonucu(llm):
    return [m["content"] for m in llm.cagrilar[-1] if m["role"] == "tool"][0]


@pytest.mark.parametrize("arac", YASAKLILAR)
async def test_dis_gorevde_genel_arac_reddedilir_dispatchera_gitmez(genis_servis, arac):
    llm = SahteLLM([_arac_akisi([("c0", arac, {"command": "id", "path": "/tmp/x", "content": "x"})]),
                    _icerik_akisi("bitti")])
    with patch("app.services.tools.call_tool", new=AsyncMock(return_value="ÇALIŞTI")) as ct:
        d = await _dis_gorev_kos(genis_servis, llm)
    assert ct.await_count == 0, f"{arac} dış görevde call_tool'a ulaştı"
    assert _arac_sonucu(llm).startswith("Hata") and d["durum"] == "bitti"


async def test_ayni_tur_yerelde_genel_araci_cagirir(genis_servis):
    """Kontrol: kapı türün listesinde değil görevin kaynağında — yerel görev aynı aracı çalıştırır."""
    llm = SahteLLM([_arac_akisi([("c0", "read_file", {"path": "/tmp/x"})]), _icerik_akisi("bitti")])
    with patch("app.services.tools.call_tool", new=AsyncMock(return_value="ÇALIŞTI")) as ct, \
         patch("app.services.llm_router.get_router", return_value=llm.router()), yerel_baglam():
        await genis_servis.baslat("genis", "y", "yap")
        await genis_servis.bekle("genis/y", 5)
    assert ct.await_count == 1 and _arac_sonucu(llm).endswith("ÇALIŞTI")  # read_file sonucu "dış içerik" başlığı taşır


async def test_dis_gorevde_turun_dis_araci_calisir(genis_servis):
    llm = SahteLLM([_arac_akisi([("c0", "web_search", {"query": "luna"})]), _icerik_akisi("bitti")])
    with patch("app.services.tools.call_tool", new=AsyncMock(return_value="SONUÇ")) as ct:
        await _dis_gorev_kos(genis_servis, llm)
    assert ct.await_count == 1


async def test_telefon_taslagini_masaustu_onaylasa_da_gorev_dis_kalir(genis_servis):
    baglam = []
    llm = SahteLLM([_arac_akisi([("c0", "read_file", {"path": "/etc/hostname"})]), _icerik_akisi("bitti")])
    asil = llm._create

    async def _izle(**kw):
        baglam.append(is_external())          # LLM çağrısı görevin asyncio bağlamında koşar
        return await asil(**kw)
    llm.client.chat.completions.create = AsyncMock(side_effect=_izle)
    with patch("app.services.tools.call_tool", new=AsyncMock(return_value="ÇALIŞTI")) as ct:
        await _dis_gorev_kos(genis_servis, llm, onaylayan="yerel")
    assert baglam and all(baglam), f"görev bağlamı dış değil: {baglam}"
    assert ct.await_count == 0


async def test_kaynagi_yazili_olmayan_eski_kayit_dis_sayilir(genis_servis, kok):
    """Faz 0d öncesi kayıt `kaynak` taşımaz → fail-closed: dış."""
    async def _asili():
        await asyncio.sleep(60)
    llm = SahteLLM([_asili])
    with patch("app.services.tools.call_tool", new=AsyncMock(return_value="ÇALIŞTI")) as ct, \
         patch("app.services.llm_router.get_router", return_value=llm.router()), yerel_baglam():
        await genis_servis.baslat("genis", "eski", "yap")
        await genis_servis.durdur("genis/eski")
        dj = kok / "genis" / "eski" / alan.AYRILMIS / "durum.json"
        d = json.loads(dj.read_text())
        d.pop("kaynak")
        dj.write_text(json.dumps(d))
        llm.yanitlar[:] = [_arac_akisi([("c1", "read_file", {"path": "/x"})]), _icerik_akisi("son")]
        await genis_servis.devam("genis/eski", onay=True)
        await genis_servis.bekle("genis/eski", 5)
    assert ct.await_count == 0
    assert _arac_sonucu(llm).startswith("Hata")


@pytest.mark.parametrize("ad", ["append_file", "write_file", "read_file", "open_application", "open_panel",
                                "panel_click", "mcp__x__y", "skill__z", "delegate_to_persona"])
def test_dis_araclara_yasak_arac_yazilamaz(ad):
    assert dis_yasak_mi(ad)
    with pytest.raises(ValueError):
        tur_dogrula(GorevTuru(ad="k", aciklama="", araclar=(), genel_araclar=(ad,), dis_araclar=(ad,)))


def test_dis_araclar_genel_araclarin_alt_kumesi():
    with pytest.raises(ValueError, match="alt küme"):
        tur_dogrula(GorevTuru(ad="k", aciklama="", araclar=(), dis_araclar=("web_search",)))


def test_dis_yasak_env_ile_daraltilamaz(monkeypatch):
    monkeypatch.setenv("EXTERNAL_DENY_TOOLS", "hicbir_sey")
    assert dis_yasak_mi("write_file") and dis_yasak_mi("read_file")


# ══════════════════════════════════════════════════════════════════════════
#  ⑫ Sohbetten dış bağlamla tür aracı → red
# ══════════════════════════════════════════════════════════════════════════





async def test_sohbet_dongusu_dis_baglamda_tur_aracini_calistiramaz(tmp_path, monkeypatch):
    """Model şemada olmayan `alan_yaz`'ı uydursa da sohbet yolu (gorev=None) reddeder."""
    monkeypatch.chdir(tmp_path)
    llm = SahteLLM([_arac_akisi([("c0", "alan_yaz", {"yol": "a.txt", "icerik": "x"})]),
                    _icerik_akisi("tamam")])
    with dis_baglam(), patch("app.services.llm_router.get_router", return_value=llm.router()):
        r = LLMRunner(llm.client, "gpt-5.6-luna", tools=[], max_steps=3)
        _ = [p async for p in r.run([{"role": "user", "content": "yaz"}])]
    tool = [m["content"] for c in llm.cagrilar for m in c if m["role"] == "tool"]
    assert tool and tool[0].startswith("Hata") and not (tmp_path / "a.txt").exists()
    assert list(tmp_path.iterdir()) == []


# ══════════════════════════════════════════════════════════════════════════
#  HTTP — ⑬ tavan · ⑮ token/Origin (ana uygulama, auth ara katmanı gerçek)
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def api(kok, bildir):
    s = GorevServisi(kok, bildir=bildir)
    s._kos_baslat = MagicMock()          # bu testler kapıyı ölçer; koşu ayrı (⑭ gerçek HTTP)
    with patch.object(gorev_mod, "_servis", s), patch.object(main_mod, "AUTH_TOKEN", TOKEN):
        # `with` YOK → lifespan koşmaz. localhost = güvenilir yerel ad.
        yield TestClient(main_mod.app, base_url="http://localhost:8001", client=("127.0.0.1", 50000)), s


GOVDE = {"tur": "deneme", "ad": "tel", "istek": "yap"}


@pytest.mark.parametrize("basliklar", [{}, {"Authorization": "Bearer yanlis"},
                                       {"Authorization": f"Bearer {TOKEN[:-1]}"}])
def test_tokensiz_ya_da_yanlis_tokenla_401(api, basliklar):
    c, s = api
    for yol, govde in (("/api/gorev/baslat", GOVDE), ("/api/gorev/deneme/tel/onayla", {"kod": "x"})):
        h = {**basliklar, "X-Forwarded-For": "100.64.0.7", "Origin": TS}
        assert c.post(yol, json=govde, headers=h).status_code == 401
    assert s.liste() == []


@pytest.mark.parametrize("origin", [None, "https://uzak.ornek.example", "https://kotu.example",
                                    "https://yuki.ornek.example.kotu.example", "http://localhost:9999",
                                    "https://baska.ornek.example", "null"])
def test_dis_istekte_ts_net_disi_origin_403(api, origin):
    c, s = api
    h = {**YETKI, "X-Forwarded-For": "100.64.0.7"}
    if origin:
        h["Origin"] = origin
    r = c.post("/api/gorev/baslat", json=GOVDE, headers=h)
    assert r.status_code == 403, r.text
    assert s.liste() == [] and s._kos_baslat.call_count == 0


def test_dis_onayda_da_origin_kapisi(api):
    c, s = api
    kod = c.post("/api/gorev/baslat", json=GOVDE, headers=TELEFON).json()["onay_kodu"]
    for origin in (None, "https://kotu.example"):
        h = {**YETKI, "X-Forwarded-For": "100.64.0.7", **({"Origin": origin} if origin else {})}
        assert c.post("/api/gorev/deneme/tel/onayla", json={"kod": kod}, headers=h).status_code == 403
    assert s.durum("deneme/tel")["durum"] == "bekliyor" and s._kos_baslat.call_count == 0


def test_telefon_akisi_taslak_sonra_kodla_onay(api, bildir):
    c, s = api
    r = c.post("/api/gorev/baslat", json=GOVDE, headers=TELEFON)
    assert r.status_code == 200
    g = r.json()
    assert (g["durum"], g["kaynak"]) == ("bekliyor", "dis") and g["onay_kodu"]
    assert g["alan"].endswith("/deneme/tel/") and g["tavanlar"]["adim"] == 10 and g["onay_son"]
    assert s._kos_baslat.call_count == 0 and len(bildir) == 1
    liste = c.get("/api/gorev", headers=TELEFON).json()
    assert liste["baglam"] == "dis" and liste["onay_kipi"] == "dokunus"
    assert g["onay_kodu"] not in json.dumps(liste), "kod listeye sızdı"
    assert {t["ad"] for t in liste["turler"]} >= {"site", "deneme"}
    assert c.post("/api/gorev/deneme/tel/onayla", json={"kod": "yanlis"}, headers=TELEFON).status_code == 403
    r = c.post("/api/gorev/deneme/tel/onayla", json={"kod": g["onay_kodu"]}, headers=TELEFON)
    assert r.status_code == 200 and r.json()["durum"] == "kosuyor"
    assert s._kos_baslat.call_count == 1


def test_masaustu_kipinde_kod_telefona_verilmez(api, monkeypatch):
    monkeypatch.setenv("YUKI_ATOLYE_DIS_ONAY", "masaustu")
    c, s = api
    g = c.post("/api/gorev/baslat", json=GOVDE, headers=TELEFON).json()
    assert g["durum"] == "bekliyor" and g["onay_kodu"] is None
    assert c.post("/api/gorev/deneme/tel/onayla", json={"kod": "x"}, headers=TELEFON).status_code == 403
    r = c.post("/api/gorev/deneme/tel/onayla", json={}, headers=YETKI)          # masaüstü (yerel)
    assert r.status_code == 200 and r.json()["durum"] == "kosuyor"


def test_yerel_baslatma_hemen_kosar_kod_yok(api):
    c, s = api
    r = c.post("/api/gorev/baslat", json=GOVDE, headers=YETKI)
    assert r.status_code == 200
    g = r.json()
    assert (g["durum"], g["kaynak"]) == ("kosuyor", "yerel") and "onay_kodu" not in g
    assert s._kos_baslat.call_count == 1


def test_yerel_istekte_yabanci_origin_403(api):
    """Masaüstündeki yabancı sayfa localhost'a istek atamaz (CSRF)."""
    c, s = api
    r = c.post("/api/gorev/baslat", json=GOVDE, headers={**YETKI, "Origin": "https://kotu.example"})
    assert r.status_code == 403 and s.liste() == []
    r = c.post("/api/gorev/baslat", json=GOVDE, headers={**YETKI, "Origin": f"http://localhost:{cfg.PORT}"})
    assert r.status_code == 200


def test_telefondan_tavan_yukseltme_reddedilir(api):
    c, s = api
    r = c.post("/api/gorev/baslat", json={**GOVDE, "tavan": {"adim": 500}}, headers=TELEFON)
    assert r.status_code == 403 and "tavan" in r.json()["detail"]
    for alan_adi in ("tavanlar", "adim", "sure_sn", "token"):            # gövdeye kaçak alan
        r = c.post("/api/gorev/baslat", json={**GOVDE, alan_adi: 999}, headers=TELEFON)
        assert r.status_code == 422, alan_adi
    assert s.liste() == []
    kod = c.post("/api/gorev/baslat", json=GOVDE, headers=TELEFON).json()["onay_kodu"]
    r = c.post("/api/gorev/deneme/tel/onayla", json={"kod": kod, "tavan": {"adim": 500}}, headers=TELEFON)
    assert r.status_code == 422
    assert s.durum("deneme/tel")["tavanlar"]["adim"] == 10


def test_telefondan_devam_ve_uzatma_reddedilir(api):
    c, s = api
    with yerel_baglam():
        asyncio.run(s.baslat("deneme", "u", "yap"))
    d = s.durum("deneme/u")
    d["durum"], d["neden"] = "yarim", "adim"
    s._yaz(d)
    r = c.post("/api/gorev/deneme/u/devam", json={"onay": True, "uzat": {"adim": 100}}, headers=TELEFON)
    assert r.status_code == 403
    assert s.durum("deneme/u")["tavanlar"]["adim"] == 10


def test_yerel_baslatma_tavan_verebilir_dogrulanir(api):
    c, s = api
    r = c.post("/api/gorev/baslat", json={**GOVDE, "tavan": {"adim": 3}}, headers=YETKI)
    assert r.status_code == 200 and s.durum("deneme/tel")["tavanlar"]["adim"] == 3
    for kotu in ({"adim": -1}, {"adim": True}, {"ucretli_dusus": 1}, {"arac_zaman_asimi": 999}):
        r = c.post("/api/gorev/baslat", json={**GOVDE, "ad": "k", "tavan": kotu}, headers=YETKI)
        assert r.status_code == 400, kotu


# ══════════════════════════════════════════════════════════════════════════
#  ⑭ Telefondan DURDUR ≤2 sn — gerçek HTTP, ikinci port
# ══════════════════════════════════════════════════════════════════════════

def _bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def sunucu(tmp_path):
    port = _bos_port()
    assert port != 8001
    env = {**os.environ, "YUKI_ATOLYE_KOK": str(tmp_path / "kok"), "OPENROUTER_API_KEY": "sahte-test"}
    p = subprocess.Popen([sys.executable, "tests/gorev_sahte_sunucu.py", "--port", str(port),
                          "--onay-suresi", "2", "--dis-origin", TS],
                         cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    url = f"http://127.0.0.1:{port}"
    son = time.monotonic() + 30
    while time.monotonic() < son:
        try:
            if httpx.get(f"{url}/test/durum", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        p.kill()
        pytest.fail("ikinci port sunucusu açılmadı: " + p.stderr.read().decode()[-500:])
    yield url
    p.terminate()
    p.wait(5)


def _durum(url, gid):
    return next(g for g in httpx.get(f"{url}/api/gorev").json()["gorevler"] if g["id"] == gid)


def test_telefondan_baslat_onayla_durdur_iki_saniye(sunucu):
    url, h = sunucu, {"X-Forwarded-For": "100.64.0.7", "Origin": TS}
    httpx.post(f"{url}/test/llm", json={"adimlar": 1000, "gecikme": 0.5})
    r = httpx.post(f"{url}/api/gorev/baslat", json={"tur": "deneme", "ad": "tel", "istek": "yap"}, headers=h)
    assert r.status_code == 200 and r.json()["durum"] == "bekliyor"
    kod = r.json()["onay_kodu"]
    time.sleep(0.8)
    durum = httpx.get(f"{url}/test/durum").json()
    assert durum["llm_cagri"] == 0 and len(durum["bildirimler"]) == 1      # onaysız → model yok
    r = httpx.post(f"{url}/api/gorev/deneme/tel/onayla", json={"kod": kod}, headers=h)
    assert r.status_code == 200 and r.json()["durum"] == "kosuyor"
    son = time.monotonic() + 5
    while _durum(url, "deneme/tel")["adim"] < 2:
        assert time.monotonic() < son, "görev adım atmadı"
        time.sleep(0.05)
    t0 = time.monotonic()
    r = httpx.post(f"{url}/api/gorev/deneme/tel/durdur", headers=h, timeout=10)
    gecen = time.monotonic() - t0
    assert r.status_code == 200 and r.json()["durum"] == "durdu" and gecen <= 2.0, (gecen, r.json().get("neden"), r.json().get("ozet"))
    n = httpx.get(f"{url}/test/durum").json()["llm_cagri"]
    time.sleep(1.5)
    assert httpx.get(f"{url}/test/durum").json()["llm_cagri"] == n, "DURDUR sonrası model çağrıldı"
    # DEVAM telefondan kapalı (masaüstünden)
    assert httpx.post(f"{url}/api/gorev/deneme/tel/devam", json={"onay": True},
                      headers=h).status_code == 403


def test_ikinci_portta_onaysiz_taslak_suresinde_duser(sunucu):
    url, h = sunucu, {"X-Forwarded-For": "100.64.0.7", "Origin": TS}
    r = httpx.post(f"{url}/api/gorev/baslat", json={"tur": "deneme", "ad": "dus", "istek": "yap"}, headers=h)
    assert r.json()["durum"] == "bekliyor"
    time.sleep(2.6)                                       # --onay-suresi 2 (gerçekte 300)
    g = _durum(url, "deneme/dus")
    assert (g["durum"], g["neden"]) == ("dustu", "onay_suresi")
    assert httpx.get(f"{url}/test/durum").json()["llm_cagri"] == 0


@pytest.mark.parametrize("ad", sorted(alan.ARACLAR))
async def test_tur_araclari_genel_dispatchera_girmez(ad, tmp_path, monkeypatch):
    """Tür araçları (`alan_*`, `kaynak_*`) yalnız görev kapısından çalışır: sohbetin `call_tool`'u
    bu adları tanımaz — dış bağlamdan da, yerel bağlamdan da çağrılamaz."""
    monkeypatch.chdir(tmp_path)
    from app.services.tools import call_tool
    for ctx in (dis_baglam(), yerel_baglam()):
        with ctx:
            sonuc = await call_tool(ad, {"yol": "kacis.txt", "icerik": "x"})
        assert sonuc.startswith("Hata") and not (tmp_path / "kacis.txt").exists()

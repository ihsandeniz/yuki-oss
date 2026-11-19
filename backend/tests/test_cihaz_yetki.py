"""Cihaz ajanının riskli eylemleri — varsayılan KAPALI, açmak erişim anahtarı ister (karar 2026-11-01).

`writefile` / `deletefile` / `killproc` kurulumdan kapalı gelir. Açma ucu `AUTH_TOKEN` ile aynı
anahtarı ister; `AUTH_TOKEN` boşsa hiçbir anahtar (boş anahtar dahil) açamaz. Ayar açıkken anahtar
sonradan boşaltılırsa eylem yine reddedilir. Kapatmak serbest. Genel ayar ucu bu anahtarları yazamaz.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import config as cfg
from app import config_manager
from app.limiter import limiter
from app.main import app
from app.services import cihaz_yetki
from app.services import device_manager as dm

c = TestClient(app)
ANAHTAR = "dogru-anahtar-0123456789abcdef0123"
RISKLI = ("writefile", "deletefile", "killproc")


@pytest.fixture(autouse=True)
def sayac_sifir():
    """`PUT /izinler` dakikada 10 — slowapi sayacı süreç boyu yaşar, testler arası sıfırla."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def sahte_cihaz(monkeypatch):
    gonderilen: list[str] = []

    class Sahte:
        async def send_command(self, action, args, timeout):
            gonderilen.append(action)
            return {"ok": True}

    monkeypatch.setattr(dm, "get", lambda _id: Sahte())
    return gonderilen


@pytest.fixture()
def anahtar(monkeypatch):
    monkeypatch.setattr(cfg, "AUTH_TOKEN", ANAHTAR)


@pytest.fixture()
def anahtarsiz(monkeypatch):
    monkeypatch.setattr(cfg, "AUTH_TOKEN", "")


def _ac(eylem, anahtar_degeri):
    return c.put("/api/devices/izinler", json={"eylem": eylem, "acik": True, "anahtar": anahtar_degeri})


# ── ① varsayılan kapalı ──────────────────────────────────────────────────────

@pytest.mark.parametrize("eylem", RISKLI)
def test_varsayilan_KAPALI_cihaza_gitmez(anahtar, sahte_cihaz, eylem):
    r = c.post("/api/devices/x/command", json={"action": eylem, "args": {}})
    assert r.status_code == 403
    assert sahte_cihaz == []


def test_durum_varsayilan_hepsi_kapali(anahtar):
    d = c.get("/api/devices/izinler").json()
    assert d["izinler"] == {e: False for e in RISKLI}
    assert d["anahtar_kurulu"] is True


def test_zararsiz_eylem_etkilenmez(anahtarsiz, sahte_cihaz):
    assert c.post("/api/devices/x/command", json={"action": "ping"}).status_code == 200
    assert sahte_cihaz == ["ping"]


# ── ② açma kapısı ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("deger", ["", "herhangi", ANAHTAR])
def test_AUTH_TOKEN_bosken_hicbir_anahtar_ACAMAZ(anahtarsiz, deger):
    r = _ac("writefile", deger)
    assert r.status_code == 409
    assert config_manager.get("CIHAZ_IZIN_DOSYA_YAZ") is None


@pytest.mark.parametrize("deger", ["", "yanlis", ANAHTAR[:-1]])
def test_yanlis_ya_da_bos_anahtar_ACAMAZ(anahtar, deger):
    r = _ac("deletefile", deger)
    assert r.status_code == 403
    assert config_manager.get("CIHAZ_IZIN_DOSYA_SIL") is None


@pytest.mark.parametrize("eylem", RISKLI)
def test_dogru_anahtarla_acilir_ve_gider(anahtar, sahte_cihaz, eylem):
    r = _ac(eylem, ANAHTAR)
    assert r.status_code == 200
    assert r.json()["izinler"][eylem] is True
    # yalnız açılan açık, öbürleri kapalı
    assert [e for e, v in r.json()["izinler"].items() if v] == [eylem]
    assert c.post("/api/devices/x/command", json={"action": eylem, "args": {}}).status_code == 200
    assert sahte_cihaz == [eylem]


def test_bilinmeyen_eylem_400(anahtar):
    assert _ac("exec", ANAHTAR).status_code == 400


# ── ③ kapatma serbest, anahtar düşerse fail-closed ───────────────────────────

def test_kapatmak_anahtarsiz_serbest(anahtar, sahte_cihaz, monkeypatch):
    assert _ac("killproc", ANAHTAR).status_code == 200
    monkeypatch.setattr(cfg, "AUTH_TOKEN", "")
    r = c.put("/api/devices/izinler", json={"eylem": "killproc", "acik": False})
    assert r.status_code == 200
    assert config_manager.get("CIHAZ_IZIN_SUREC_KAPAT") is False


def test_ayar_acikken_anahtar_bosalirsa_REDDEDILIR(anahtar, sahte_cihaz, monkeypatch):
    assert _ac("writefile", ANAHTAR).status_code == 200
    monkeypatch.setattr(cfg, "AUTH_TOKEN", "")
    r = c.post("/api/devices/x/command", json={"action": "writefile", "args": {}})
    assert r.status_code == 403
    assert sahte_cihaz == []


def test_ayar_okunamazsa_kapali(anahtar, monkeypatch):
    def patla(*a, **k):
        raise OSError("disk")
    monkeypatch.setattr(config_manager, "get", patla)
    assert cihaz_yetki.izinli("deletefile") is False


# ── ④ genel ayar ucu bu kapıyı atlayamaz ─────────────────────────────────────

@pytest.mark.parametrize("ad", sorted(cihaz_yetki.RISKLI_EYLEMLER.values()))
def test_genel_ayar_ucundan_YAZILAMAZ(anahtar, ad):
    from app.api import settings_api
    assert ad in settings_api.AYRI_KAPILI
    c.post(f"/api/settings/{ad}", json={"value": True})
    assert config_manager.get(ad) is None


def test_bos_bos_eslesmesi_KABUL_EDILMEZ(anahtarsiz):
    """`compare_digest("", "")` True döner — kapı API'deki 409'a yaslanmasın, fonksiyon kendisi reddetsin."""
    assert cihaz_yetki.anahtar_dogru("") is False
    assert cihaz_yetki.anahtar_dogru(None) is False

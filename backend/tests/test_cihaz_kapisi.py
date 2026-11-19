"""Cihaz yönetimi — kademe kapısı + eşleştirme kimliği (2026-09-18).

🔴 **Bu dosyanın ilk sebebi bir REGRESYON koruması.** `/ws/agent` şöyleydi:

    if AUTH_TOKEN and not secrets.compare_digest(_token, AUTH_TOKEN):

`AUTH_TOKEN` üründe boş → `and`in solu falsy → koşul kısa devre → `ws.close()`
hiç çağrılmaz. Canlı ölçüldü: **token verilmeden bağlanılıp sahte cihaz kaydedildi.**
`test_ws_kimliksiz_REDDEDILIR` tam bunu bekler; o test kırmızıysa açık geri gelmiştir.

⚠️ Modülde İKİ router var ve ikisi ayrı korunur (REST `Depends`, WS el-içi
`close(4403)`). Birini kapatıp öbürünü unutmak en kolay hata — ikisi de ölçülür.
"""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from app.api import devices_api
from app.main import app
from app.services import cihaz_eslestirme as ce
from app.services import device_manager as dm


@pytest.fixture()
def gecici_depo(tmp_path, monkeypatch):
    """Gerçek cihazlar.json'a DOKUNMA."""
    monkeypatch.setenv("YUKI_DATA_DIR", str(tmp_path))
    ce.kod_iptal()
    yield tmp_path
    ce.kod_iptal()


@pytest.fixture()
def ultra():
    yield  # kademe yok — yetki her zaman açık


c = TestClient(app)


# ── ① REST kademe kapısı ─────────────────────────────────────────────────────

def test_rest_router_kapiyi_tasiyor():
    adlar = [d.dependency.__name__ for d in devices_api.router.dependencies
             if getattr(d, "dependency", None)]
    assert "require_devices" in adlar


def test_rest_ultra_gecer(ultra, gecici_depo):
    assert c.get("/api/devices").status_code == 200
    assert c.get("/api/devices/eslestirilmis").status_code == 200


def test_ws_kimliksiz_REDDEDILIR(ultra, gecici_depo):
    """🔴 Açığın kendisi: eskiden bu bağlantı KABUL EDİLİYORDU."""
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as e:
        with c.websocket_connect("/ws/agent"):
            pass
    assert e.value.code == 4401


def test_ws_yanlis_kod_REDDEDILIR(ultra, gecici_depo):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as e:
        with c.websocket_connect("/ws/agent?eslestirme=YANLISKOD"):
            pass
    assert e.value.code == 4401


def test_ws_gecerli_kod_baglanir_ve_token_verir(ultra, gecici_depo):
    kod = ce.kod_uret()["kod"]
    with c.websocket_connect(f"/ws/agent?eslestirme={kod}&ad=Telefon") as ws:
        mesaj = json.loads(ws.receive_text())
    assert mesaj["type"] == "eslestirildi"
    assert mesaj["cihaz_token"]
    assert ce.token_dogrula(mesaj["cihaz_token"]) is not None


def test_ws_cihaz_tokeniyle_tekrar_baglanir(ultra, gecici_depo):
    kod = ce.kod_uret()["kod"]
    with c.websocket_connect(f"/ws/agent?eslestirme={kod}") as ws:
        token = json.loads(ws.receive_text())["cihaz_token"]
    # İkinci bağlantı kodsuz, token ile — ve yeni token GÖNDERİLMEZ
    with c.websocket_connect(f"/ws/agent?cihaz={token}") as ws:
        ws.send_text('{"type":"heartbeat"}')
    assert True   # kapanmadan buraya geldiyse kabul edildi


# ── ③ Eşleştirme kodu disiplini ──────────────────────────────────────────────

def test_kod_TEK_KULLANIMLIK(gecici_depo):
    kod = ce.kod_uret()["kod"]
    assert ce.kod_dogrula(kod) is not None
    assert ce.kod_dogrula(kod) is None, "aynı kod ikinci kez kabul edildi"


def test_kod_suresi_gecince_olur(gecici_depo, monkeypatch):
    """QR ekranda unutulsa bile pencere 5 dakikada kapanmalı."""
    simdi = time.time()
    kod = ce.kod_uret()["kod"]
    monkeypatch.setattr(ce.time, "time", lambda: simdi + ce.KOD_OMRU_SN + 1)
    assert ce.kod_dogrula(kod) is None


def test_yeni_kod_eskisini_gecersiz_kilar(gecici_depo):
    eski = ce.kod_uret()["kod"]
    ce.kod_uret()
    assert ce.kod_dogrula(eski) is None, "iki kod aynı anda geçerli — görünmeyen kapı"


def test_yanlis_deneme_kodu_yakar(gecici_depo):
    kod = ce.kod_uret()["kod"]
    for _ in range(ce.MAX_DENEME):
        ce.kod_dogrula("YANLIS00")
    assert ce.kod_dogrula(kod) is None, "kaba kuvvet penceresi açık kaldı"


def test_bos_kod_reddedilir(gecici_depo):
    ce.kod_uret()
    assert ce.kod_dogrula("") is None


# ── ④ Token diske DÜZ yazılmaz ───────────────────────────────────────────────

def test_token_diskte_duz_DURMAZ(gecici_depo):
    kod = ce.kod_uret()["kod"]
    token = ce.kod_dogrula(kod)
    ham = ce.cihaz_dosyasi().read_text(encoding="utf-8")
    assert token not in ham, "cihaz tokeni dosyada DÜZ duruyor — yedeğe/Drive'a sızar"
    assert "token_ozet" in ham


def test_listede_ozet_SIZMAZ(gecici_depo):
    ce.kod_dogrula(ce.kod_uret()["kod"])
    for cihaz in ce.cihazlar():
        assert "token_ozet" not in cihaz


def test_bos_token_reddedilir(gecici_depo):
    assert ce.token_dogrula("") is None
    assert ce.token_dogrula("uydurma") is None


# ── ⑤ Cihaz kimliğini CİHAZ seçemez ──────────────────────────────────────────

def test_cihaz_baskasinin_kimligine_buremez(ultra, gecici_depo):
    """Eskiden `msg.get("device_id")` önceliyordu → cihaz başkasının kaydını ezerdi."""
    kod = ce.kod_uret()["kod"]
    with c.websocket_connect(f"/ws/agent?eslestirme={kod}") as ws:
        gercek_id = json.loads(ws.receive_text())["cihaz_id"]
        ws.send_text(json.dumps({"type": "register", "device_id": "BASKA-CIHAZ",
                                 "hostname": "sahte"}))
        time.sleep(0.2)
        kayitli = [d.device_id for d in dm.get_all()]
    assert "BASKA-CIHAZ" not in kayitli, "cihaz kendi kimliğini seçebildi"
    assert gercek_id in kayitli


# ── ⑥ Ağ durumu DÜRÜST ───────────────────────────────────────────────────────

def test_ag_durumu_localhost_uyarir():
    """HOST=127.0.0.1 iken panel 'bağlanabilir' gibi görünmemeli."""
    ag = devices_api._ag_durumu()
    if ag["host"] in ("127.0.0.1", "localhost", "::1", ""):
        assert ag["agda_erisilebilir"] is False
        assert ag["uyari"], "kullanıcıya sebep söylenmiyor"
    else:
        assert ag["agda_erisilebilir"] is True
        assert ag["uyari"] is None




# ── açık kaynak: cihaza komut çalıştırma gönderilmez ─────────────────────────

def test_exec_eylemi_cihaza_GITMEZ(gecici_depo, monkeypatch):
    gonderilen = []

    class Sahte:
        async def send_command(self, action, args, timeout):
            gonderilen.append(action)
            return {"ok": True}

    monkeypatch.setattr(dm, "get", lambda _id: Sahte())
    r = c.post("/api/devices/x/command", json={"action": "exec", "args": {"command": "id"}})
    assert r.status_code == 400
    assert gonderilen == []
    assert c.post("/api/devices/x/command", json={"action": "ping"}).status_code == 200
    assert gonderilen == ["ping"]

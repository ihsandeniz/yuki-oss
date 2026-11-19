"""Yerel motor kapısı (v0.8.1) — saldırı vakaları. Kapatır: C1 (link), H1 (DNS rebinding), H3 (/ws/screen), H7.

Her vaka bir saldırgan şeklidir; geçmemesi gerekir. Kapının KIRMAMASI gerekenler de burada:
Electron arayüzü (çerezli), aynı kökenli uzak arayüz (ağa açık kurulum), tünel (AUTH_TOKEN), cihaz ajanı.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import app.main as ana
from app.main import app
from app.yerel_kapi import CEREZ_ADI, YerelKapi

ANAHTAR = "a" * 64
YEREL = ("127.0.0.1", 50000)
KOK = "http://127.0.0.1:8791"


def _mini(token_kabul=lambda t: t == "tunel-parolasi"):
    """Kapının mantığını uç kodundan bağımsız ölçmek için küçük uygulama."""
    m = FastAPI()

    @m.get("/api/gizli")
    async def gizli():
        return {"ok": True}

    @m.get("/health")
    async def saglik():
        return {"ok": True}

    @m.websocket("/ws/screen")
    async def ekran(ws: WebSocket):
        await ws.accept()
        await ws.send_text("kare")
        await ws.close()

    m.add_middleware(YerelKapi, acik_yollar={"/health"}, acik_onekler=("/ui/",),
                     izinli_kokenler=[KOK, "http://localhost:8791"], token_kabul=token_kabul)
    return m


@pytest.fixture
def anahtarli(monkeypatch):
    monkeypatch.setenv("YUKI_OTURUM_ANAHTARI", ANAHTAR)


def _istemci(app_=None, client=YEREL, base=KOK):
    return TestClient(app_ or _mini(), client=client, base_url=base)


# ── 1) Host — DNS rebinding ──────────────────────────────────────────── #
def test_rebinding_yabanci_host_403_tam_uygulamada():
    c = _istemci(app, base="http://evil.example:8791")
    assert c.get("/api/settings").status_code == 403
    assert c.get("/health").status_code == 403, "Host kuralı açık yollarda da geçerli olmalı"


@pytest.mark.parametrize("host", ["127.0.0.1:8791", "localhost:8791", "[::1]:8791"])
def test_yerel_host_gecer(host):
    c = _istemci()
    assert c.get("/health", headers={"host": host}).status_code == 200


def test_tunel_hostu_extra_ile_izinli(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS_EXTRA", "https://yuki.ornek.net")
    assert _istemci(base="https://yuki.ornek.net").get("/health").status_code == 200


def test_agdan_gelen_istekte_host_kurali_yok():
    """Ağa açık kurulumda telefon LAN IP'siyle gelir — onu kilit korur, Host kuralı değil."""
    c = _istemci(client=("192.168.1.50", 5555), base="http://192.168.1.10:8791")
    assert c.get("/health").status_code == 200


# ── 2) Origin ────────────────────────────────────────────────────────── #
@pytest.mark.parametrize("koken", ["http://evil.example", "http://127.0.0.1:9999", "null", "file://"])
def test_yabanci_origin_403(koken):
    """127.0.0.1:9999 — çerezler porta göre ayrılmaz; Origin denetimi bu yüzden zorunlu."""
    assert _istemci().get("/health", headers={"origin": koken}).status_code == 403


def test_izinli_ve_ayni_koken_origin_gecer():
    assert _istemci().get("/health", headers={"origin": KOK}).status_code == 200
    uzak = _istemci(client=("192.168.1.50", 5555), base="http://192.168.1.10:8791")
    assert uzak.get("/health", headers={"origin": "http://192.168.1.10:8791"}).status_code == 200


def test_ws_screen_yabanci_origin_reddedilir():
    with pytest.raises(WebSocketDisconnect):
        with _istemci().websocket_connect("ws://127.0.0.1:8791/ws/screen",
                                          headers={"origin": "http://evil.example"}) as ws:
            ws.receive_text()


# ── 3) Oturum anahtarı (Electron çerezi) ─────────────────────────────── #
def test_anahtar_yoksa_gelistirici_yolu_degismez():
    assert _istemci().get("/api/gizli").status_code == 200


def test_cerezsiz_istek_401_link_saldirisi(anahtarli):
    """C1: müşterinin tarayıcısında çerez yok → link/fetch/rebinding hepsi 401."""
    c = _istemci()
    assert c.get("/api/gizli").status_code == 401
    c.cookies.set(CEREZ_ADI, "yanlis")
    assert c.get("/api/gizli").status_code == 401


def test_cerezli_electron_istegi_gecer(anahtarli):
    c = _istemci()
    c.cookies.set(CEREZ_ADI, ANAHTAR)
    assert c.get("/api/gizli").status_code == 200


def test_acik_yollar_cerezsiz_gecer(anahtarli):
    assert _istemci().get("/health").status_code == 200


def test_tunel_tokeni_cerezsiz_gecer(anahtarli):
    c = _istemci()
    assert c.get("/api/gizli", headers={"authorization": "Bearer tunel-parolasi"}).status_code == 200
    assert c.get("/api/gizli?token=tunel-parolasi").status_code == 200
    assert c.get("/api/gizli?token=sahte").status_code == 401


def test_ws_cerezsiz_reddedilir_cerezli_kabul(anahtarli):
    with pytest.raises(WebSocketDisconnect):
        with _istemci().websocket_connect("ws://127.0.0.1:8791/ws/screen",
                                          headers={"origin": KOK}) as ws:
            ws.receive_text()
    with _istemci().websocket_connect("ws://127.0.0.1:8791/ws/screen",
                                      headers={"origin": KOK, "cookie": f"{CEREZ_ADI}={ANAHTAR}"}) as ws:
        assert ws.receive_text() == "kare"


def test_tam_uygulamada_cerezsiz_api_401_saglik_200(anahtarli):
    c = _istemci(app)
    assert c.get("/api/settings").status_code == 401
    assert c.get("/health").status_code == 200
    assert c.get("/api/lock/status").status_code == 200, "kilit ekranı token almadan çağırır"


def test_tam_uygulamada_tunel_authtoken_cerezsiz_gecer(anahtarli, monkeypatch):
    monkeypatch.setattr(ana, "AUTH_TOKEN", "tunel-parolasi")
    c = _istemci(app)
    assert c.get("/api/lock/status", headers={"authorization": "Bearer tunel-parolasi"}).status_code == 200
    assert c.get("/api/settings").status_code == 401


# ── WS uçlarının kendi Origin denetimi kapıyla AYNI kural (v0.8.1) ───── #
def test_ws_uc_origin_kurali_kapiyla_ayni():
    from types import SimpleNamespace
    from app.api.websocket import _check_ws_origin

    def ws(origin, host="127.0.0.1:8791", sema="ws"):
        return SimpleNamespace(headers={"origin": origin, "host": host}, url=SimpleNamespace(scheme=sema))

    assert _check_ws_origin(ws("http://127.0.0.1:8791"))
    assert not _check_ws_origin(ws("http://127.0.0.1:8000.evil.example")), "startsWith açığı"
    assert not _check_ws_origin(ws("null"))
    assert not _check_ws_origin(ws("file://"))
    # ağa açık kurulum: telefonun arayüzü aynı kökenden
    assert _check_ws_origin(ws("http://192.168.1.10:8791", host="192.168.1.10:8791"))
    assert not _check_ws_origin(ws("http://evil.example", host="192.168.1.10:8791"))

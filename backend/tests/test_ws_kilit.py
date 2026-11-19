"""Kilit kuruluyken YEREL WebSocket de oturum token'ı ister — HTTP ile aynı kural (denetim 2026-11-16, API-F001).

Eskiden: kilit kurulu, `AUTH_TOKEN` boş (ürün varsayılanı) → HTTP `/api/ping` token'sız 401, ama
`/ws/realtime`, `/ws/screen` (ekran akışı), `/ws/native`, `/ws/gorus` (kamera) aynı makineden token'sız KABUL.
Tarayıcı kipinde (Electron çerezi yok) bu, kilidin hiç kurulmamış olması demekti.

Girişin bozulmadığı da burada ölçülür: kilit ekranından alınan token ile her iki kipte (tarayıcı + Electron
çerezi) aynı WS açılır; kilitsiz kurulumda yerel WS eskisi gibi token'sız açılır.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import config as cfg
from app.main import app
from app.services import app_lock, login_guard
from app.yerel_kapi import CEREZ_ADI

ANAHTAR = "c" * 64
PAROLA = "dogru-parola"


@pytest.fixture(autouse=True)
def izole(tmp_path, monkeypatch):
    from app.limiter import limiter
    monkeypatch.setattr(app_lock, "KILIT_DOSYASI", tmp_path / "app_lock.json")
    monkeypatch.setattr(app_lock, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "AUTH_TOKEN", "")
    monkeypatch.setattr("app.main.AUTH_TOKEN", "")
    monkeypatch.setattr(cfg, "AG_ACIK_SUREC", False)
    app_lock.tum_oturumlari_kapat()
    login_guard._sifirla()
    limiter.reset()

    async def _sahte_kare(*_a, **_k):   # kapı kırılırsa (mutasyon) /ws/screen gerçek ekranı OKUMASIN
        return None
    import app.api.websocket as w
    monkeypatch.setattr(w, "_capture_frame", _sahte_kare)
    yield
    app_lock.tum_oturumlari_kapat()
    login_guard._sifirla()
    limiter.reset()


def _yerel(**kw):
    return TestClient(app, client=("127.0.0.1", 5555), base_url="http://127.0.0.1:8791", **kw)


def _kod(c, yol, kapanis_bekle=False):
    """WS el sıkışması reddedilirse kapanış kodu; kabul edilirse 'acik'.
    `kapanis_bekle`: uç kabul edip hemen sebebiyle kapatıyorsa (gorus 4409, native 4503) o kodu oku."""
    try:
        # TestClient WS'de base_url'i kullanmaz (Host=testserver) → tam adres; yoksa Host kuralı reddeder.
        with c.websocket_connect("ws://127.0.0.1:8791" + yol) as ws:
            if kapanis_bekle:
                m = ws.receive()
                return m.get("code") if m.get("type") == "websocket.close" else m
            return "acik"
    except WebSocketDisconnect as e:
        return e.code


def _giris(c) -> str:
    """Kilit ekranının yaptığı: parola → token (tarayıcı ve Electron aynı ucu kullanır)."""
    r = c.post("/api/lock/unlock", json={"parola": PAROLA})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture
def gorus_acik(monkeypatch):
    monkeypatch.setattr(cfg, "GORUS", True, raising=False)


@pytest.mark.parametrize("yol", ["/ws/realtime", "/ws/screen", "/ws/native", "/ws/gorus"])
def test_kilitliyken_yerel_ws_tokensiz_REDDEDILIR(yol, gorus_acik):
    app_lock.parola_kur(PAROLA)
    c = _yerel()
    assert c.get("/api/ping").status_code == 401, "HTTP tarafı zaten token istiyor (kıyas)"
    # Kapanış yalnız kabul-edip-kapatan uçta beklenir (gorus); öbürleri el sıkışmada reddeder. Kapı kırılırsa
    # realtime/screen KABUL eder ve açık kalır → beklemek testi asardı, "acik" dönmesi yeterli kırmızı.
    bekle = yol == "/ws/gorus"
    assert _kod(c, yol, kapanis_bekle=bekle) == 4401
    assert _kod(c, yol + "?token=sahte", kapanis_bekle=bekle) == 4401


def test_kilitliyken_tarayici_kipi_girisle_realtime_acilir():
    app_lock.parola_kur(PAROLA)
    c = _yerel()
    token = _giris(c)
    assert c.get("/api/ping", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert _kod(c, f"/ws/realtime?token={token}") == "acik"


def test_kilitliyken_electron_kipi_cerez_ve_girisle_realtime_acilir(monkeypatch):
    monkeypatch.setenv("YUKI_OTURUM_ANAHTARI", ANAHTAR)
    app_lock.parola_kur(PAROLA)
    c = _yerel(cookies={CEREZ_ADI: ANAHTAR})
    token = _giris(c)
    assert _kod(c, f"/ws/realtime?token={token}") == "acik"
    assert _kod(c, "/ws/realtime") == 4401, "çerez tek başına kilidi açmaz (HTTP'de de açmıyor)"


def test_kilitliyken_gorus_tokenla_kilit_kapisini_gecer(gorus_acik):
    """Token'la kilit kapısı geçilir; sıradaki kapı (biyometrik rıza, 4409) devreye girer."""
    app_lock.parola_kur(PAROLA)
    c = _yerel()
    token = _giris(c)
    assert _kod(c, f"/ws/gorus?token={token}", kapanis_bekle=True) == 4409


def test_kilitliyken_native_tokenla_kilit_kapisini_gecer(monkeypatch):
    """Native özellik kapalıysa uç accept + 4503 döner — 4401 değil: kilit kapısı geçildi."""
    import app.api.websocket_native as wn
    monkeypatch.setattr(wn, "GEMINI_NATIVE_AUDIO", False)
    app_lock.parola_kur(PAROLA)
    c = _yerel()
    token = _giris(c)
    assert _kod(c, f"/ws/native?token={token}", kapanis_bekle=True) == 4503


def test_kilitsiz_kurulumda_yerel_ws_eskisi_gibi_tokensiz():
    assert _kod(_yerel(), "/ws/realtime") == "acik"

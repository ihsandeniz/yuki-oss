"""API yanlış-anahtar kilidi — `services/api_guard.py` + `main.py::auth_middleware`.

Kapının üç sözü:
  1. N farklı yanlış anahtardan sonra 429 — DOĞRU anahtar da reddedilir
  2. aynı (bayat) anahtarın tekrarı kilitlemez — parola değişince sahip kendi cihazından kilitlenmesin
  3. vekil arkasındaki istemciler birbirinden ayrılır, vekilsiz yerel bağlantı hiç kilitlenmez

Yanıt kodları: kapıdan geçen istek var olmayan yola gider → 404. 401 = kapı reddi, 429 = kilit.

    cd backend && venv/bin/python -m pytest tests/test_api_guard.py -q
"""

import pytest
from starlette.testclient import TestClient

import app.main as main
from app.services import api_guard

ANAHTAR = "dogru-anahtar-test-123"
YOL = "/api/__api_guard_yok__"   # kapıdan geçerse 404


def _esit(t):
    return t == ANAHTAR


@pytest.fixture
def istemci(monkeypatch):
    import app.config as config
    from app.services import ag_ayari, app_lock
    monkeypatch.setattr(main, "AUTH_TOKEN", ANAHTAR)
    monkeypatch.setattr(config, "AUTH_TOKEN", ANAHTAR)       # WS uçları anahtarı config'ten okur
    monkeypatch.setattr(config, "API_GUARD_MAX_WRONG", 5)
    monkeypatch.setattr(app_lock, "kurulu", lambda: False)   # makinedeki gerçek kilit testi etkilemesin
    # TestClient'ın kaynağı "testclient" — yerel değil; ağ kapısı burada ölçülen şey değil.
    monkeypatch.setattr(ag_ayari, "uzak_izin", lambda *a, **k: True)
    monkeypatch.setattr(ag_ayari, "ws_izinli", lambda *a, **k: True)
    api_guard.sifirla()
    with TestClient(main.app) as c:
        yield c
    api_guard.sifirla()


def _bearer(t):
    return {"Authorization": f"Bearer {t}"}


def test_dogru_anahtar_gecer(istemci):
    assert istemci.get(YOL, headers=_bearer(ANAHTAR)).status_code == 404
    assert istemci.get(YOL, params={"token": ANAHTAR}).status_code == 404


def test_farkli_yanlis_anahtarlar_kilitler_dogruyu_da(istemci):
    for i in range(4):
        assert istemci.get(YOL, headers=_bearer(f"tahmin-{i}")).status_code == 401
    r = istemci.get(YOL, headers=_bearer("tahmin-4"))
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
    # Kilitliyken doğru anahtar da, ?token= ile deneme de geçmez.
    assert istemci.get(YOL, headers=_bearer(ANAHTAR)).status_code == 429
    assert istemci.get(YOL, params={"token": ANAHTAR}).status_code == 429


def test_query_token_denemesi_de_sayilir(istemci):
    for i in range(5):
        istemci.get(YOL, params={"token": f"q-{i}"})
    assert istemci.get(YOL, headers=_bearer(ANAHTAR)).status_code == 429


def test_ayni_bayat_anahtar_kilitlemez(istemci):
    for _ in range(30):
        assert istemci.get(YOL, headers=_bearer("eski-anahtar")).status_code == 401
    assert istemci.get(YOL, headers=_bearer(ANAHTAR)).status_code == 404


def test_anahtarsiz_istek_sayilmaz(istemci):
    for _ in range(30):
        assert istemci.get(YOL).status_code == 401
    assert istemci.get(YOL, headers=_bearer(ANAHTAR)).status_code == 404


def test_basari_sayaci_sifirlar(istemci):
    for i in range(4):
        istemci.get(YOL, headers=_bearer(f"a-{i}"))
    assert istemci.get(YOL, headers=_bearer(ANAHTAR)).status_code == 404
    for i in range(4):
        assert istemci.get(YOL, headers=_bearer(f"b-{i}")).status_code == 401


def test_muaf_yollar_kilitte_acik(istemci):
    """Kilitli istemci arayüzü ve giriş ekranını yine görür (giriş kendi kilidine tabi)."""
    for i in range(5):
        istemci.get(YOL, headers=_bearer(f"t-{i}"))
    assert istemci.get("/health").status_code == 200
    assert istemci.get("/api/lock/status").status_code not in (401, 429)


def test_kilit_mesaji_iki_dilde_var():
    from app.mesajlar import en, tr
    for m in (tr, en):
        sozluk = next(v for v in vars(m).values() if isinstance(v, dict) and "cihaz.ag-kilitsiz-uzak" in v)
        assert sozluk.get("api.cok-yanlis-anahtar"), f"{m.__name__}: kilit mesajı yok"


# ── İstemci kimliği: vekil arkası ──────────────────────────────────────── #

class _Baglanti:
    def __init__(self, host, basliklar=None):
        self.client = type("C", (), {"host": host})()
        self.headers = {k.lower(): v for k, v in (basliklar or {}).items()}


def test_vekilsiz_yerel_kilitlenmez():
    api_guard.sifirla()
    b = _Baglanti("127.0.0.1")
    assert api_guard.istemci(b) is None
    for i in range(50):
        durum, _ = api_guard.dene(b, [f"x-{i}"], _esit)
    assert durum == api_guard.YANLIS
    assert api_guard.dene(b, [ANAHTAR], _esit)[0] == api_guard.OK


def test_vekil_arkasi_istemciler_ayrisir():
    """Ters vekil loopback'ten bağlanır; gerçek adres başlıktan."""
    import app.config as config
    api_guard.sifirla()
    saldirgan = _Baglanti("127.0.0.1", {"CF-Connecting-IP": "203.0.113.9"})
    telefon = _Baglanti("127.0.0.1", {"X-Forwarded-For": "100.64.0.7"})
    for i in range(config.API_GUARD_MAX_WRONG):
        api_guard.dene(saldirgan, [f"t-{i}"], _esit)
    assert api_guard.dene(saldirgan, [ANAHTAR], _esit)[0] == api_guard.KILITLI
    assert api_guard.dene(telefon, [ANAHTAR], _esit)[0] == api_guard.OK
    api_guard.sifirla()


def test_baslik_degeri_dondurmek_kilidi_atlatmaz():
    """Loopback'ten her istekte başka X-Forwarded-For / CF-Connecting-IP değeri yollamak
    yeni kova açmamalı; yoksa yanlış-anahtar sayacı hiç dolmaz."""
    import app.config as config
    for baslik in ("X-Forwarded-For", "CF-Connecting-IP", "Tailscale-User-Login"):
        api_guard.sifirla()
        for i in range(config.API_GUARD_MAX_WRONG):
            b = _Baglanti("127.0.0.1", {baslik: f"198.51.100.{i + 1}"})
            api_guard.dene(b, [f"t-{i}"], _esit)
        yeni = _Baglanti("127.0.0.1", {baslik: "203.0.113.250"})
        assert api_guard.dene(yeni, [ANAHTAR], _esit)[0] == api_guard.KILITLI, baslik
    api_guard.sifirla()


def test_lan_dan_uydurulan_baslik_kimligi_degistirmez():
    """Başlığa yalnız loopback bağlantıda bakılır."""
    b1 = _Baglanti("192.168.1.50", {"X-Forwarded-For": "1.1.1.1"})
    b2 = _Baglanti("192.168.1.50", {"X-Forwarded-For": "2.2.2.2"})
    assert api_guard.istemci(b1) == api_guard.istemci(b2) == "192.168.1.50"


def test_ws_yanlis_token_sayilir(istemci):
    """WS el sıkışması "http" middleware'den geçmez — uç içindeki kontrol saymalı."""
    from starlette.websockets import WebSocketDisconnect
    for i in range(5):
        with pytest.raises(WebSocketDisconnect):
            with istemci.websocket_connect(f"/ws/realtime?token=ws-{i}") as ws:
                ws.receive_text()
    assert api_guard.kalan("testclient") > 0

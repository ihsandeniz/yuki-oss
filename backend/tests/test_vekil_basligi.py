"""`X-Forwarded-For` ile yerel kapının atlatılması (denetim 2026-11-16, SEC-F001 + SEC-F002).

Kök: uvicorn'un varsayılanı `proxy_headers=True`, `forwarded_allow_ips="127.0.0.1"`. Loopback'ten gelen
istekte `scope["client"]`'ı `X-Forwarded-For` değeriyle YENİDEN YAZAR. `YerelKapi` "bu bilgisayardan mı"
kararını `scope["client"]`'tan verdiği için başlığı ekleyen istek "uzak" sayılıyor, Host (DNS rebinding) ve
oturum çerezi kuralı ikisi birden atlanıyordu. Aynı yol parola deneme sayacını da sıfırlıyordu (sayaç IP'ye bağlı).

Üç katman ölçülür:
1. `run.py` (paketli ürün + `start.sh`): gerçek uvicorn 0.35 sunucusu, gerçek soket → vekil başlığı yok sayılır.
2. `YerelKapi` (README'deki `python -m uvicorn` yolu run.py'den geçmez): uvicorn'un ProxyHeadersMiddleware'i
   önde olsa bile vekil başlığı taşıyan istek yerel kurallardan geçer.
3. Deneme sınırı: başlığı her istekte değiştirmek parola sayacını sıfırlamaz.
"""
from __future__ import annotations

import asyncio
import http.client
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.yerel_kapi import CEREZ_ADI, YerelKapi

ANAHTAR = "b" * 64


def _mini():
    m = FastAPI()

    @m.get("/api/gizli")
    async def gizli():
        return {"ok": True}

    m.add_middleware(YerelKapi, acik_yollar={"/health"}, izinli_kokenler=["http://127.0.0.1:8791"])
    return m


@pytest.fixture
def anahtarli(monkeypatch):
    monkeypatch.setenv("YUKI_OTURUM_ANAHTARI", ANAHTAR)


# ── 1) run.py: gerçek uvicorn sunucusu ──────────────────────────────────── #
class _Sunucu:
    """`run.py`'nin ayarlarıyla (host/port hariç) gerçek uvicorn sunucusu, rastgele portta."""

    def __init__(self, app_, **ek):
        import run
        ayar = {k: v for k, v in run.sunucu_ayarlari().items() if k not in ("host", "port")}
        ayar.update(ek)
        self.config = uvicorn.Config(app_, host="127.0.0.1", port=0, log_level="warning", lifespan="off", **ayar)
        self.sunucu = uvicorn.Server(self.config)
        self.sunucu.install_signal_handlers = lambda: None
        self.is_ = threading.Thread(target=lambda: asyncio.run(self.sunucu.serve()), daemon=True)

    def __enter__(self):
        self.is_.start()
        bitis = time.monotonic() + 10
        while not self.sunucu.started:
            assert time.monotonic() < bitis, "uvicorn 10 sn'de açılmadı"
            time.sleep(0.02)
        self.port = self.sunucu.servers[0].sockets[0].getsockname()[1]
        return self

    def __exit__(self, *_):
        self.sunucu.should_exit = True
        self.is_.join(timeout=10)

    def get(self, yol, basliklar):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            c.request("GET", yol, headers=basliklar)
            return c.getresponse().status
        finally:
            c.close()


def test_run_py_vekil_basligini_kapatir():
    import run
    assert run.sunucu_ayarlari()["proxy_headers"] is False


@pytest.mark.parametrize("basliklar,beklenen", [
    ({"Host": "evil.example:8791", "X-Forwarded-For": "203.0.113.5"}, 403),      # DNS rebinding
    ({"Host": "127.0.0.1:8791", "X-Forwarded-For": "203.0.113.5"}, 401),         # çerezsiz yerel süreç
    ({"Host": "127.0.0.1:8791", "X-Forwarded-For": "203.0.113.5",
      "Cookie": f"{CEREZ_ADI}={ANAHTAR}"}, 200),                                   # Electron hâlâ girer
])
def test_gercek_uvicorn_run_ayarlariyla_xff_kapiyi_atlatamaz(anahtarli, basliklar, beklenen):
    with _Sunucu(_mini()) as s:
        assert s.get("/api/gizli", basliklar) == beklenen


# ── 2) YerelKapi: uvicorn vekil katmanı önde olsa bile ─────────────────── #
def _vekilli(app_):
    """`python -m uvicorn app.main:app` = ProxyHeadersMiddleware(trusted 127.0.0.1) → uygulama."""
    return TestClient(ProxyHeadersMiddleware(app_, trusted_hosts="127.0.0.1"),
                      client=("127.0.0.1", 5555), base_url="http://127.0.0.1:8791")


def test_vekil_katmani_onde_rebinding_yine_403(anahtarli):
    c = _vekilli(_mini())
    r = c.get("/api/gizli", headers={"host": "evil.example:8791", "x-forwarded-for": "203.0.113.5",
                                     "cookie": f"{CEREZ_ADI}={ANAHTAR}"})
    assert r.status_code == 403


def test_vekil_katmani_onde_cerezsiz_yine_401(anahtarli):
    c = _vekilli(_mini())
    assert c.get("/api/gizli", headers={"x-forwarded-for": "203.0.113.5"}).status_code == 401
    assert c.get("/api/gizli", headers={"forwarded": "for=203.0.113.5"}).status_code == 401


def test_vekil_katmani_onde_electron_girer(anahtarli):
    c = _vekilli(_mini())
    r = c.get("/api/gizli", headers={"x-forwarded-for": "203.0.113.5", "cookie": f"{CEREZ_ADI}={ANAHTAR}"})
    assert r.status_code == 200


def test_agdan_gelen_baslıksiz_istek_degismedi():
    """Ağa açık kurulumda telefon LAN IP'siyle, vekil başlığı OLMADAN gelir — Host kuralına girmez."""
    c = TestClient(_mini(), client=("192.168.1.50", 5555), base_url="http://192.168.1.10:8791")
    assert c.get("/api/gizli").status_code == 200


# ── 3) Deneme sınırı başlık döndürerek sıfırlanmaz ─────────────────────── #
@pytest.fixture
def kilitli(tmp_path, monkeypatch):
    from app.limiter import limiter
    from app.services import app_lock, login_guard
    monkeypatch.setattr(app_lock, "KILIT_DOSYASI", tmp_path / "app_lock.json")
    monkeypatch.setattr(app_lock, "DATA_DIR", tmp_path)
    app_lock.tum_oturumlari_kapat()
    login_guard._sifirla()
    limiter.reset()
    app_lock.parola_kur("dogru-parola")
    yield
    app_lock.tum_oturumlari_kapat()
    login_guard._sifirla()
    limiter.reset()


def test_xff_dondurmek_parola_sayacini_sifirlamaz(kilitli):
    from app.config import LOGIN_MAX_FAILS
    from app.main import app
    c = _vekilli(app)
    kodlar = [c.post("/api/lock/unlock", json={"parola": "yanlis"},
                     headers={"x-forwarded-for": f"203.0.113.{i + 1}"}).status_code
              for i in range(LOGIN_MAX_FAILS)]
    assert kodlar[-1] == 429, f"başlık döndürülünce sayaç doldu mu? {kodlar}"
    # Kilitliyken doğru parola da (yeni sahte adresle) geçmemeli.
    r = c.post("/api/lock/unlock", json={"parola": "dogru-parola"}, headers={"x-forwarded-for": "198.51.100.7"})
    assert r.status_code == 429


def test_vekilsiz_yerel_kullanici_vekil_denemelerinden_kilitlenmez(kilitli):
    """Tünelden (vekil başlıklı) gelen yanlış denemeler bu bilgisayardaki sahibi dışarıda bırakmasın."""
    from app.config import LOGIN_MAX_FAILS
    from app.main import app
    c = TestClient(app, client=("127.0.0.1", 5555), base_url="http://127.0.0.1:8791")
    for i in range(LOGIN_MAX_FAILS):
        c.post("/api/lock/unlock", json={"parola": "yanlis"}, headers={"x-forwarded-for": f"203.0.113.{i + 1}"})
    r = c.post("/api/lock/unlock", json={"parola": "dogru-parola"})
    assert r.status_code == 200, r.text

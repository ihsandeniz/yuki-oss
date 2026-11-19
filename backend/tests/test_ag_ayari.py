"""Yuki'yi yerel ağa açma ayarı — GÜVENLİK KAPISI ölçümü (HQ › CİHAZLAR, 2026-10-01).

Asıl soru "ayar kaydoluyor mu" değil: **kilitsiz ağ açılabiliyor mu?** Dört kapı, her biri mutasyonla kırmızı görülür:
① `PUT /api/devices/ag` kilit yokken açmayı REDDEDER (409) — dosya yazılmaz.   ② Kapatmak her koşulda serbest.
③ Açılış kapısı (`config.py`): ayar açık + kilit yok → HOST 127.0.0.1, ayar kapanır, günlük düşer (gerçek süreçte).
④ Çalışırken kilit kalkarsa ağdan gelen istek 403; WebSocket'ler ağdan token'sız GİREMEZ (eskiden giriyordu).
Ayrıca: "yeşil yalnız gerçekten dinleniyorsa" — soket ölçümü (127.0.0.1'e bağlı süreç ≠ dinliyor).
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import config as cfg
from app import config_manager
from app.main import app
from app.services import ag_ayari, app_lock

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def izole(tmp_path, monkeypatch):
    """Gerçek config.user.json / app_lock.json'a DOKUNMA; ayar belleği testler arası sızmasın."""
    from app.limiter import limiter
    monkeypatch.setattr(config_manager, "CONFIG_USER_PATH", tmp_path / "config.user.json")
    monkeypatch.setattr(app_lock, "KILIT_DOSYASI", tmp_path / "app_lock.json")
    monkeypatch.setattr(app_lock, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "AG_ACIK", False)
    monkeypatch.setattr(cfg, "AG_ACIK_SUREC", False)
    monkeypatch.setattr(cfg, "AG_KILIT_DUSTU", False)
    monkeypatch.setattr(cfg, "HOST", "127.0.0.1")
    monkeypatch.setattr(cfg, "AUTH_TOKEN", "")
    monkeypatch.setattr("app.main.AUTH_TOKEN", "")
    app_lock.tum_oturumlari_kapat()
    limiter.reset()
    yield tmp_path
    app_lock.tum_oturumlari_kapat()
    limiter.reset()


def _kullanici():
    return json.loads(config_manager.CONFIG_USER_PATH.read_text(encoding="utf-8")) \
        if config_manager.CONFIG_USER_PATH.exists() else {}


def _kilit_kur() -> dict:
    app_lock.parola_kur("gizli-parola")
    return {"Authorization": "Bearer " + app_lock.oturum_ac()}


# ── ① açma kapısı ─────────────────────────────────────────────────────────────

def test_kilitsiz_acma_REDDEDILIR_409_ve_dosya_yazilmaz():
    c = TestClient(app)
    r = c.put("/api/devices/ag", json={"acik": True})
    assert r.status_code == 409, "uygulama kilidi yokken ağ açılabildi"
    assert "AG_ACIK" not in _kullanici(), "reddedilen istek yine de ayarı yazdı"
    assert cfg.AG_ACIK is False


def test_kilitliyken_acma_calisir_ayar_yazilir_HOST_degismez():
    basl = _kilit_kur()
    c = TestClient(app)
    r = c.put("/api/devices/ag", json={"acik": True}, headers=basl)
    assert r.status_code == 200, r.text
    assert _kullanici()["AG_ACIK"] is True
    assert cfg.HOST == "127.0.0.1", "HOST çalışırken değişmez — ayar yeniden başlatınca geçerli"
    ag = r.json()["ag"]
    assert ag["ag_ayari"] is True and ag["ag_durum"] == "acik-bekliyor" and ag["yeniden_baslat_gerek"] is True
    assert ag["dinleniyor"] is False and ag["kilit_kurulu"] is True


def test_genel_ayar_ucu_AG_ACIK_yazamaz_kapi_atlanmaz():
    """`POST /api/settings/AG_ACIK` açık olsaydı kilit şartı atlanırdı."""
    c = TestClient(app)
    r = c.post("/api/settings/AG_ACIK", json={"value": True})
    assert r.status_code == 400
    assert "AG_ACIK" not in _kullanici()
    assert c.delete("/api/settings/AG_ACIK").status_code == 400


def test_kapatma_kilitsiz_da_serbest():
    config_manager.set_value("AG_ACIK", True)
    cfg.AG_ACIK = True
    r = TestClient(app).put("/api/devices/ag", json={"acik": False})
    assert r.status_code == 200
    assert _kullanici()["AG_ACIK"] is False and cfg.AG_ACIK is False


def test_kapatma_ag_acikken_kapanis_bekliyor_der():
    """Süreç 0.0.0.0'da dinliyor (ayarla açılmıştı) → kapatınca soket yeniden başlayana dek açık: dürüst durum."""
    basl = _kilit_kur()
    cfg.HOST, cfg.AG_ACIK, cfg.AG_ACIK_SUREC = "0.0.0.0", True, True
    r = TestClient(app).put("/api/devices/ag", json={"acik": False}, headers=basl)
    assert r.status_code == 200
    assert r.json()["ag"]["ag_durum"] == "kapanis-bekliyor"
    assert r.json()["ag"]["yeniden_baslat_gerek"] is True


# ── ③ açılış kapısı — GERÇEK süreçte (config.py import anında) ───────────────

def _acilis(veri_dizini: Path, kilit: bool, ayar: bool) -> dict:
    (veri_dizini / "config.user.json").write_text(json.dumps({"AG_ACIK": ayar}), encoding="utf-8")
    if kilit:
        (veri_dizini / "app_lock.json").write_text(json.dumps({"hash": "x", "tuz": "y"}), encoding="utf-8")
    ortam = {k: v for k, v in os.environ.items() if k not in ("HOST", "AG_ACIK")}
    ortam.update(YUKI_DATA_DIR=str(veri_dizini), PYTHONPATH=str(BACKEND), PYTHONIOENCODING="utf-8")
    r = subprocess.run(
        [sys.executable, "-c",
         "import json, app.config as c; print('SONUC' + json.dumps({'host': c.HOST, 'ayar': c.AG_ACIK,"
         " 'surec': c.AG_ACIK_SUREC, 'dustu': c.AG_KILIT_DUSTU}))"],
        capture_output=True, text=True, cwd=str(BACKEND), env=ortam, timeout=60)
    assert r.returncode == 0, r.stderr
    satir = [s for s in r.stdout.splitlines() if s.startswith("SONUC")][-1]
    d = json.loads(satir[5:])
    d["kayit"] = json.loads((veri_dizini / "config.user.json").read_text(encoding="utf-8"))
    d["gunluk"] = r.stderr
    return d


def test_acilis_ayar_acik_kilit_VAR_ag_acilir(tmp_path):
    d = _acilis(tmp_path, kilit=True, ayar=True)
    assert d["host"] == "0.0.0.0" and d["surec"] is True and d["dustu"] is False


def test_acilis_ayar_acik_kilit_YOK_127_e_doner_ayar_kapanir_gunluge_yazar(tmp_path):
    d = _acilis(tmp_path, kilit=False, ayar=True)
    assert d["host"] == "127.0.0.1", "kilitsiz açılışta ağ açıldı"
    assert d["ayar"] is False and d["surec"] is False and d["dustu"] is True
    assert d["kayit"]["AG_ACIK"] is False, "ayar kapatılmadı: kilit yeniden kurulunca ağ kendiliğinden açılırdı"
    assert "app lock is gone" in d["gunluk"], "günlüğe yazılmadı"


def test_acilis_ayar_kapali_ag_kapali(tmp_path):
    d = _acilis(tmp_path, kilit=True, ayar=False)
    assert d["host"] == "127.0.0.1" and d["surec"] is False


# ── ④ çalışırken kilit kalkarsa + WebSocket ───────────────────────────────────

def test_kilit_kalkinca_ag_acik_surecte_UZAK_istek_403_yerel_gecer():
    cfg.HOST, cfg.AG_ACIK_SUREC = "0.0.0.0", True        # ayarla açılmış süreç, kilit YOK
    uzak = TestClient(app, client=("192.168.1.50", 5555))
    r = uzak.get("/api/lock/status")
    assert r.status_code == 403, "kilitsiz açık süreçte ağdan gelen istek geçti"
    yerel = TestClient(app, client=("127.0.0.1", 5555), base_url="http://127.0.0.1:8791")  # Host yerel olmalı (yerel_kapi)
    assert yerel.get("/api/lock/status").status_code == 200


def test_ortamdan_HOST_veren_gelistirici_etkilenmez():
    cfg.HOST = "0.0.0.0"                                   # AG_ACIK_SUREC False: ayar değil, ortam
    assert TestClient(app, client=("192.168.1.50", 5555)).get("/api/lock/status").status_code == 200


def _ws(host, token=""):
    return SimpleNamespace(client=SimpleNamespace(host=host), query_params={"token": token} if token else {})


def test_ws_izinli_matrisi():
    # kilit yok, ayar yok (dev) → eskisi gibi
    assert ag_ayari.ws_izinli(_ws("192.168.1.9")) is True
    # ayarla açık süreç, kilit YOK → ağdan red, yerel geçer
    cfg.AG_ACIK_SUREC = True
    assert ag_ayari.ws_izinli(_ws("192.168.1.9")) is False
    assert ag_ayari.ws_izinli(_ws("127.0.0.1")) is True
    assert ag_ayari.ws_izinli(_ws("::ffff:127.0.0.1")) is True
    # kilit kurulu → ağdan token şart
    app_lock.parola_kur("gizli-parola")
    assert ag_ayari.ws_izinli(_ws("192.168.1.9")) is False
    assert ag_ayari.ws_izinli(_ws("192.168.1.9", "sahte")) is False
    assert ag_ayari.ws_izinli(_ws("192.168.1.9", app_lock.oturum_ac())) is True
    # kilit kurulu → YEREL soket de token ister (HTTP ile aynı kural; denetim 11-16 API-F001)
    assert ag_ayari.ws_izinli(_ws("127.0.0.1")) is False
    assert ag_ayari.ws_izinli(_ws("127.0.0.1", "sahte")) is False
    assert ag_ayari.ws_izinli(_ws("127.0.0.1", app_lock.oturum_ac())) is True
    assert ag_ayari.ws_izinli(_ws(None)) is False, "istemci adresi bilinmiyorsa uzak sayılmalı"


@pytest.mark.parametrize("yol", ["/ws/realtime", "/ws/screen", "/ws/native"])
def test_ws_ag_den_tokensiz_KAPANIR_kilit_kuruluyken(yol):
    """🔴 Eskiden: AUTH_TOKEN boş → kapı yok → kilit kuruluyken bile ağdan ekran akışı açılabilirdi."""
    app_lock.parola_kur("gizli-parola")
    uzak = TestClient(app, client=("192.168.1.50", 5555))
    with pytest.raises(Exception) as e:
        with uzak.websocket_connect(yol):
            pass
    assert "4401" in repr(e.value) or "Unauthorized" in repr(e.value) or "WebSocketDisconnect" in repr(e.value)


# ── yeşil yalnız gerçekten dinleniyorsa ───────────────────────────────────────

def _lan_ip() -> str:
    from app.api.devices_api import _yerel_ip
    return _yerel_ip()


def _dinle(adres: str):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((adres, 0)); s.listen(4)
    return s, s.getsockname()[1]


def test_dinleniyor_SOKETTEN_olculur_127_ye_bagli_surec_dinliyor_degil():
    ip = _lan_ip()
    if ip.startswith("127."):
        pytest.skip("makinede yerel ağ adresi yok")
    cfg.HOST = "0.0.0.0"
    acik, port = _dinle("0.0.0.0")
    try:
        assert ag_ayari.dinleniyor(ip, port) is True
    finally:
        acik.close()
    yerel, port2 = _dinle("127.0.0.1")
    try:
        assert ag_ayari.dinleniyor(ip, port2) is False, "127.0.0.1'e bağlı soket ağda dinliyor sanıldı (yalan yeşil)"
    finally:
        yerel.close()


def test_durum_ozeti_hallleri(monkeypatch):
    monkeypatch.setattr(ag_ayari, "dinleniyor", lambda ip, port: True)
    def d(ayar, host, surec=True):
        cfg.AG_ACIK, cfg.HOST, cfg.AG_ACIK_SUREC = ayar, host, surec
        return ag_ayari.durum_ozeti("192.168.1.9", 8001)
    assert d(False, "127.0.0.1", False)["ag_durum"] == "kapali"
    assert d(True, "127.0.0.1", False)["ag_durum"] == "acik-bekliyor"        # ayar açık, süreç hâlâ loopback
    assert d(True, "0.0.0.0")["ag_durum"] == "acik-dinliyor"
    assert d(False, "0.0.0.0")["ag_durum"] == "kapanis-bekliyor"
    monkeypatch.setattr(ag_ayari, "dinleniyor", lambda ip, port: False)
    assert d(True, "0.0.0.0")["ag_durum"] == "acik-ulasilamiyor", "HOST açık ama soket cevap vermiyorken yeşil verildi"
    # geliştirici ortam HOST'u: ayar kapalı ama süreç ağda → "açık" görünür, 'kapanış bekliyor' DEĞİL
    monkeypatch.setattr(ag_ayari, "dinleniyor", lambda ip, port: True)
    o = d(False, "0.0.0.0", False)
    assert o["ortamdan"] is True and o["ag_durum"] == "acik-dinliyor"


def test_kilit_dustu_bayragi_gorulur_ve_yeniden_acinca_biter():
    cfg.AG_KILIT_DUSTU = True
    c = TestClient(app)
    assert c.get("/api/devices/ag").json()["kilit_dustu"] is True
    basl = _kilit_kur()
    assert c.put("/api/devices/ag", json={"acik": True}, headers=basl).json()["ag"]["kilit_dustu"] is False


def test_bekleyen_yeniden_baslatma_listesinde_etiketli():
    from app.api import settings_api
    basl = _kilit_kur()
    TestClient(app).put("/api/devices/ag", json={"acik": True}, headers=basl)
    etiketler = [b["label"] for b in settings_api.bekleyen_yeniden_baslatma()]
    assert "Yuki'yi yerel ağa aç" in etiketler, etiketler
    settings_api._BEKLEYEN.pop("AG_ACIK", None); settings_api._ACILIS_DEGERI.pop("AG_ACIK", None)


# ── /ws/agent ağ kapısı + hassas yol ──────────────────────────────────────────

def _eslesmis_token(izole):
    from app.services import cihaz_eslestirme as ce
    kod = ce.kod_uret()["kod"]
    t = ce.kod_dogrula(kod, "pc")
    assert t
    return t


def test_ws_agent_KILITSIZ_acik_surecte_uzaktan_eslesmis_cihaz_bile_reddedilir(monkeypatch, izole):
    """Cihaz token'ı geçerli olsa da: ağa-açma ayarıyla açık süreç + kilit YOK + loopback dışı → 4403."""
    from starlette.websockets import WebSocketDisconnect
    from app.services import cihaz_eslestirme as ce
    monkeypatch.setenv("YUKI_DATA_DIR", str(izole))
    token = _eslesmis_token(izole)
    cfg.AG_ACIK_SUREC = True
    uzak = TestClient(app, client=("192.168.1.50", 5555))
    with pytest.raises(WebSocketDisconnect) as e:
        with uzak.websocket_connect(f"/ws/agent?cihaz={token}"):
            pass
    assert e.value.code == 4403, "kilitsiz açık ağda eşleşmiş uzak ajan bağlandı"


def test_ws_agent_kilit_VARKEN_uzak_cihaz_tokeniyle_baglanir_ve_yerel_her_zaman(monkeypatch, izole):
    monkeypatch.setenv("YUKI_DATA_DIR", str(izole))
    token = _eslesmis_token(izole)
    cfg.AG_ACIK_SUREC = True
    app_lock.parola_kur("gizli-parola")           # kilit kurulu: uzaktaki ajanın kilit token'ı olmaz, cihaz token'ı yeter
    for istemci in ("192.168.1.50", "127.0.0.1"):
        with TestClient(app, client=(istemci, 5555), ).websocket_connect(f"ws://127.0.0.1:8791/ws/agent?cihaz={token}") as ws:
            ws.send_text(json.dumps({"type": "heartbeat"}))


def test_ws_agent_baglantisi_surerken_kilit_kalkarsa_kesilir(monkeypatch, izole):
    from starlette.websockets import WebSocketDisconnect
    monkeypatch.setenv("YUKI_DATA_DIR", str(izole))
    token = _eslesmis_token(izole)
    cfg.AG_ACIK_SUREC = True
    app_lock.parola_kur("gizli-parola")
    uzak = TestClient(app, client=("192.168.1.50", 5555))
    with uzak.websocket_connect(f"/ws/agent?cihaz={token}") as ws:
        ws.send_text(json.dumps({"type": "heartbeat"}))
        app_lock.parola_kaldir()
        ws.send_text(json.dumps({"type": "heartbeat"}))
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_text()
        assert e.value.code == 4403


def test_ws_agent_ortamdan_HOST_gelistirici_etkilenmez(monkeypatch, izole):
    monkeypatch.setenv("YUKI_DATA_DIR", str(izole))
    token = _eslesmis_token(izole)
    with TestClient(app, client=("192.168.1.50", 5555)).websocket_connect(f"/ws/agent?cihaz={token}") as ws:
        ws.send_text(json.dumps({"type": "heartbeat"}))


@pytest.mark.parametrize("ad", ["config.user.json", "config.user.json.backup", "app_lock.json", "login_guard_state.json", ".env"])
def test_arac_hassas_yol_ayar_ve_kilit_dosyalarina_YAZAMAZ(tmp_path, monkeypatch, ad):
    from app.services.tools import files
    from app.services.tools import _base
    monkeypatch.setattr(_base, "_SAFE_ROOTS", [tmp_path.resolve()])
    monkeypatch.setattr(files, "_is_safe_path", _base._is_safe_path)
    hedef = tmp_path / ad
    for fn in (files.write_file, files.append_file):
        sonuc = fn(str(hedef), '{"AG_ACIK": true}')
        assert "hassas yol" in sonuc, (fn.__name__, ad, sonuc)
    assert not hedef.exists()
    # sıradan dosya hâlâ yazılabilir
    assert "yazıldı" in files.write_file(str(tmp_path / "not.txt"), "x")

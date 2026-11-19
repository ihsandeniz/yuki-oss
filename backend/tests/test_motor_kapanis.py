"""Zarif kapanış ucu — `POST /api/motor/kapan` (2026-10-08).

Windows'ta motoru kibarca kapatmanın tek yolu bu uç (SIGTERM yok). Korunan sözleşme:
1. Uç uvicorn'un `should_exit` bayrağını kaldırır ve emniyet zamanlayıcısı kurar.
2. Kapı: bu bilgisayardan + oturum çerezi. Çerezsiz yerel istek 401 (müşterinin tarayıcısındaki
   bir site motoru kapatamasın). Ağdan gelen istek kilit kapısına takılır (muafiyet ağa uzamaz).
3. Kilitli kurulumda yerel + çerezli istek GEÇER — yoksa kilitli müşteride kapanış hep zorla olur.
4. Anahtarsız motorda (elle başlatılmış geliştirme) uç kapalıdır.
"""
from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

import app.main as ana
from app import motor_kapanis
from app.main import app
from app.yerel_kapi import CEREZ_ADI

ANAHTAR = "b" * 64
YEREL = ("127.0.0.1", 50000)
KOK = "http://127.0.0.1:8791"
YOL = "/api/motor/kapan"


class SahteSunucu:
    should_exit = False


@pytest.fixture
def sunucu(monkeypatch):
    s = SahteSunucu()
    monkeypatch.setattr(motor_kapanis, "_sunucu", s)
    # Emniyet zamanlayıcısı testte gerçekten süreci öldürmesin.
    monkeypatch.setattr(motor_kapanis, "ZORLA_SN", 3600.0)
    monkeypatch.setattr(motor_kapanis.iste, "__kwdefaults__", {"zorla_sn": 3600.0, "cik": lambda k: None})
    return s


@pytest.fixture
def anahtarli(monkeypatch):
    monkeypatch.setenv("YUKI_OTURUM_ANAHTARI", ANAHTAR)


def _istemci(client=YEREL, base=KOK, cerez=True):
    c = TestClient(app, client=client, base_url=base)
    if cerez:
        c.cookies.set(CEREZ_ADI, ANAHTAR)
    return c


# ── modül ──────────────────────────────────────────────────────────────── #
def test_sunucu_yoksa_false():
    eski = motor_kapanis._sunucu
    motor_kapanis._sunucu = None
    try:
        assert motor_kapanis.iste(cik=lambda k: None) is False
    finally:
        motor_kapanis._sunucu = eski


def test_iste_bayragi_kaldirir_ve_zorlar():
    s = SahteSunucu()
    eski = motor_kapanis._sunucu
    motor_kapanis._sunucu = s
    cikti = threading.Event()
    try:
        assert motor_kapanis.iste(zorla_sn=0.05, cik=lambda k: cikti.set()) is True
        assert s.should_exit is True
        assert cikti.wait(2), "zarif kapanış takılırsa emniyet zamanlayıcısı çıkmalı"
        # İkinci istek ikinci zamanlayıcı kurmaz, yine True
        assert motor_kapanis.iste(zorla_sn=0.05, cik=lambda k: pytest.fail("ikinci zamanlayıcı")) is True
    finally:
        motor_kapanis._sunucu = eski


# ── uç + kapı ──────────────────────────────────────────────────────────── #
def test_yerel_cerezli_202(sunucu, anahtarli):
    r = _istemci().post(YOL)
    assert r.status_code == 202, r.text
    assert sunucu.should_exit is True


def test_cerezsiz_yerel_401(sunucu, anahtarli):
    r = _istemci(cerez=False).post(YOL)
    assert r.status_code == 401
    assert sunucu.should_exit is False


def test_get_kapatmaz(sunucu, anahtarli):
    assert _istemci().get(YOL).status_code == 405
    assert sunucu.should_exit is False


def test_anahtarsiz_motorda_kapali(sunucu, monkeypatch):
    monkeypatch.delenv("YUKI_OTURUM_ANAHTARI", raising=False)
    assert _istemci(cerez=False).post(YOL).status_code == 403
    assert sunucu.should_exit is False


def test_reload_modunda_409(anahtarli, monkeypatch):
    monkeypatch.setattr(motor_kapanis, "_sunucu", None)
    assert _istemci().post(YOL).status_code == 409


def test_kilitli_kurulumda_yerel_cerezli_gecer(sunucu, anahtarli, monkeypatch):
    """🔑 Bu muafiyet silinirse kilitli müşteride Windows kapanışı hep zorla olur."""
    from app.services import app_lock
    monkeypatch.setattr(app_lock, "kurulu", lambda: True)
    r = _istemci().post(YOL)
    assert r.status_code == 202, r.text


def test_kilitli_kurulumda_agdan_istek_reddedilir(sunucu, anahtarli, monkeypatch):
    """🔴 Muafiyet ağa uzarsa telefon/LAN motoru kimliksiz kapatır."""
    from app.services import app_lock
    monkeypatch.setattr(app_lock, "kurulu", lambda: True)
    monkeypatch.setattr(ana, "_token_kabul", lambda t, k: False)
    r = _istemci(client=("192.168.1.50", 5555), base="http://192.168.1.10:8791", cerez=False).post(YOL)
    assert r.status_code in (401, 403), r.text
    assert sunucu.should_exit is False


def test_yabanci_koken_403(sunucu, anahtarli):
    r = _istemci().post(YOL, headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    assert sunucu.should_exit is False

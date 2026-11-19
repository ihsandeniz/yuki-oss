"""Harita vekilleri (v0.8.1, denetim C1 + H4) — saldırı vakaları.

C1: upstream `text/html` dönerse saldırganın sayfası Yuki'nin kökeninde çalışıyordu.
H4: SSRF kapısı yalnız ilk adreste; 302 ile 127.0.0.1'e yönlendirme gövdeyi döndürüyordu.
Ağ yok: httpx.MockTransport. Adresler IP yazılı → DNS çağrısı yok.
"""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import map as map_api
from app.main import app

DIS = "http://93.184.216.34"          # global adres
c = TestClient(app, base_url="http://127.0.0.1:8791")
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32


@pytest.fixture(autouse=True)
def pro():
    yield  # kademe yok — yetki her zaman açık


@pytest.fixture
def upstream(monkeypatch):
    """`yanitlar[url] = httpx.Response(...)`; istenen adresler `istenen`de birikir."""
    yanitlar: dict[str, httpx.Response] = {}
    istenen: list[str] = []

    def isle(req: httpx.Request) -> httpx.Response:
        istenen.append(str(req.url))
        return yanitlar.get(str(req.url), httpx.Response(404))

    gercek = httpx.AsyncClient

    def sahte(*a, **k):
        k["transport"] = httpx.MockTransport(isle)
        return gercek(*a, **k)

    monkeypatch.setattr(httpx, "AsyncClient", sahte)
    return yanitlar, istenen


@pytest.mark.parametrize("uc", ["/api/stream/proxy", "/api/cctv/img"])
def test_html_upstream_reddedilir_C1(upstream, uc):
    yanitlar, _ = upstream
    yanitlar[f"{DIS}/x"] = httpx.Response(200, headers={"content-type": "text/html"},
                                          content=b"<script>fetch('/api/settings')</script>")
    r = c.get(uc, params={"url": f"{DIS}/x"})
    assert r.status_code == 415
    assert b"<script>" not in r.content


@pytest.mark.parametrize("uc", ["/api/stream/proxy", "/api/cctv/img"])
def test_svg_reddedilir(upstream, uc):
    yanitlar, _ = upstream
    yanitlar[f"{DIS}/x.svg"] = httpx.Response(200, headers={"content-type": "image/svg+xml"},
                                              content=b"<svg onload=alert(1)>")
    assert c.get(uc, params={"url": f"{DIS}/x.svg"}).status_code == 415


@pytest.mark.parametrize("hedef", ["http://127.0.0.1:8791/api/settings", "http://192.168.1.1/",
                                   "http://169.254.169.254/latest/meta-data/", "http://[::ffff:127.0.0.1]:8791/"])
@pytest.mark.parametrize("uc", ["/api/stream/proxy", "/api/cctv/img"])
def test_yonlendirme_ile_yerel_aga_gidilmez_H4(upstream, uc, hedef):
    yanitlar, istenen = upstream
    yanitlar[f"{DIS}/r"] = httpx.Response(302, headers={"location": hedef})
    yanitlar[hedef] = httpx.Response(200, headers={"content-type": "image/jpeg"}, content=JPEG)
    r = c.get(uc, params={"url": f"{DIS}/r"})
    assert r.status_code == 400
    assert hedef not in istenen, "yerel adrese istek ATILMAMALI"


def test_mjpeg_gecer_ve_sandbox_tasir_ACAO_yok(upstream):
    yanitlar, _ = upstream
    yanitlar[f"{DIS}/cam"] = httpx.Response(
        200, headers={"content-type": "multipart/x-mixed-replace; boundary=f"}, content=b"--f\r\n" + JPEG)
    r = c.get("/api/stream/proxy", params={"url": f"{DIS}/cam"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("multipart/x-mixed-replace")
    assert "sandbox" in r.headers["content-security-policy"], "genel CSP vekilin sandbox'ını ezmemeli"
    assert "access-control-allow-origin" not in r.headers


def test_dis_yonlendirme_izlenir(upstream):
    yanitlar, _ = upstream
    yanitlar[f"{DIS}/a"] = httpx.Response(301, headers={"location": "/b.jpg"})
    yanitlar[f"{DIS}/b.jpg"] = httpx.Response(200, headers={"content-type": "image/jpeg"}, content=JPEG)
    r = c.get("/api/cctv/img", params={"url": f"{DIS}/a"})
    assert r.status_code == 200 and r.content == JPEG


def test_tur_basligi_yoksa_imzadan_taninir_html_taninmaz(upstream):
    yanitlar, _ = upstream
    yanitlar[f"{DIS}/j"] = httpx.Response(200, headers={"content-type": "application/octet-stream"}, content=JPEG)
    yanitlar[f"{DIS}/h"] = httpx.Response(200, headers={"content-type": "application/octet-stream"},
                                          content=b"<html><script>1</script>")
    r = c.get("/api/cctv/img", params={"url": f"{DIS}/j"})
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert c.get("/api/cctv/img", params={"url": f"{DIS}/h"}).status_code == 415


def test_yonlendirme_dongusu_kesilir(upstream):
    yanitlar, istenen = upstream
    yanitlar[f"{DIS}/d"] = httpx.Response(302, headers={"location": f"{DIS}/d"})
    assert c.get("/api/cctv/img", params={"url": f"{DIS}/d"}).status_code == 508
    assert len(istenen) <= map_api._VEKIL_YONLENDIRME + 1


def test_ozel_adres_ipv4_esli_ipv6():
    assert map_api._ozel_adres_mi("http://[::ffff:127.0.0.1]/")
    assert map_api._ozel_adres_mi("http://[::ffff:192.168.1.1]/")

"""Kamera görüşü ("Yuki bak") — bayrak, rıza, yerellik ve kare kapıları.

Router ana uygulamaya G4'te bağlanır (main.py ortak dosya); burada küçük bir FastAPI uygulamasına
takılıp ölçülür. Ağ isteği yok: yerel model `gorus_bak._istek` sahte yürütücüyle değiştirilir.

  · `GORUS` kapalıyken (varsayılan) her HTTP ucu 404, WS 4404 ile kapanır
  · açık ama rıza yok → kamera WS'i 4409, bakış 409; rıza eski sürümle verilemez
  · rıza / bakış yalnız bu bilgisayardan (loopback); uzaktan 403, WS 4403
  · rıza geri çekilince açık kamera bağlantısı kapanır
  · model adresi yerel değilse kare hiç istenmez, istek gitmez
  · yerel model yoksa açık hata cümlesi
  · kare yalnız bekleyen bakışa verilir, saklanmaz; JPEG olmayan kare düşer
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import gorus_api
from app.services import biyometrik_riza, gorus_bak, gorus_kare

JPEG = b"\xff\xd8" + b"\x00" * 64 + b"\xff\xd9"


@pytest.fixture(autouse=True)
def ortam(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GORUS", raising=False)
    # G4b: config.GORUS artık tanımlı (varsayılan False) ve ortamdan önce gelir → bu dosya ortamla sınar
    from app import config as _c
    monkeypatch.setattr(_c, "GORUS", None)
    monkeypatch.delenv("GORUS_MODEL_URL", raising=False)
    monkeypatch.delenv("GORUS_MODEL", raising=False)
    monkeypatch.setattr(gorus_api, "_auth_token", lambda: "")
    monkeypatch.setattr(gorus_kare, "yuz_say", lambda veri: (0, 1.0))   # sahte JPEG çözülmez
    gorus_bak._sifirla()
    yield
    gorus_bak._sifirla()


def _uygulama():
    app = FastAPI()
    app.include_router(gorus_api.router)
    return app


def _istemci(yerel=True):
    return TestClient(_uygulama(), base_url="http://127.0.0.1:8001",
                      client=("127.0.0.1" if yerel else "192.168.1.40", 50000))


def _ac(monkeypatch):
    monkeypatch.setenv("GORUS", "true")


def _riza():
    biyometrik_riza.ver("gorus", biyometrik_riza.SURUM["gorus"])


class SahteModel:
    def __init__(self, modeller=("qwen2.5vl:3b",), cevap="Masada bir kupa var.", kod=200, patla=False):
        self.modeller, self.cevap, self.kod, self.patla = modeller, cevap, kod, patla
        self.cagrilar: list[tuple[str, str, dict | None]] = []

    async def __call__(self, metot, url, govde, sure):
        self.cagrilar.append((metot, url, govde))
        if self.patla:
            raise OSError("bağlantı reddedildi")
        if url.endswith("/models"):
            return 200, {"data": [{"id": m} for m in self.modeller]}
        return self.kod, {"choices": [{"message": {"content": self.cevap}}]}


# ── bayrak ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("metot,yol", [("GET", "/api/gorus/durum"), ("POST", "/api/gorus/riza"),
                                       ("DELETE", "/api/gorus/riza"), ("POST", "/api/gorus/bak")])
def test_kapaliyken_her_uc_404(metot, yol):
    r = _istemci().request(metot, yol, json={})
    assert r.status_code == 404


def test_kapaliyken_ws_4404():
    with _istemci().websocket_connect("/ws/gorus") as ws:
        ws.send_bytes(JPEG)                  # kapı kırılırsa sunucu cevap verir, test asılmaz
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4404


@pytest.mark.parametrize("deger", ["", "0", "false", "hayir", "evet-degil"])
def test_bayrak_yalniz_acik_degerle(monkeypatch, deger):
    monkeypatch.setenv("GORUS", deger)
    assert gorus_api.bayrak_acik() is False


def test_config_bayragi_ortamdan_once(monkeypatch):
    from app import config
    monkeypatch.setenv("GORUS", "true")
    monkeypatch.setattr(config, "GORUS", False, raising=False)
    assert gorus_api.bayrak_acik() is False


# ── rıza ────────────────────────────────────────────────────────────────────
def test_acik_riza_yok_durum(monkeypatch):
    _ac(monkeypatch)
    monkeypatch.setattr(gorus_bak, "_istek", SahteModel())
    d = _istemci().get("/api/gorus/durum").json()
    assert d["acik"] is True and d["riza"]["verildi"] is False
    assert d["model"]["hazir"] is True


def test_riza_yokken_ws_4409(monkeypatch):
    _ac(monkeypatch)
    with _istemci().websocket_connect("/ws/gorus") as ws:
        ws.send_bytes(JPEG)                  # kapı kırılırsa sunucu cevap verir, test asılmaz
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4409
    assert e.value.reason == "riza yok"          # bağlanırken kapandı (kare kapısına kalmadı)


def test_riza_yokken_bak_409(monkeypatch):
    _ac(monkeypatch)
    r = _istemci().post("/api/gorus/bak", json={})
    assert r.status_code == 409


def test_riza_eski_surumle_400(monkeypatch):
    _ac(monkeypatch)
    r = _istemci().post("/api/gorus/riza", json={"kabul": True, "surum": 0})
    assert r.status_code == 400
    assert biyometrik_riza.var_mi("gorus") is False


def test_riza_kabul_false_400(monkeypatch):
    _ac(monkeypatch)
    r = _istemci().post("/api/gorus/riza", json={"kabul": False, "surum": biyometrik_riza.SURUM["gorus"]})
    assert r.status_code == 400
    assert biyometrik_riza.var_mi("gorus") is False


def test_riza_ver_ve_geri_cek(monkeypatch, tmp_path):
    _ac(monkeypatch)
    c = _istemci()
    r = c.post("/api/gorus/riza", json={"kabul": True, "surum": biyometrik_riza.SURUM["gorus"]})
    assert r.status_code == 200 and r.json()["riza"]["verildi"] is True
    yol = tmp_path / "biyometrik_riza.json"
    assert oct(yol.stat().st_mode & 0o777) == "0o600"
    assert set(json.loads(yol.read_text())["gorus"]) == {"surum", "verildi"}   # görüntü/ad yok
    assert c.delete("/api/gorus/riza").json()["riza"]["verildi"] is False
    assert biyometrik_riza.var_mi("gorus") is False


def test_riza_surumu_degisirse_gecersiz(monkeypatch):
    _riza()
    monkeypatch.setitem(biyometrik_riza.SURUM, "gorus", biyometrik_riza.SURUM["gorus"] + 1)
    assert biyometrik_riza.var_mi("gorus") is False


def test_bozuk_riza_dosyasi_riza_yok(tmp_path):
    (tmp_path / "biyometrik_riza.json").write_text("{bozuk")
    assert biyometrik_riza.var_mi("gorus") is False


# ── yalnız bu bilgisayar ────────────────────────────────────────────────────
def test_uzaktan_riza_403(monkeypatch):
    _ac(monkeypatch)
    r = _istemci(yerel=False).post("/api/gorus/riza", json={"kabul": True, "surum": 1})
    assert r.status_code == 403
    assert biyometrik_riza.var_mi("gorus") is False


def test_uzaktan_bak_403(monkeypatch):
    _ac(monkeypatch)
    _riza()
    assert _istemci(yerel=False).post("/api/gorus/bak", json={}).status_code == 403


def test_uzaktan_ws_4403(monkeypatch):
    _ac(monkeypatch)
    _riza()
    with _istemci(yerel=False).websocket_connect("/ws/gorus") as ws:
        ws.send_bytes(JPEG)                  # kapı kırılırsa sunucu cevap verir, test asılmaz
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4403


def test_token_yanlissa_ws_4401(monkeypatch):
    _ac(monkeypatch)
    _riza()
    monkeypatch.setattr(gorus_api, "_auth_token", lambda: "dogru-anahtar")
    with _istemci().websocket_connect("/ws/gorus?token=yanlis") as ws:
        ws.send_bytes(JPEG)
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4401


# ── kamera akışı ────────────────────────────────────────────────────────────
def test_ws_kare_alir_jpeg_olmayani_reddeder(monkeypatch):
    _ac(monkeypatch)
    _riza()
    with _istemci().websocket_connect("/ws/gorus") as ws:
        ws.send_bytes(JPEG)
        assert ws.receive_json()["tip"] == "durum"            # ilk kare işlenir
        ws.send_bytes(JPEG)
        assert ws.receive_json() == {"tip": "tamam"}           # aralık dolmadan gelen kare yalnız onaylanır
        ws.send_bytes(b"GIF89a....")
        assert ws.receive_json() == {"tip": "hata", "neden": "kare"}


def test_riza_geri_cekilince_ws_kapanir(monkeypatch):
    _ac(monkeypatch)
    _riza()
    c = _istemci()
    with c.websocket_connect("/ws/gorus") as ws:
        ws.send_bytes(JPEG)
        assert ws.receive_json()["tip"] == "durum"
        biyometrik_riza.geri_cek("gorus")
        ws.send_bytes(JPEG)
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4409


def test_kare_bekleyen_yokken_saklanmaz():
    gorus_bak.kare_geldi(JPEG)
    assert gorus_bak._bekleyenler == []


@pytest.mark.parametrize("veri,beklenen", [(JPEG, True), (b"", False), (b"\xff\xd8\x00\x00", False),
                                           (b"\x89PNG\r\n\x1a\n", False),
                                           (b"\xff\xd8" + b"\x00" * gorus_bak.MAX_BAYT + b"\xff\xd9", False)])
def test_kare_gecerli(veri, beklenen):
    assert gorus_bak.kare_gecerli(veri) is beklenen


# ── yerel model ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("url,yerel", [
    ("http://127.0.0.1:11434/v1", True), ("http://localhost:1234/v1", True), ("http://[::1]:8080/v1", True),
    ("http://127.5.5.5/v1", True), ("https://api.openai.com/v1", False), ("http://192.168.1.5:11434/v1", False),
    ("http://127.0.0.1.nip.io/v1", False), ("http://user:p@127.0.0.1/v1", False), ("file:///etc/passwd", False),
    ("http://0.0.0.0:11434/v1", False),
])
def test_yerel_adres_mi(url, yerel):
    assert gorus_bak.yerel_adres_mi(url) is yerel


def _bak_kos(soru="", kare=JPEG):
    async def _kos():
        gorus_bak.istemci_baglandi()
        gorev = asyncio.create_task(gorus_bak.bak(soru))
        for _ in range(50):
            await asyncio.sleep(0.01)
            if gorus_bak._bekleyenler:
                gorus_bak.kare_geldi(kare)
                break
        return await gorev
    return asyncio.run(_kos())


def test_bak_yerel_modelle(monkeypatch):
    sahte = SahteModel()
    monkeypatch.setattr(gorus_bak, "_istek", sahte)
    s = _bak_kos("ne var?")
    assert s == {"ok": True, "metin": "Masada bir kupa var."}
    metot, url, govde = sahte.cagrilar[-1]
    assert url == "http://127.0.0.1:11434/v1/chat/completions"
    assert govde == {}                          # gövde (base64 kare) gönderimden sonra temizlendi


def test_bulut_adresinde_kare_istenmez_istek_gitmez(monkeypatch):
    monkeypatch.setenv("GORUS_MODEL_URL", "https://api.example.com/v1")
    sahte = SahteModel()
    monkeypatch.setattr(gorus_bak, "_istek", sahte)
    s = _bak_kos()
    assert s["ok"] is False and "dışarı gönderilmez" in s["metin"]
    assert sahte.cagrilar == []
    assert gorus_bak._bekleyenler == []


def test_model_yoksa_acik_hata(monkeypatch):
    monkeypatch.setattr(gorus_bak, "_istek", SahteModel(patla=True))
    s = _bak_kos()
    assert s["ok"] is False and "yerel görsel model bulunamadı" in s["metin"] and "ollama pull" in s["metin"]


def test_model_durumu_model_yuklu_degil(monkeypatch):
    monkeypatch.setattr(gorus_bak, "_istek", SahteModel(modeller=("baska",)))
    d = asyncio.run(gorus_bak.model_durumu())
    assert d["hazir"] is False and "yüklü değil" in d["neden"]


def test_model_durumu_bulut_adresine_istek_atmaz(monkeypatch):
    monkeypatch.setenv("GORUS_MODEL_URL", "http://10.0.0.2:11434/v1")
    sahte = SahteModel()
    monkeypatch.setattr(gorus_bak, "_istek", sahte)
    assert asyncio.run(gorus_bak.model_durumu())["hazir"] is False
    assert sahte.cagrilar == []


def test_kamera_bagli_degilse_hata(monkeypatch):
    monkeypatch.setattr(gorus_bak, "_istek", SahteModel())
    s = asyncio.run(gorus_bak.bak())
    assert s["ok"] is False and "kamera açık değil" in s["metin"]


def test_iki_bakis_arasi_bekleme(monkeypatch):
    monkeypatch.setattr(gorus_bak, "_istek", SahteModel())
    assert _bak_kos()["ok"] is True
    s = _bak_kos()
    assert s["ok"] is False and "Az önce" in s["metin"]


def test_bak_ucu_rizali(monkeypatch):
    _ac(monkeypatch)
    _riza()
    monkeypatch.setattr(gorus_bak, "_istek", SahteModel())
    r = _istemci().post("/api/gorus/bak", json={"soru": "x"})
    assert r.status_code == 200 and r.json()["ok"] is False   # kamera bağlı değil → açık cümle
    assert "kamera açık değil" in r.json()["metin"]


# ── araç ────────────────────────────────────────────────────────────────────
def test_arac_kapali_ve_rizasizken_bakmaz(monkeypatch):
    from app.services.tools import gorus_tools
    monkeypatch.setattr(gorus_bak, "_istek", SahteModel())
    assert "kapalı" in asyncio.run(gorus_tools.kameraya_bak())
    _ac(monkeypatch)
    assert "rıza" in asyncio.run(gorus_tools.kameraya_bak())


# ── rıza metni sürümü ön yüzle aynı ─────────────────────────────────────────
def test_riza_metni_surumu_on_yuzle_ayni():
    import re
    from pathlib import Path
    js = (Path(__file__).resolve().parents[2] / "frontend/js/gorus-panel.js").read_text(encoding="utf-8")
    for ozellik in biyometrik_riza.OZELLIKLER:
        m = re.search(ozellik + r":\s*\{\s*surum:\s*(\d+)", js)
        assert m, f"{ozellik} rıza metni ön yüzde yok"
        assert int(m.group(1)) == biyometrik_riza.SURUM[ozellik], "rıza metni değiştiyse iki sürümü birlikte artır"


def test_riza_dosyasi_ilk_yazimda_600(monkeypatch, tmp_path):
    """Sonradan chmod'a güvenilmez: geçici dosya da 600 açılmalı (yazma ile chmod arası pencere)."""
    import os as _os
    monkeypatch.setattr(_os, "chmod", lambda *a, **k: None)
    _riza()
    assert oct((tmp_path / "biyometrik_riza.json").stat().st_mode & 0o777) == "0o600"


def test_bulut_adresinde_kare_hic_istenmez(monkeypatch):
    monkeypatch.setenv("GORUS_MODEL_URL", "https://api.example.com/v1")
    monkeypatch.setattr(gorus_bak, "_istek", SahteModel())

    async def _kos():
        gorus_bak.istemci_baglandi()
        gorev = asyncio.create_task(gorus_bak.bak())
        goruldu = False
        for _ in range(20):
            await asyncio.sleep(0.01)
            goruldu = goruldu or bool(gorus_bak._bekleyenler)
            if gorev.done():
                break
        if not gorev.done():
            gorus_bak.kare_geldi(JPEG)
        return goruldu, await gorev
    goruldu, s = asyncio.run(_kos())
    assert goruldu is False and s["ok"] is False

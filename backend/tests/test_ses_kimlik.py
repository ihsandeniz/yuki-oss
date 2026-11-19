"""Ses kimliği ("yalnız kayıtlı sesi dinle") — bayrak, rıza, kayıt, doğrulama, silme.

Gömme modeli (CAM++ ONNX) depoda yok, kullanıcı indirir; testler `ses_kimlik._gomme` yerine
sahte bir gömme koyar (sesin baskın frekansından türeyen vektör). Ağ yok, mikrofon yok.

  · `SES_KIMLIK` kapalıyken (varsayılan) her uç 404, `dogrula()` None (kapı geçirir, model yüklemez)
  · açık ama rıza yok → kayıt 409, `dogrula()` None
  · rıza / kayıt / deneme yalnız bu bilgisayardan (403)
  · model yoksa kayıt 409 + indirme yolu söylenir
  · kayıt yalnız gömme saklar (ses yok), dosya 600; az konuşma reddedilir
  · rıza geri çekilince ses izi de silinir
  · kayıtlı sese yakın ses kabul, uzak ses red; çok kısa ses red
"""
from __future__ import annotations

import io
import json
import math
import struct
import wave

import numpy as np
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api import ses_kimlik_api
from app.services import biyometrik_riza, ses_kimlik


def _wav(frekans: float, sn: float, hz: int = 16000, genlik: float = 0.4, kanal: int = 1) -> bytes:
    n = int(sn * hz)
    ornek = [int(genlik * 32767 * math.sin(2 * math.pi * frekans * i / hz)) for i in range(n)]
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as w:
        w.setnchannels(kanal)
        w.setsampwidth(2)
        w.setframerate(hz)
        w.writeframes(b"".join(struct.pack("<" + "h" * kanal, *([o] * kanal)) for o in ornek))
    return tampon.getvalue()


def _sahte_gomme(konusma: np.ndarray) -> np.ndarray:
    """Baskın frekansın çevresine tepe koyan 192-d vektör (aynı ses → aynı gömme)."""
    spek = np.abs(np.fft.rfft(konusma[:16000]))
    f = int(np.argmax(spek) * 16000 / (2 * (len(spek) - 1)))
    v = np.exp(-0.5 * ((np.arange(192) - f / 10) / 3.0) ** 2) + 1e-3
    return (v / np.linalg.norm(v)).astype(np.float32)


@pytest.fixture(autouse=True)
def ortam(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SES_KIMLIK", raising=False)
    # G4b: config.SES_KIMLIK artık tanımlı (varsayılan False) ve ortamdan önce gelir → bu dosya ortamla sınar
    from app import config as _c
    monkeypatch.setattr(_c, "SES_KIMLIK", None)
    model = tmp_path / "model.onnx"
    model.write_bytes(b"sahte")
    monkeypatch.setenv("SES_KIMLIK_MODEL", str(model))
    monkeypatch.setattr(ses_kimlik, "_gomme", _sahte_gomme)
    ses_kimlik._onbellek_temizle()
    yield
    ses_kimlik._onbellek_temizle()


def _istemci(yerel=True):
    app = FastAPI()
    app.include_router(ses_kimlik_api.router)
    return TestClient(app, base_url="http://127.0.0.1:8001",
                      client=("127.0.0.1" if yerel else "192.168.1.40", 50000))


def _ac(monkeypatch):
    monkeypatch.setenv("SES_KIMLIK", "true")


def _riza():
    biyometrik_riza.ver("ses_kimlik", biyometrik_riza.SURUM["ses_kimlik"])


def _klipler(frekans=220.0):
    return [("sesler", (f"k{i}.wav", _wav(frekans, 3.0), "audio/wav")) for i in range(3)]


# ── bayrak ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("metot,yol", [("GET", "/api/ses-kimlik/durum"), ("POST", "/api/ses-kimlik/riza"),
                                       ("DELETE", "/api/ses-kimlik/riza"), ("POST", "/api/ses-kimlik/kayit"),
                                       ("DELETE", "/api/ses-kimlik/kayit"), ("POST", "/api/ses-kimlik/dene")])
def test_kapaliyken_her_uc_404(metot, yol):
    assert _istemci().request(metot, yol).status_code == 404


def test_kapaliyken_dogrula_none_model_yuklemez(monkeypatch):
    _ac(monkeypatch)
    _riza()
    ses_kimlik.kaydet([_wav(220, 3.0)] * 3)      # ses izi ve model hazır: tek engel bayrak
    monkeypatch.delenv("SES_KIMLIK")
    cagri = []
    monkeypatch.setattr(ses_kimlik, "_gomme", lambda k: cagri.append(1))
    assert ses_kimlik.dogrula(_wav(220, 2)) is None
    assert ses_kimlik.kesme_izni(_wav(220, 2)) is True
    assert cagri == []


@pytest.mark.parametrize("deger", ["", "0", "false", "kapali"])
def test_bayrak_yalniz_acik_degerle(monkeypatch, deger):
    monkeypatch.setenv("SES_KIMLIK", deger)
    assert ses_kimlik.bayrak_acik() is False


# ── rıza ────────────────────────────────────────────────────────────────────
def test_rizasiz_kayit_409(monkeypatch):
    _ac(monkeypatch)
    cagri = []
    monkeypatch.setattr(ses_kimlik, "kaydet", lambda *a, **k: cagri.append(1))
    r = _istemci().post("/api/ses-kimlik/kayit", files=_klipler())
    assert r.status_code == 409
    assert cagri == []                           # rıza kapısı servisi hiç çağırtmadı
    assert not ses_kimlik.parmak_izi_yolu().exists()


def test_rizasiz_dogrula_none(monkeypatch):
    _ac(monkeypatch)
    _riza()
    ses_kimlik.kaydet([_wav(220, 3.0)] * 3)
    biyometrik_riza.geri_cek("ses_kimlik")     # dosya kalsa bile rıza yoksa kapı kullanılmaz
    assert ses_kimlik.dogrula(_wav(220, 2)) is None


def test_uzaktan_403(monkeypatch):
    _ac(monkeypatch)
    _riza()
    c = _istemci(yerel=False)
    assert c.post("/api/ses-kimlik/riza", json={"kabul": True, "surum": 1}).status_code == 403
    assert c.post("/api/ses-kimlik/kayit", files=_klipler()).status_code == 403
    assert c.post("/api/ses-kimlik/dene", files=[("ses", ("a.wav", _wav(220, 2), "audio/wav"))]).status_code == 403


def test_riza_eski_surum_400(monkeypatch):
    _ac(monkeypatch)
    assert _istemci().post("/api/ses-kimlik/riza", json={"kabul": True, "surum": 0}).status_code == 400
    assert biyometrik_riza.var_mi("ses_kimlik") is False


def test_riza_geri_cekilince_ses_izi_silinir(monkeypatch):
    _ac(monkeypatch)
    c = _istemci()
    assert c.post("/api/ses-kimlik/riza", json={"kabul": True, "surum": 1}).status_code == 200
    assert c.post("/api/ses-kimlik/kayit", files=_klipler()).status_code == 200
    assert ses_kimlik.parmak_izi_yolu().exists()
    d = c.delete("/api/ses-kimlik/riza").json()
    assert d["riza"]["verildi"] is False and d["kayit"]["var"] is False
    assert not ses_kimlik.parmak_izi_yolu().exists()


# ── kayıt ───────────────────────────────────────────────────────────────────
def test_model_yoksa_kayit_409_indirme_yolu(monkeypatch, tmp_path):
    _ac(monkeypatch)
    _riza()
    monkeypatch.setenv("SES_KIMLIK_MODEL", str(tmp_path / "yok.onnx"))
    r = _istemci().post("/api/ses-kimlik/kayit", files=_klipler())
    assert r.status_code == 409
    assert "huggingface.co" in r.json()["detail"]
    d = _istemci().get("/api/ses-kimlik/durum").json()
    assert d["model"]["var"] is False and d["model"]["indir"].startswith("https://")


def test_kayit_yalniz_gomme_saklar(monkeypatch):
    _ac(monkeypatch)
    _riza()
    r = _istemci().post("/api/ses-kimlik/kayit", files=_klipler())
    assert r.status_code == 200, r.text
    yol = ses_kimlik.parmak_izi_yolu()
    assert oct(yol.stat().st_mode & 0o777) == "0o600"
    veri = json.loads(yol.read_text())
    assert set(veri) == {"model", "klip", "konusma_sn", "tarih", "gomme"}
    assert len(veri["gomme"]) == 192
    assert list(yol.parent.glob("*.wav")) == []


def test_az_konusma_reddedilir(monkeypatch):
    _ac(monkeypatch)
    _riza()
    r = _istemci().post("/api/ses-kimlik/kayit", files=[("sesler", ("a.wav", _wav(220, 2.0), "audio/wav"))])
    assert r.status_code == 400 and "az" in r.json()["detail"]
    assert not ses_kimlik.parmak_izi_yolu().exists()


def test_sessizlik_konusma_sayilmaz(monkeypatch):
    _ac(monkeypatch)
    _riza()
    sessiz = _wav(220, 3.0, genlik=0.0)
    with pytest.raises(ValueError):
        ses_kimlik.kaydet([sessiz] * 4)


def test_cok_fazla_ya_da_buyuk_klip_reddedilir(monkeypatch):
    _ac(monkeypatch)
    _riza()
    c = _istemci()
    fazla = [("sesler", (f"k{i}.wav", _wav(220, 1.0), "audio/wav")) for i in range(ses_kimlik_api.EN_COK_KLIP + 1)]
    assert c.post("/api/ses-kimlik/kayit", files=fazla).status_code == 413
    buyuk = [("sesler", ("b.wav", b"RIFF" + b"\x00" * (ses_kimlik_api.EN_COK_BAYT + 1), "audio/wav"))]
    assert c.post("/api/ses-kimlik/kayit", files=buyuk).status_code == 413


def test_kayit_silinir(monkeypatch):
    _ac(monkeypatch)
    _riza()
    c = _istemci()
    c.post("/api/ses-kimlik/kayit", files=_klipler())
    assert c.delete("/api/ses-kimlik/kayit").json()["kayit"]["var"] is False
    assert ses_kimlik.dogrula(_wav(220, 2)) is None


# ── doğrulama ───────────────────────────────────────────────────────────────
def test_kayitli_ses_kabul_baska_ses_red(monkeypatch):
    _ac(monkeypatch)
    _riza()
    ses_kimlik.kaydet([_wav(220, 3.0)] * 3)
    ayni = ses_kimlik.dogrula(_wav(220, 2.0))
    baska = ses_kimlik.dogrula(_wav(900, 2.0))
    assert ayni is not None and ayni.kabul() is True
    assert baska is not None and baska.kabul() is False
    assert ses_kimlik.kesme_izni(_wav(900, 1.5)) is False
    assert ses_kimlik.kesme_izni(_wav(220, 1.5)) is True


def test_cok_kisa_ses_red(monkeypatch):
    _ac(monkeypatch)
    _riza()
    ses_kimlik.kaydet([_wav(220, 3.0)] * 3)
    s = ses_kimlik.dogrula(_wav(220, 0.1))
    assert s is not None and s.skor is None and s.kabul() is False


def test_dene_ucu(monkeypatch):
    _ac(monkeypatch)
    _riza()
    c = _istemci()
    assert c.post("/api/ses-kimlik/dene", files=[("ses", ("a.wav", _wav(220, 2), "audio/wav"))]).status_code == 409
    c.post("/api/ses-kimlik/kayit", files=_klipler())
    d = c.post("/api/ses-kimlik/dene", files=[("ses", ("a.wav", _wav(220, 2), "audio/wav"))]).json()
    assert d["kabul"] is True and d["skor"] > d["esik"]


def test_onay_esigi_daha_siki(monkeypatch):
    s = ses_kimlik.Sonuc(skor=0.52, sure_sn=2.0)
    assert s.kabul() is True and s.kabul(onay=True) is False


def test_bozuk_ses_izi_kapi_gecirir(monkeypatch):
    _ac(monkeypatch)
    _riza()
    ses_kimlik.parmak_izi_yolu().write_text("{bozuk")
    assert ses_kimlik.dogrula(_wav(900, 2)) is None


def test_baska_model_izi_kullanilmaz(monkeypatch):
    _ac(monkeypatch)
    _riza()
    ses_kimlik.kaydet([_wav(220, 3.0)] * 3)
    yol = ses_kimlik.parmak_izi_yolu()
    veri = json.loads(yol.read_text())
    veri["model"] = "baska.onnx"
    yol.write_text(json.dumps(veri))
    ses_kimlik._onbellek_temizle()
    assert ses_kimlik.dogrula(_wav(900, 2)) is None


# ── ses işleme ──────────────────────────────────────────────────────────────
def test_fbank_boyut_ve_sonlu():
    x = ses_kimlik.pcm_oku(_wav(440, 1.0))
    f = ses_kimlik.fbank(x)
    assert f.shape == (98, 80) and np.isfinite(f).all()
    assert abs(float(f.mean(0).mean())) < 1e-4      # zaman ortalaması çıkarıldı


def test_pcm_stereo_ve_44k_donusur():
    x = ses_kimlik.pcm_oku(_wav(440, 1.0, hz=44100, kanal=2))
    assert abs(len(x) - 16000) <= 2 and x.dtype == np.float32 and np.abs(x).max() <= 1.0


def test_bozuk_ses_hatasi():
    with pytest.raises(ValueError):
        ses_kimlik.pcm_oku(b"bu ses degil")


def test_kaydet_dogrudan_cagrida_da_riza_ister(monkeypatch):
    _ac(monkeypatch)
    with pytest.raises(ses_kimlik.RizaYok):
        ses_kimlik.kaydet([_wav(220, 3.0)] * 3)
    assert not ses_kimlik.parmak_izi_yolu().exists()

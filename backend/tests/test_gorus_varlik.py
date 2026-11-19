"""Kamera görüşü — varlık ("geldin / gittin"), selam ve mola cümleleri.

  · durum makinesi: tek yanlış algılama "geldi" yapmaz; kısa kayıp "gitti" yapmaz (histerezis)
  · tanıma yalnız gelişte ve dakikada en çok 1; selam yalnız tanınan adla, 5 dk'dan uzun
    ayrılıştan sonra ve süreç genelinde 30 dk'da en çok 1 (yeniden bağlanmak sıfırlamaz)
  · mola 50 dk kesintisiz oturuşta, sonra en erken 50 dk sonra
  · seslendirici: `GORUS_SES=0` susturur, ad yoksa susar, kendi tavanı var
  · kare yalnız bellekte çözülür (diske dosya açılmaz); bozuk/büyük kare hata
  · WS akışı: işlenen karede durum + söylenecek cümle döner
"""
from __future__ import annotations

import builtins
import os

import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api import gorus_api
from app.services import biyometrik_riza, gorus_bak, gorus_kare, gorus_ses, gorus_varlik
from app.services.gorus_varlik import (DONUS_MIN_SN, GEL_KARE, MOLA_SN, SELAM_ARALIK_SN, TANIMA_ARALIK_SN,
                                       YOK_SN, SelamDefteri, VarlikIzleyici)


def _iz():
    return VarlikIzleyici(defter=SelamDefteri())


def _gel(iz, t0=0.0):
    olaylar = []
    for i in range(GEL_KARE):
        olaylar += iz.kare(1, t0 + i)
    return olaylar, t0 + GEL_KARE - 1


# ── durum makinesi ──────────────────────────────────────────────────────────
def test_tek_yanlis_algilama_geldi_yapmaz():
    iz = _iz()
    assert iz.kare(1, 0) == [] and iz.kare(0, 1) == [] and iz.kare(1, 2) == []
    assert iz.durum == "yok"


def test_gelis_tanima_ister_ve_buradaya_gecer():
    iz = _iz()
    olaylar, t = _gel(iz)
    assert olaylar == ["geldi", "tanima_iste"] and iz.durum == "geldi"
    iz.kare(1, t + 1)
    assert iz.durum == "burada"


def test_kisa_kayip_gitti_yapmaz_uzun_kayip_yapar():
    iz = _iz()
    _, t = _gel(iz)
    assert iz.kare(0, t + YOK_SN - 1) == [] and iz.durum == "burada"
    assert iz.kare(0, t + YOK_SN + 1) == ["gitti"]
    iz.kare(0, t + YOK_SN + 2)
    assert iz.durum == "yok"


def test_tanima_dakikada_bir():
    iz = _iz()
    _, t = _gel(iz)
    iz.kare(0, t + YOK_SN + 1)
    iz.kare(0, t + YOK_SN + 2)
    olaylar, _ = _gel(iz, t + YOK_SN + 3)
    assert "geldi" in olaylar and "tanima_iste" not in olaylar      # 60 sn dolmadı
    iz2 = _iz()
    _, t = _gel(iz2)
    iz2.kare(0, t + YOK_SN + 1)
    iz2.kare(0, t + YOK_SN + 2)
    olaylar, _ = _gel(iz2, t + TANIMA_ARALIK_SN + YOK_SN)
    assert "tanima_iste" in olaylar


def test_selam_yalniz_adla():
    iz = _iz()
    _, t = _gel(iz)
    assert iz.tanima_sonucu(None, t) == []
    iz = _iz()
    _, t = _gel(iz)
    assert iz.tanima_sonucu("Deniz", t) == ["selam"]


def test_selam_bekleyen_tanima_yoksa_yok():
    iz = _iz()
    assert iz.tanima_sonucu("Deniz", 0) == []


def test_kisa_ayrilistan_sonra_selam_yok():
    defter = SelamDefteri()
    iz = VarlikIzleyici(defter=defter)
    _, t = _gel(iz)
    iz.tanima_sonucu("Deniz", t)
    iz.kare(0, t + YOK_SN + 1)                        # gitti (son yüz t'de)
    iz.kare(0, t + YOK_SN + 2)
    t2 = t + TANIMA_ARALIK_SN + YOK_SN
    defter.sifirla()
    _gel(iz, t2)
    assert t2 - t < DONUS_MIN_SN
    assert iz.tanima_sonucu("Deniz", t2 + GEL_KARE) == []


def test_selam_tavani_surec_genelinde():
    defter = SelamDefteri()
    a = VarlikIzleyici(defter=defter)
    _, t = _gel(a)
    assert a.tanima_sonucu("Deniz", t) == ["selam"]
    b = VarlikIzleyici(defter=defter)                 # yeniden bağlanan istemci
    _, t2 = _gel(b, t + 10)
    assert b.tanima_sonucu("Deniz", t2) == []
    c = VarlikIzleyici(defter=defter)
    _, t3 = _gel(c, t + SELAM_ARALIK_SN + 1)
    assert c.tanima_sonucu("Deniz", t3) == ["selam"]


def test_mola_elli_dakikada():
    iz = _iz()
    _, t = _gel(iz)
    bas = t - GEL_KARE + 1
    iz.kare(1, t + 1)
    assert iz.kare(1, bas + MOLA_SN - 1) == []
    assert iz.kare(1, bas + MOLA_SN) == ["mola"]
    assert iz.kare(1, bas + MOLA_SN + 10) == []
    assert iz.kare(1, bas + 2 * MOLA_SN) == ["mola"]


# ── seslendirici ────────────────────────────────────────────────────────────
@pytest.fixture
def ses_ortam(monkeypatch):
    monkeypatch.delenv("GORUS_SES", raising=False)


def test_selam_cumlesi_adla(ses_ortam):
    s = gorus_ses.GorusSeslendirici(saat=lambda: 0.0)
    assert s.cumle({"olay": "selam", "ad": "Deniz"}) == "Tekrar hoş geldin Deniz."
    assert s.cumle({"olay": "selam"}) is None
    assert s.sayac["adsiz"] == 1


def test_mola_cumlesi_ve_tavan(ses_ortam):
    saat = [0.0]
    s = gorus_ses.GorusSeslendirici(saat=lambda: saat[0])
    assert "mola" in s.cumle({"olay": "mola"})
    saat[0] = MOLA_SN - 1
    assert s.cumle({"olay": "mola"}) is None and s.sayac["tavan"] == 1
    saat[0] = MOLA_SN + 1
    assert s.cumle({"olay": "mola"}) is not None


def test_gorus_ses_kapali_susar(monkeypatch):
    monkeypatch.setenv("GORUS_SES", "0")
    s = gorus_ses.GorusSeslendirici(saat=lambda: 0.0)
    assert s.cumle({"olay": "mola"}) is None and s.sayac["kapali"] == 1


def test_bilinmeyen_olay_susar(ses_ortam):
    assert gorus_ses.GorusSeslendirici().cumle({"olay": "geldi"}) is None


def test_ad_temizlenir(ses_ortam):
    s = gorus_ses.GorusSeslendirici(saat=lambda: 0.0)
    assert s.cumle({"olay": "selam", "ad": "<b>Ali</b>\n" + "x" * 80}) == "Tekrar hoş geldin bAlib " + "x" * 34 + "."


# ── kare ────────────────────────────────────────────────────────────────────
def _jpeg(g=320, y=240):
    ok, b = cv2.imencode(".jpg", np.full((y, g, 3), 128, np.uint8))
    assert ok
    return b.tobytes()


def test_kare_bellekte_cozulur_diske_yazilmaz(monkeypatch):
    acilan = []
    gercek_open, gercek_osopen = builtins.open, os.open

    def izle_open(f, mode="r", *a, **k):
        if any(c in mode for c in "wax+"):
            acilan.append(f)
        return gercek_open(f, mode, *a, **k)

    def izle_osopen(f, flags, *a, **k):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            acilan.append(f)
        return gercek_osopen(f, flags, *a, **k)

    gorus_kare._dedektor()                    # sınıflandırıcı önceden yüklü (okuma)
    monkeypatch.setattr(builtins, "open", izle_open)
    monkeypatch.setattr(os, "open", izle_osopen)
    yuz, ms = gorus_kare.yuz_say(_jpeg())
    assert yuz == 0 and ms >= 0 and acilan == []



def test_cascade_yoksa_kare_hatasi_doner(monkeypatch):
    """OpenCV 5.0'da `cv2.CascadeClassifier` yok. AttributeError WS döngüsünü
    düşürüyordu (`_kare_isle` yalnız KareHatasi yakalar); artık KareHatasi olmalı."""
    import types
    sahte = types.SimpleNamespace(data=types.SimpleNamespace(haarcascades=""))
    monkeypatch.setattr(gorus_kare, "_cv2", lambda: sahte)
    monkeypatch.setattr(gorus_kare, "_haar", None)
    with pytest.raises(gorus_kare.KareHatasi, match="yuz-dedektoru-yok"):
        gorus_kare._dedektor()


def test_opencv_4x_sabit_ve_iki_paket_ayni_surum():
    """Kurulan cv2 yüz sayabilmeli; kaynak kilit OpenCV'yi 4.x'te, rapidocr'ın çektiği
    opencv-python'u da headless ile AYNI sürümde tutmalı (yoksa 5.0 gelip cv2/'yi ezer)."""
    import re
    from pathlib import Path
    assert hasattr(cv2, "CascadeClassifier"), f"cv2 {cv2.__version__}: CascadeClassifier yok"
    req = (Path(__file__).resolve().parents[1] / "requirements-product.txt").read_text(encoding="utf-8")
    surum = dict(re.findall(r"^(opencv-python(?:-headless)?)==(\S+)", req, re.M))
    assert set(surum) == {"opencv-python", "opencv-python-headless"}, surum
    assert surum["opencv-python"] == surum["opencv-python-headless"], surum
    assert surum["opencv-python-headless"].startswith("4."), surum


def test_buyuk_kare_kucultulur():
    k = gorus_kare.kare_coz(_jpeg(1280, 720))
    assert max(k.shape[:2]) == gorus_kare.HEDEF_KENAR


@pytest.mark.parametrize("veri", [b"", b"\xff\xd8bozuk\xff\xd9", b"x" * (gorus_bak.MAX_BAYT + 1)])
def test_bozuk_kare_hata(veri):
    with pytest.raises(gorus_kare.KareHatasi):
        gorus_kare.kare_coz(veri)


def test_kocaman_cozunurluk_reddedilir():
    ok, b = cv2.imencode(".jpg", np.zeros((10, gorus_kare.MAX_KENAR + 10, 3), np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 10])
    with pytest.raises(gorus_kare.KareHatasi):
        gorus_kare.kare_coz(b.tobytes())


def test_tanima_hata_verirse_ad_yok(monkeypatch):
    import asyncio

    from app.services import face_multi_auth

    async def patla(_):
        raise RuntimeError("model yok")
    monkeypatch.setattr(face_multi_auth, "recognize_face", patla)
    assert asyncio.run(gorus_kare.tani(b"x")) is None


# ── WS akışı ────────────────────────────────────────────────────────────────
def test_ws_islenen_karede_durum_ve_selam(monkeypatch, tmp_path):
    monkeypatch.setenv("YUKI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GORUS", "true")
    from app import config as _c
    monkeypatch.setattr(_c, "GORUS", None)   # G4b: config önce gelir, bu test ortamla sınar
    monkeypatch.delenv("GORUS_SES", raising=False)
    monkeypatch.setattr(gorus_api, "_auth_token", lambda: "")
    monkeypatch.setattr(gorus_api, "MIN_ARALIK_SN", 0.0)
    monkeypatch.setattr(gorus_varlik, "defter", SelamDefteri())
    monkeypatch.setattr(gorus_api, "_seslendirici", gorus_ses.GorusSeslendirici())
    monkeypatch.setattr(gorus_kare, "yuz_say", lambda veri: (1, 3.0))

    async def tani(_):
        return "Deniz"
    monkeypatch.setattr(gorus_kare, "tani", tani)
    gorus_bak._sifirla()
    biyometrik_riza.ver("gorus", biyometrik_riza.SURUM["gorus"])
    app = FastAPI()
    app.include_router(gorus_api.router)
    c = TestClient(app, base_url="http://127.0.0.1:8001", client=("127.0.0.1", 50000))
    cevaplar = []
    with c.websocket_connect("/ws/gorus") as ws:
        for _ in range(GEL_KARE):
            ws.send_bytes(_jpeg())
            cevaplar.append(ws.receive_json())
    assert cevaplar[0]["tip"] == "durum" and cevaplar[0]["yuz"] == 1
    son = cevaplar[-1]
    assert son["durum"] == "geldi" and son["soyle"] == "Tekrar hoş geldin Deniz."
    assert "tanima_iste" not in son["olaylar"]

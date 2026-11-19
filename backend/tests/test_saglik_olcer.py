"""Sağlık ölçeri — skor sözleşmesi, kayıt ucu, ekran yapısı.

Asıl soru "uç çalışıyor mu" değil: *sensör KÖR mü?* Yeşil bir panel, ölçtüğü şey
bozulunca kırmızıya dönmüyorsa bilgi taşımaz. Korunan karar: ⚪ ölçülemedi ≠ ❌ kötü.
"""
import json
import os
import time

import pytest
from starlette.testclient import TestClient

from app.main import app
from app.services import saglik_olcer as so
from tests.yardim import FRONTEND, sozluk

c = TestClient(app)


def _s(durum):
    x = so.Sensor("x")
    return {"iyi": x.iyi, "uyari": x.uyari, "kotu": x.kotu}[durum]() if durum != "olculemedi" else x.yok("n")


@pytest.fixture()
def dizin(tmp_path, monkeypatch):
    monkeypatch.setattr(so, "KAYIT_DIZINI", tmp_path / "saglik")
    return tmp_path / "saglik"


# ── Skor sözleşmesi ─────────────────────────────────────────────────────────

def test_olculemeyen_sensor_skoru_dusurmez():
    skor, olculen, toplam = so.skorla([_s("iyi"), _s("iyi"), _s("olculemedi")])
    assert (skor, olculen, toplam) == (100, 2, 3)


def test_kotu_sensor_skoru_dusurur():
    assert so.skorla([_s("iyi"), _s("kotu")])[0] == 50
    assert so.skorla([_s("iyi"), _s("uyari")])[0] == 80


def test_hicbiri_olculemezse_skor_yok():
    skor, olculen, _ = so.skorla([_s("olculemedi")])
    assert skor is None and olculen == 0


def test_cokmus_sensor_olculemedi_olur_kotu_degil(monkeypatch):
    def patla():
        raise RuntimeError("x")
    patla.__name__ = "s_patla"
    monkeypatch.setattr(so, "SENSORLER", [patla])
    (s,) = so.olc()
    assert s.durum == "olculemedi" and s.neden == "cokmus"


# ── Sensörler kör değil ─────────────────────────────────────────────────────

def test_disk_sensoru_dolu_diski_gorur(monkeypatch):
    K = type("K", (), {})
    for bos, beklenen in ((50, "iyi"), (10, "uyari"), (2, "kotu")):
        k = K()
        k.total, k.free = 100, bos
        monkeypatch.setattr(so.shutil, "disk_usage", lambda p, k=k: k)
        assert so.s_disk().durum == beklenen


def test_disk_okunamazsa_olculemedi(monkeypatch):
    def hata(p):
        raise OSError
    monkeypatch.setattr(so.shutil, "disk_usage", hata)
    assert so.s_disk().durum == "olculemedi"


def test_yedek_kurulmamis_ariza_degil(monkeypatch):
    from app.services import yedekleme
    monkeypatch.setattr(yedekleme, "ayarlar", lambda: {"son_tur": None})
    assert so.s_yedek().durum == "olculemedi"


def test_yedek_hatali_tur_kotu_bayat_uyari(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app.services import yedekleme
    eski = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
    monkeypatch.setattr(yedekleme, "ayarlar", lambda: {"son_tur": {"hata": "x", "basladi": eski}})
    assert so.s_yedek().durum == "kotu"
    monkeypatch.setattr(yedekleme, "ayarlar",
                        lambda: {"son_tur": {"hata": None, "basladi": eski}, "zamanlama": "03:30"})
    assert so.s_yedek().durum == "uyari"
    monkeypatch.setattr(yedekleme, "ayarlar",
                        lambda: {"son_tur": {"hata": None, "basladi": eski}, "zamanlama": None})
    assert so.s_yedek().durum == "iyi"      # yalnız elle yedekleyen için yaş arıza değil


def test_hata_gunlugu_esikleri(monkeypatch):
    from app.services import error_log
    for adet, beklenen in ((0, "iyi"), (3, "uyari"), (50, "kotu")):
        monkeypatch.setattr(error_log, "ozet", lambda a=adet: {"son_24s": a})
        assert so.s_hata_gunlugu().durum == beklenen


# ── Uç ──────────────────────────────────────────────────────────────────────

def test_kayit_yoksa_404_degil_kayit_yok(dizin):
    r = c.get("/api/saglik")
    assert r.status_code == 200 and r.json() == {"durum": "kayit-yok"}


def test_olc_kaydeder_ve_get_okur(dizin):
    r = c.post("/api/saglik/olc")
    assert r.status_code == 200
    d = r.json()
    assert d["durum"] == "iyi" and d["bayat"] is False and d["yas_saat"] < 1
    assert len(d["sensorler"]) == len(so.SENSORLER)
    assert len(list(dizin.glob("*.json"))) == 1
    assert c.get("/api/saglik").json()["skor"] == d["skor"]


def test_bozuk_kayit_yalanci_skor_vermez(dizin):
    dizin.mkdir(parents=True)
    (dizin / "2026-01-01.json").write_text("{yarim", encoding="utf-8")
    d = c.get("/api/saglik").json()
    assert d["durum"] == "kayit-bozuk" and "skor" not in d


def test_eski_kayit_bayat_isaretlenir(dizin):
    dizin.mkdir(parents=True)
    f = dizin / "2026-01-01.json"
    f.write_text(json.dumps({"skor": 100, "kapsam": "5/5", "sensorler": []}), encoding="utf-8")
    eski = time.time() - 40 * 3600
    os.utime(f, (eski, eski))
    d = c.get("/api/saglik").json()
    assert d["bayat"] is True and d["yas_saat"] >= 39


def test_eski_kayitlar_budanir(dizin):
    dizin.mkdir(parents=True)
    for i in range(40):
        (dizin / f"2025-01-{i:02d}.json").write_text("{}", encoding="utf-8")
    so.olc_ve_kaydet(dizin)
    assert len(list(dizin.glob("*.json"))) == so.SAKLANAN_KAYIT


# ── Ekran ───────────────────────────────────────────────────────────────────

def test_ekran_yapisi_ve_sozluk():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert 'id="mon-saglik-katli"' in html and 'id="mon-saglik-olc"' in html
    js = (FRONTEND / "js" / "intro-sequences.js").read_text(encoding="utf-8")
    assert "/api/saglik/olc" in js and "monitorSaglikYukle" in js
    tr, en = sozluk("tr"), sozluk("en")
    gerekli = {f"mon.saglik.s.{s.__name__[2:]}" for s in so.SENSORLER}
    assert gerekli <= set(tr) and gerekli <= set(en)
    assert {k for k in tr if k.startswith("mon.saglik")} == {k for k in en if k.startswith("mon.saglik")}

"""Galeri "+ KÖK KLASÖR EKLE" — `/kok` + `/gozat` güvenlik kapısı.

Kapılar (galeri_api._ekleme_kapisi + _yerel_istek):
  K1 yalnız bu bilgisayar (loopback)      K2 izinli üst dizin (ev / takılı disk / YUKI_GALERI_IZINLI)
  K3 sistem dizini reddi                   K4 gizli parça reddi (izinli köke göre)
  K5 sembolik bağ çözülüp yeniden denetim  K6 yol gezinmesi (..) çözülür, dışarı çıkamaz
  K7 galerinin veri klasörü reddi          K8 ortam değişkeni sabitse 409
  K9 seçici gizli ve sembolik bağlı klasörü listelemez

    cd backend && python -m pytest -q tests/test_galeri_kok_ekle.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import galeri_api as g

YEREL = ("127.0.0.1", 50000)


@pytest.fixture()
def ev(tmp_path, monkeypatch):
    ev = (tmp_path / "ev").resolve()
    (ev / "Resimler" / "tatil").mkdir(parents=True)
    (ev / "Resimler" / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (ev / "Fotolar").mkdir()
    (ev / ".ssh").mkdir()
    (ev / ".gizli" / "ic").mkdir(parents=True)
    disari = (tmp_path / "disari").resolve()
    disari.mkdir()
    (ev / "kacis").symlink_to(disari, target_is_directory=True)
    (ev / "gizli-bag").symlink_to(ev / ".ssh", target_is_directory=True)
    monkeypatch.setenv("HOME", str(ev))
    monkeypatch.setenv("USER", "yok-boyle-kullanici-xq")      # takılı disk yok
    monkeypatch.delenv("YUKI_GALERI_KOKLER", raising=False)
    monkeypatch.delenv("YUKI_GALERI_IZINLI", raising=False)
    monkeypatch.setattr(g, "VERI", tmp_path / "veri")
    monkeypatch.setattr(g, "ONBELLEK", tmp_path / "veri" / "onbellek")
    monkeypatch.setattr(g, "AYAR_YOLU", tmp_path / "veri" / "galeri-ayar.json")
    monkeypatch.setattr(g, "_TUM_ONBELLEK", (0.0, (), []))
    g._KAYIT.clear()
    app = FastAPI()
    app.include_router(g.router)
    return {"ev": ev, "disari": disari, "tmp": tmp_path,
            "c": TestClient(app, client=YEREL),
            "uzak": TestClient(app, client=("192.168.1.40", 50000))}


def _kokler(o):
    if not g.AYAR_YOLU.exists():
        return []
    return json.loads(g.AYAR_YOLU.read_text("utf-8"))["kokler"]


def test_ev_altindaki_klasor_eklenir_ve_cikarilir(ev):
    c = ev["c"]
    # varsayılan kök (~/Resimler) zaten listede → "zaten var", ayar yazılmaz
    assert c.post("/api/galeri/kok", json={"yol": str(ev["ev"] / "Resimler")}).json()["zaten_var"] is True
    r = c.post("/api/galeri/kok", json={"yol": str(ev["ev"] / "Fotolar")})
    assert r.status_code == 200, r.text
    assert _kokler(ev) == [str(ev["ev"] / "Resimler"), str(ev["ev"] / "Fotolar")]
    kid = r.json()["id"]
    assert kid in [k["id"] for k in c.get("/api/galeri/kokler").json()["kokler"]]
    assert c.delete(f"/api/galeri/kok/{kid}").status_code == 200
    assert _kokler(ev) == [str(ev["ev"] / "Resimler")]
    assert (ev["ev"] / "Resimler" / "a.png").exists()          # dosyaya dokunulmadı


def test_k1_uzak_istemci_reddedilir(ev):
    u = ev["uzak"]
    assert u.post("/api/galeri/kok", json={"yol": str(ev["ev"] / "Resimler")}).status_code == 403
    assert u.get("/api/galeri/gozat").status_code == 403
    assert u.delete("/api/galeri/kok/0123456789abcdef").status_code == 403
    assert _kokler(ev) == []


@pytest.mark.parametrize("ad", ["disari_mutlak", "etc", "goreli"])
def test_k2_izinli_ust_dizin_disi_reddedilir(ev, ad):
    yol = {"disari_mutlak": str(ev["disari"]), "etc": "/usr/share", "goreli": "Resimler"}[ad]
    r = ev["c"].post("/api/galeri/kok", json={"yol": yol})
    assert r.status_code in (400, 403), r.text
    assert _kokler(ev) == []


@pytest.mark.parametrize("yol", ["/", "/etc", "/usr", "/var", "/tmp", "/home", "/root"])
def test_k3_sistem_dizini_reddedilir(ev, monkeypatch, yol):
    # izinli köke "/" yazılsa bile sistem dizinleri kabul edilmez
    monkeypatch.setenv("YUKI_GALERI_IZINLI", "/")
    r = ev["c"].post("/api/galeri/kok", json={"yol": yol})
    assert r.status_code == 403, (yol, r.text)
    assert ev["c"].get("/api/galeri/gozat", params={"yol": yol}).status_code == 403


@pytest.mark.parametrize("parca", [".ssh", ".gizli/ic"])
def test_k4_gizli_klasor_reddedilir(ev, parca):
    r = ev["c"].post("/api/galeri/kok", json={"yol": str(ev["ev"] / parca)})
    assert r.status_code == 403 and "Gizli" in r.json()["detail"]
    assert ev["c"].get("/api/galeri/gozat", params={"yol": str(ev["ev"] / parca)}).status_code == 403


@pytest.mark.parametrize("bag", ["kacis", "gizli-bag"])
def test_k5_sembolik_bag_kacisi_reddedilir(ev, bag):
    r = ev["c"].post("/api/galeri/kok", json={"yol": str(ev["ev"] / bag)})
    assert r.status_code == 403, r.text
    assert ev["c"].get("/api/galeri/gozat", params={"yol": str(ev["ev"] / bag)}).status_code == 403
    assert _kokler(ev) == []


def test_k6_yol_gezinmesi_disari_cikamaz(ev):
    kotu = str(ev["ev"] / "Resimler" / ".." / ".." / "disari")
    assert ev["c"].post("/api/galeri/kok", json={"yol": kotu}).status_code == 403
    assert ev["c"].get("/api/galeri/gozat", params={"yol": kotu}).status_code == 403
    for bozuk in ["", "   ", "/ev/\x00x", "x" * 5000]:
        assert ev["c"].post("/api/galeri/kok", json={"yol": bozuk}).status_code == 400


def test_k7_veri_klasoru_eklenemez(ev, monkeypatch):
    veri = ev["ev"] / "yuki-veri"
    veri.mkdir()
    monkeypatch.setattr(g, "VERI", veri)
    r = ev["c"].post("/api/galeri/kok", json={"yol": str(veri)})
    assert r.status_code == 403


def test_k8_ortam_degiskeni_sabitse_409(ev, monkeypatch):
    monkeypatch.setenv("YUKI_GALERI_KOKLER", str(ev["ev"] / "Resimler"))
    assert ev["c"].post("/api/galeri/kok", json={"yol": str(ev["ev"] / "Resimler" / "tatil")}).status_code == 409
    assert ev["c"].delete("/api/galeri/kok/0123456789abcdef").status_code == 409


def test_k9_gozat_gizli_ve_bagli_klasoru_listelemez(ev):
    d = ev["c"].get("/api/galeri/gozat").json()
    adlar = {k["ad"] for k in d["klasorler"]}
    assert d["yol"] == str(ev["ev"])
    assert "Resimler" in adlar
    assert not adlar & {".ssh", ".gizli", "kacis", "gizli-bag"}
    assert d["ust"] is None                     # ev dizininin üstüne çıkılmaz
    alt = ev["c"].get("/api/galeri/gozat", params={"yol": str(ev["ev"] / "Resimler")}).json()
    assert alt["ust"] == str(ev["ev"]) and alt["medya"] == 1


def test_izinli_kok_ortam_degiskeniyle_acilir(ev, monkeypatch):
    disari = ev["disari"]
    (disari / "Fotolar").mkdir()
    assert ev["c"].post("/api/galeri/kok", json={"yol": str(disari / "Fotolar")}).status_code == 403
    monkeypatch.setenv("YUKI_GALERI_IZINLI", str(disari))
    assert ev["c"].post("/api/galeri/kok", json={"yol": str(disari / "Fotolar")}).status_code == 200
    d = ev["c"].get("/api/galeri/gozat").json()
    assert {"ad": disari.name, "yol": str(disari)} in d["diskler"]


def test_sil_bilinmeyen_ve_bozuk_kimlik(ev):
    assert ev["c"].delete("/api/galeri/kok/zzzz").status_code == 400
    assert ev["c"].delete("/api/galeri/kok/0123456789abcdef").status_code == 404


# ── Katmanlar birbirini maskelemesin: her kapı TEK BAŞINA (mutasyon 11-15) ───

def test_k3_tek_basina_ev_sistem_dizininin_kendisi_eklenemez(ev, monkeypatch):
    """Ev /root ise ev izinli kök sayılır ama /root'un KENDİSİ sistem dizinidir → yalnız K3 tutar."""
    if not Path("/root").is_dir():
        pytest.skip("/root yok")
    monkeypatch.setenv("HOME", "/root")
    r = ev["c"].post("/api/galeri/kok", json={"yol": "/root"})
    assert r.status_code == 403 and "Sistem" in r.json()["detail"]


def test_k3b_tek_basina_izinli_kok_olarak_sistem_dizini_suzulur(ev, monkeypatch):
    """YUKI_GALERI_IZINLI=/ yazılsa bile sistem altındaki alt klasör (/usr/share) eklenemez."""
    monkeypatch.setenv("YUKI_GALERI_IZINLI", "/")
    assert Path("/") not in g._ekleme_kokleri()
    assert ev["c"].post("/api/galeri/kok", json={"yol": "/usr/share"}).status_code == 403
    assert ev["c"].get("/api/galeri/gozat", params={"yol": "/usr/share"}).status_code == 403


def test_k6_tek_basina_uzun_mutlak_yol_400(ev):
    uzun = str(ev["ev"]) + "/" + "a" * 4200
    assert ev["c"].post("/api/galeri/kok", json={"yol": uzun}).status_code == 400

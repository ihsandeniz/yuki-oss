"""Galeri (salt okunur gezgin) — kök ayardan gelir, dizin dışına çıkılamaz, yazma ucu yok.

    cd backend && python -m pytest -q tests/test_galeri.py
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import galeri_api as g


def _png() -> bytes:
    def parca(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + parca(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + parca(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + parca(b"IEND", b""))


@pytest.fixture()
def ortam(tmp_path, monkeypatch):
    kok = (tmp_path / "Galerim").resolve()
    (kok / "alt").mkdir(parents=True)
    (kok / "a.png").write_bytes(_png())
    (kok / "alt" / "b.png").write_bytes(_png())
    (kok / ".gizli").mkdir()
    (kok / ".gizli" / "g.png").write_bytes(_png())
    (kok / "not.txt").write_text("medya degil")
    disari = (tmp_path / "Disari").resolve()
    disari.mkdir()
    (disari / "sir.png").write_bytes(_png())
    monkeypatch.setattr(g, "VERI", tmp_path / "veri")
    monkeypatch.setattr(g, "ONBELLEK", tmp_path / "veri" / "onbellek")
    monkeypatch.setattr(g, "AYAR_YOLU", tmp_path / "veri" / "galeri-ayar.json")
    monkeypatch.setenv("YUKI_GALERI_KOKLER", str(kok))
    monkeypatch.setattr(g, "_TUM_ONBELLEK", (0.0, (), []))
    g._KAYIT.clear()
    app = FastAPI()
    app.include_router(g.router)
    return TestClient(app), kok, disari


def test_kok_ortamdan_gelir_ve_liste(ortam):
    c, kok, _ = ortam
    r = c.get("/api/galeri/kokler").json()
    assert [k["yol"] for k in r["kokler"]] == [str(kok)]
    assert r["kokler"][0]["sayi"] == 2          # gizli klasör ve .txt sayılmaz
    kid = r["kokler"][0]["id"]
    lst = c.get("/api/galeri/liste", params={"id": kid})
    assert lst.status_code == 200 and lst.json()["ok"] is True
    assert all("yol" not in d for d in lst.json()["dosyalar"])   # dosya kaydı ham yol taşımaz


def test_kok_ayar_dosyasindan(ortam, monkeypatch):
    c, kok, _ = ortam
    monkeypatch.delenv("YUKI_GALERI_KOKLER")
    g.VERI.mkdir(parents=True, exist_ok=True)
    g.AYAR_YOLU.write_text('{"kokler": ["%s"]}' % (kok / "alt"), "utf-8")
    r = c.get("/api/galeri/kokler").json()
    assert [k["yol"] for k in r["kokler"]] == [str(kok / "alt")]


@pytest.mark.parametrize("kotu", ["../../etc/passwd", "../Disari/sir.png", "/etc/passwd",
                                  "0000000000000000", "%2e%2e%2fetc"])
def test_traversal_ve_bozuk_kimlik_reddedilir(ortam, kotu):
    c, _, _ = ortam
    c.get("/api/galeri/kokler")
    for uc in ("dosya", "kucuk", "bilet", "bilgi", "exif"):
        r = c.get(f"/api/galeri/{uc}/{kotu}")
        assert r.status_code in (400, 403, 404, 405, 422), (uc, kotu, r.status_code)
        assert b"root:" not in r.content


def test_kok_disi_kimlik_reddedilir(ortam):
    c, _, disari = ortam
    c.get("/api/galeri/kokler")
    kid = g._kimlik(disari / "sir.png")           # sunucu bu yolu bir kez görmüş olsa bile
    assert c.get(f"/api/galeri/dosya/{kid}").status_code in (403, 404)
    assert c.get(f"/api/galeri/kucuk/{kid}").status_code in (403, 404)
    assert c.get("/api/galeri/liste", params={"id": g._kimlik(disari)}).status_code in (403, 404)


def test_symlink_kok_disina_cikamaz(ortam):
    c, kok, disari = ortam
    (kok / "link.png").symlink_to(disari / "sir.png")
    c.get("/api/galeri/kokler")
    kid = g._kimlik(kok / "link.png")
    assert c.get(f"/api/galeri/dosya/{kid}").status_code in (403, 404)


def test_uzanti_ve_imza(ortam):
    c, kok, _ = ortam
    (kok / "sahte.png").write_bytes(b"bu png degil")
    c.get("/api/galeri/kokler")
    assert c.get(f"/api/galeri/dosya/{g._kimlik(kok / 'sahte.png')}").status_code in (403, 404, 415)
    assert c.get(f"/api/galeri/dosya/{g._kimlik(kok / 'not.txt')}").status_code in (403, 404, 415)


def test_dosya_range_ve_bilet(ortam):
    c, kok, _ = ortam
    c.get("/api/galeri/kokler")
    kid = g._kimlik(kok / "a.png")
    tam = c.get(f"/api/galeri/dosya/{kid}")
    assert tam.status_code == 200 and tam.content == _png()
    parca = c.get(f"/api/galeri/dosya/{kid}", headers={"Range": "bytes=0-7"})
    assert parca.status_code == 206 and parca.content == _png()[:8]
    b = c.get(f"/api/galeri/bilet/{kid}").json()
    kod = b.get("bilet") or b.get("kod")
    assert kod and c.get(f"/api/galeri/akis/{kod}").status_code in (200, 206)
    assert c.get("/api/galeri/akis/uydurma-bilet").status_code in (401, 403, 404, 410)


def test_yazma_uclari_yok(ortam):
    c, kok, _ = ortam
    c.get("/api/galeri/kokler")
    kid = g._kimlik(kok / "a.png")
    # Kök LİSTESİ yazılabilir (karar 11-15, test_galeri_kok_ekle.py); dosya yazan uç yok.
    for yontem, yol in [("post", "/api/galeri/duzen/sil"), ("post", "/api/galeri/duzen/cop"),
                        ("post", "/api/galeri/duzen/tasi"), ("post", "/api/galeri/duzen/ad"),
                        ("delete", f"/api/galeri/dosya/{kid}"),
                        ("post", "/api/galeri/onbellek/temizle")]:
        assert getattr(c, yontem)(yol).status_code in (404, 405), (yontem, yol)
    assert (kok / "a.png").exists()
    yazanlar = {r.path for r in g.router.routes if {"POST", "PUT", "PATCH", "DELETE"} & set(r.methods or ())}
    assert yazanlar == {"/api/galeri/kok", "/api/galeri/kok/{kid}"}


def test_veri_dizini_ve_gizli_taranmaz(ortam):
    _, kok, _ = ortam
    assert g._atla_mi(g.VERI / "onbellek" / "x.webp")
    assert g._atla_mi(kok / ".gizli")


def test_kisisel_yol_gomulu_degil():
    kaynak = Path(g.__file__).read_text("utf-8")
    assert "/home/" not in kaynak and ("ih" + "san") not in kaynak.lower()


# ── Ön yüz: kabuk bağı + salt okunur yüzey ─────────────────────────────── #
_FE = Path(__file__).resolve().parents[2] / "frontend"


def test_kabuk_galeri_sekmesi_bagli():
    html = (_FE / "index.html").read_text("utf-8")
    assert 'id="tab-btn-galeri"' in html and "switchTab('galeri')" in html
    assert 'id="tab-galeri"' in html and 'id="galeri-iframe"' in html
    nav = (_FE / "js" / "tab-nav.js").read_text("utf-8")
    assert "tab-galeri" in nav and "/ui/galeri.html" in nav
    for dil in ("tr", "en"):
        sozluk = (_FE / "js" / "diller" / f"{dil}.js").read_text("utf-8")
        assert "'nav.galeri'" in sozluk and "'nav.7-galeri'" in sozluk


def test_galeri_sayfasi_salt_okunur():
    html = (_FE / "galeri.html").read_text("utf-8")
    js = (_FE / "js" / "galeri.js").read_text("utf-8")
    for yasak in ("gl-duzen", "gl-cop", "gl-tasi", "gl-ad-form"):
        assert yasak not in html, yasak
    for yasak in ("/duzen", "X-Duzenleme"):
        assert yasak not in js, yasak
    # Tek yazma: kök LİSTESİ (karar 11-15). POST yalnız /kok'a, DELETE yalnız /kok/'a gider.
    import re as _re
    assert 'id="gl-ekle"' in html and 'id="gl-secici-ekle"' in html
    cagrilar = _re.findall(r"json\('([^']+)'[^)]*method: '(POST|DELETE)'", js.replace("\n", " "))
    assert len(cagrilar) == 2, cagrilar
    for cagri in cagrilar:
        assert cagri[0].startswith("/kok"), cagri
    assert "googleapis" not in html and "gstatic" not in html      # yazı tipi yerelden
    assert "/ui/css/galeri-tokens.css" in html and "/ui/css/galeri.css" in html


def test_galeri_sayfasi_js_idleri_html_de_var():
    import re
    html = (_FE / "galeri.html").read_text("utf-8")
    js = (_FE / "js" / "galeri.js").read_text("utf-8")
    ids = set(re.findall(r'id="([^"]+)"', html))
    assert set(re.findall(r"\$\('([a-z0-9-]+)'\)", js)) - ids == set()

"""Dosya gezgini (salt okunur, terminalsiz) — kök ayardan gelir, dizin dışına çıkılamaz, yazma ucu yok.

    cd backend && python -m pytest -q tests/test_dosya.py
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import dosya_api as d


@pytest.fixture()
def ortam(tmp_path, monkeypatch):
    kok = (tmp_path / "Belgelerim").resolve()
    (kok / "alt" / "derin").mkdir(parents=True)
    (kok / "not.txt").write_text("merhaba dunya")
    (kok / "alt" / "rapor.md").write_text("# rapor")
    (kok / "alt" / "derin" / "gizemli-dosya.txt").write_text("x")
    (kok / "ikili.txt").write_bytes(b"ab\x00cd")
    (kok / ".gizli").mkdir()
    (kok / ".gizli" / "g.txt").write_text("gizli")
    (kok / ".ssh").mkdir()
    (kok / ".ssh" / "id_rsa").write_text("ANAHTAR")
    disari = (tmp_path / "Disari").resolve()
    disari.mkdir()
    (disari / "sir.txt").write_text("SIR")
    monkeypatch.setattr(d, "AYAR_YOLU", tmp_path / "veri" / "dosya-ayar.json")
    monkeypatch.setenv("YUKI_DOSYA_KOKLER", str(kok))
    d._KAYIT.clear()
    d._BILETLER.clear()
    d._LISTE_ONBELLEK.clear()
    app = FastAPI()
    app.include_router(d.router)
    return TestClient(app), kok, disari


def _kok_id(c):
    return c.get("/api/dosya/kokler").json()["kokler"][0]["id"]


def test_kok_ortamdan_gelir_ve_liste(ortam):
    c, kok, _ = ortam
    r = c.get("/api/dosya/kokler").json()
    assert [k["yol"] for k in r["kokler"]] == [str(kok)]
    lst = c.get(f"/api/dosya/liste/{r['kokler'][0]['id']}").json()
    adlar = [g["ad"] for g in lst["girdiler"]]
    assert adlar == ["alt", "ikili.txt", "not.txt"]          # klasör önce; gizli girdiler yok
    assert lst["ust"] is None and "id" in lst["girdiler"][0]


def test_kok_ayar_dosyasindan(ortam, monkeypatch):
    c, kok, _ = ortam
    monkeypatch.delenv("YUKI_DOSYA_KOKLER")
    d.AYAR_YOLU.parent.mkdir(parents=True, exist_ok=True)
    d.AYAR_YOLU.write_text('{"kokler": ["%s"]}' % (kok / "alt"), "utf-8")
    assert [k["yol"] for k in c.get("/api/dosya/kokler").json()["kokler"]] == [str(kok / "alt")]


def test_varsayilan_kok_ev_dizini(ortam, monkeypatch, tmp_path):
    c, _, _ = ortam
    monkeypatch.delenv("YUKI_DOSYA_KOKLER")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert [k["yol"] for k in c.get("/api/dosya/kokler").json()["kokler"]] == [str(tmp_path.resolve())]


@pytest.mark.parametrize("kotu", ["../Disari/sir.txt", "../../etc/passwd", "/etc/passwd",
                                  "~/../../etc/passwd", "alt/../../Disari/sir.txt"])
def test_git_ile_dizin_disina_cikilamaz(ortam, kotu):
    c, kok, _ = ortam
    yol = kotu if kotu.startswith(("/", "~")) else str(kok / kotu)
    r = c.post("/api/dosya/git", json={"yol": yol})
    assert r.status_code in (400, 403, 404), (kotu, r.status_code)
    assert "root:" not in r.text and "SIR" not in r.text


def test_bozuk_ve_bilinmeyen_kimlik(ortam):
    c, _, _ = ortam
    _kok_id(c)
    for kotu in ("0000000000000000", "..%2F..%2Fetc", "%2e%2e"):
        for uc in ("liste", "bilgi", "onizle", "bilet", "ara"):
            r = c.get(f"/api/dosya/{uc}/{kotu}", params={"q": "x"} if uc == "ara" else None)
            assert r.status_code in (400, 403, 404, 405, 422), (uc, kotu, r.status_code)


def test_kok_disi_kimlik_reddedilir(ortam):
    c, _, disari = ortam
    _kok_id(c)
    for yol in (disari, disari / "sir.txt"):
        kid = d._kimlik(yol)                      # sunucu bu yolu bir kez görmüş olsa bile
        for uc in ("liste", "bilgi", "onizle", "bilet"):
            assert c.get(f"/api/dosya/{uc}/{kid}").status_code in (400, 403), (uc, yol)


def test_symlink_kok_disina_cikamaz(ortam):
    c, kok, disari = ortam
    (kok / "baglanti.txt").symlink_to(disari / "sir.txt")
    (kok / "baglanti-dizin").symlink_to(disari, target_is_directory=True)
    _kok_id(c)
    assert c.get(f"/api/dosya/onizle/{d._kimlik(kok / 'baglanti.txt')}").status_code == 403
    assert c.get(f"/api/dosya/liste/{d._kimlik(kok / 'baglanti-dizin')}").status_code == 403


def test_gizli_ve_hassas_kapilari(ortam):
    c, kok, _ = ortam
    _kok_id(c)
    gizli = d._kimlik(kok / ".gizli")
    assert c.get(f"/api/dosya/liste/{gizli}").status_code == 403
    assert c.get(f"/api/dosya/liste/{gizli}", params={"gizli": 1}).status_code == 200
    ssh = d._kimlik(kok / ".ssh" / "id_rsa")
    assert c.get(f"/api/dosya/onizle/{ssh}", params={"gizli": 1}).status_code == 403   # gizli=1'de de hassas
    assert c.get(f"/api/dosya/liste/{d._kimlik(kok / '.ssh')}", params={"gizli": 1}).status_code == 403


def test_onizle_metin_ve_ikili(ortam):
    c, kok, _ = ortam
    _kok_id(c)
    r = c.get(f"/api/dosya/onizle/{d._kimlik(kok / 'not.txt')}").json()
    assert r["metin"] == "merhaba dunya" and r["kesildi"] is False
    assert c.get(f"/api/dosya/onizle/{d._kimlik(kok / 'ikili.txt')}").status_code == 415


def test_ara_symlink_izlemez_gizli_ve_hassasi_atlar(ortam):
    c, kok, disari = ortam
    (disari / "gizemli-sir.txt").write_text("x")
    (kok / "alt" / "kacak").symlink_to(disari, target_is_directory=True)
    kid = _kok_id(c)
    ad = c.get(f"/api/dosya/ara/{kid}", params={"q": "gizemli"}).json()
    assert [s["ad"] for s in ad["sonuclar"]] == ["gizemli-dosya.txt"]   # symlink'in ardındaki dosya gelmez
    assert c.get(f"/api/dosya/ara/{kid}", params={"q": "id_rsa", "gizli": 1}).json()["sonuclar"] == []
    assert c.get(f"/api/dosya/ara/{kid}", params={"q": "g.txt"}).json()["sonuclar"] == []


def test_bilet_ve_akis_range(ortam):
    c, kok, _ = ortam
    _kok_id(c)
    b = c.get(f"/api/dosya/bilet/{d._kimlik(kok / 'not.txt')}").json()
    assert b["url"].startswith("/api/galeri/akis/d/")
    tam = c.get(b["url"])
    assert tam.status_code == 200 and tam.content == b"merhaba dunya"
    parca = c.get(b["url"], headers={"Range": "bytes=0-6"})
    assert parca.status_code == 206 and parca.content == b"merhaba"
    assert c.get("/api/galeri/akis/d/uydurma-bilet").status_code == 403
    assert c.get(f"/api/dosya/bilet/{d._kimlik(kok / 'alt')}").status_code == 400   # klasöre bilet yok


def test_yazma_uclari_yok(ortam):
    c, kok, _ = ortam
    kid = _kok_id(c)
    nid = d._kimlik(kok / "not.txt")
    for yontem, yol in [("post", "/api/dosya/duzen/sil"), ("post", "/api/dosya/duzen/tasi"),
                        ("post", "/api/dosya/duzen/ad"), ("post", "/api/dosya/duzen/klasor"),
                        ("post", "/api/dosya/duzen/kopyala"), ("get", "/api/dosya/duzen/durum"),
                        ("delete", f"/api/dosya/bilgi/{nid}"), ("put", f"/api/dosya/bilgi/{nid}"),
                        ("patch", f"/api/dosya/bilgi/{nid}"), ("post", f"/api/dosya/liste/{kid}"),
                        ("get", "/api/dosya/terminal"), ("post", "/api/dosya/terminal/ac")]:
        assert getattr(c, yontem)(yol).status_code in (404, 405), (yontem, yol)
    assert (kok / "not.txt").read_text() == "merhaba dunya"
    yazanlar = {(r.path, tuple(sorted(r.methods))) for r in d.router.routes
                if {"POST", "PUT", "PATCH", "DELETE"} & set(r.methods or ())}
    assert yazanlar == {("/api/dosya/git", ("POST",))}        # tek POST: yolu çözer, diske yazmaz
    assert not [r for r in d.router.routes if "websocket" in type(r).__name__.lower()]


def test_kaynak_yazma_ve_terminal_cagrisi_yok():
    kaynak = Path(d.__file__).read_text("utf-8")
    kod = "\n".join(s for s in kaynak.splitlines() if not s.lstrip().startswith("#"))
    for yasak in (".write_text(", ".write_bytes(", ".unlink(", ".rename(", "os.replace", "shutil.",
                  "os.remove", "os.rename", "os.makedirs", ".mkdir(", ".rmdir(", "open(\"w", "'wb'",
                  "pty", "subprocess", "guvenli_dosya"):
        assert yasak not in kod, yasak
    assert "/home/" not in kaynak and ("ih" + "san") not in kaynak.lower()
    assert "/mnt/" not in kaynak


# ── Ön yüz: kabuk bağı + salt okunur yüzey ─────────────────────────────── #
_FE = Path(__file__).resolve().parents[2] / "frontend"


def test_main_dosya_yonlendiricisini_kaydeder():
    main = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text("utf-8")
    assert "dosya_api.router" in main and "/api/galeri/akis/" in main


def test_kabuk_dosya_sekmesi_bagli():
    html = (_FE / "index.html").read_text("utf-8")
    assert 'id="tab-btn-dosya"' in html and "switchTab('dosya')" in html
    assert 'id="tab-dosya"' in html and 'id="dosya-iframe"' in html
    nav = (_FE / "js" / "tab-nav.js").read_text("utf-8")
    assert "tab-dosya" in nav and "/ui/dosya.html" in nav
    for dil in ("tr", "en"):
        sozluk = (_FE / "js" / "diller" / f"{dil}.js").read_text("utf-8")
        assert "'nav.dosya'" in sozluk and "'nav.8-dosya'" in sozluk


def test_dosya_sayfasi_salt_okunur_ve_terminalsiz():
    html = (_FE / "dosya.html").read_text("utf-8")
    js = (_FE / "js" / "dosya.js").read_text("utf-8")
    css = (_FE / "css" / "dosya.css").read_text("utf-8")
    for metin in (html, js, css):
        assert not re.search(r"xterm|\bpty\b|terminal|cekmece|dy-duzen|dy-serit\b|dy-modal|X-Duzenleme|/duzen",
                             metin, re.I)
    for yasak in ("method: 'DELETE'", "method: 'PUT'", "method: 'PATCH'", "draggable"):
        assert yasak not in js, yasak
    assert js.count("method: 'POST'") == 2 and js.count("/api/dosya/git") == 2   # yalnız yol çözme
    assert "googleapis" not in html and "gstatic" not in html
    assert not (_FE / "js" / "dosya-terminal.js").exists()


def test_dosya_sayfasi_js_idleri_html_de_var():
    html = (_FE / "dosya.html").read_text("utf-8")
    js = (_FE / "js" / "dosya.js").read_text("utf-8")
    ids = set(re.findall(r'id="([^"]+)"', html))
    assert set(re.findall(r"\$\('([a-z0-9-]+)'\)", js)) - ids == set()

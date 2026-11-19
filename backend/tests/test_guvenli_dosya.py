"""Güvenli dosya işlemleri (çöpe at · taşı · geri al) — varsayılan KAPALI, açık hâli.

Kapalıyken: dosya gezgini salt okunur kalır (`test_dosya.py` aynen geçer), bu yönlendiricinin
işlem uçları 404'tür. Açıkken: her yıkıcı işlem iki adımlı (hazırla → kullanıcı onayı → uygula),
silme kalıcı değil (çöp klasörüne taşınır), her işlem günlüğe yazılır ve geri alınır.

    cd backend && python -m pytest -q tests/test_guvenli_dosya.py
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import config as cfg
from app.api import dosya_api as d
from app.api import guvenli_dosya_api as gapi
from app.services import guvenli_dosya as gd

ANAHTAR = "dogru-anahtar-123"


@pytest.fixture()
def ortam(tmp_path, monkeypatch):
    kok = (tmp_path / "Belgelerim").resolve()
    (kok / "alt").mkdir(parents=True)
    (kok / "not.txt").write_text("merhaba")
    (kok / "ikinci.txt").write_text("iki")
    (kok / "alt" / "rapor.md").write_text("# rapor")
    (kok / ".ssh").mkdir()
    (kok / ".ssh" / "id_rsa").write_text("ANAHTAR")
    disari = (tmp_path / "Disari").resolve()
    disari.mkdir()
    (disari / "sir.txt").write_text("SIR")
    veri = tmp_path / "veri"
    monkeypatch.setattr(d, "AYAR_YOLU", veri / "dosya-ayar.json")
    monkeypatch.setattr(gd, "VERI_DIZINI", veri / "guvenli")
    monkeypatch.setenv("YUKI_DOSYA_KOKLER", str(kok))
    monkeypatch.setattr(cfg, "AUTH_TOKEN", ANAHTAR, raising=False)
    d._KAYIT.clear()
    d._BILETLER.clear()
    d._LISTE_ONBELLEK.clear()
    gd._BEKLEYEN.clear()
    app = FastAPI()
    app.include_router(d.router)
    app.include_router(gapi.router)
    return TestClient(app), kok, disari


def _id(c, yol: Path) -> str:
    r = c.post("/api/dosya/git", json={"yol": str(yol)})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _ac(c):
    r = c.put("/api/guvenli-dosya/ayar", json={"acik": True, "anahtar": ANAHTAR})
    assert r.status_code == 200, r.text


def _hazirla_uygula(c, govde):
    h = c.post("/api/guvenli-dosya/hazirla", json=govde)
    assert h.status_code == 200, h.text
    u = c.post("/api/guvenli-dosya/uygula", json={"onay": h.json()["onay"]})
    assert u.status_code == 200, u.text
    return h.json(), u.json()


# ── Kapalı (varsayılan) ──────────────────────────────────────────── #

def test_varsayilan_kapali_ve_islem_uclari_404(ortam):
    c, kok, _ = ortam
    assert c.get("/api/guvenli-dosya/durum").json() == {"acik": False, "anahtar_kurulu": True}
    nid = _id(c, kok / "not.txt")
    for yontem, yol, govde in [
        ("post", "/api/guvenli-dosya/hazirla", {"tur": "cop", "ogeler": [nid]}),
        ("post", "/api/guvenli-dosya/uygula", {"onay": "x" * 32}),
        ("get", "/api/guvenli-dosya/gunluk", None),
        ("post", "/api/guvenli-dosya/geri-al/abc", None),
    ]:
        r = getattr(c, yontem)(yol, **({"json": govde} if govde is not None else {}))
        assert r.status_code == 404, (yol, r.status_code)
    assert (kok / "not.txt").read_text() == "merhaba"


def test_ayar_okunamazsa_kapali(ortam):
    c, _, _ = ortam
    gd.VERI_DIZINI.mkdir(parents=True, exist_ok=True)
    (gd.VERI_DIZINI / "ayar.json").write_text("{bozuk", "utf-8")
    assert gd.acik() is False
    (gd.VERI_DIZINI / "ayar.json").write_text('{"acik": "evet"}', "utf-8")
    assert gd.acik() is False                      # yalnız gerçek True açar


def test_acmak_anahtar_ister(ortam, monkeypatch):
    c, _, _ = ortam
    assert c.put("/api/guvenli-dosya/ayar", json={"acik": True}).status_code == 403
    assert c.put("/api/guvenli-dosya/ayar", json={"acik": True, "anahtar": "yanlis"}).status_code == 403
    assert gd.acik() is False
    monkeypatch.setattr(cfg, "AUTH_TOKEN", "", raising=False)
    assert c.put("/api/guvenli-dosya/ayar", json={"acik": True, "anahtar": ""}).status_code == 409
    assert gd.acik() is False


def test_kapatmak_serbest_ve_anahtar_bosalinca_kapali(ortam, monkeypatch):
    c, kok, _ = ortam
    _ac(c)
    assert c.get("/api/guvenli-dosya/durum").json()["acik"] is True
    monkeypatch.setattr(cfg, "AUTH_TOKEN", "", raising=False)       # sonradan boşaltıldı
    assert c.get("/api/guvenli-dosya/durum").json()["acik"] is False
    nid = _id(c, kok / "not.txt")
    assert c.post("/api/guvenli-dosya/hazirla", json={"tur": "cop", "ogeler": [nid]}).status_code == 404
    monkeypatch.setattr(cfg, "AUTH_TOKEN", ANAHTAR, raising=False)
    assert c.put("/api/guvenli-dosya/ayar", json={"acik": False}).status_code == 200
    assert c.get("/api/guvenli-dosya/durum").json()["acik"] is False


# ── Açık: onay ───────────────────────────────────────────────────── #

def test_hazirla_dosyaya_dokunmaz_ve_onay_tek_kullanimlik(ortam):
    c, kok, _ = ortam
    _ac(c)
    nid = _id(c, kok / "not.txt")
    h = c.post("/api/guvenli-dosya/hazirla", json={"tur": "cop", "ogeler": [nid]}).json()
    assert (kok / "not.txt").exists()                               # onaysız hiçbir şey olmaz
    assert h["ozet"]["sayi"] == 1 and h["ozet"]["adlar"] == ["not.txt"]
    assert c.post("/api/guvenli-dosya/uygula", json={"onay": h["onay"]}).status_code == 200
    assert c.post("/api/guvenli-dosya/uygula", json={"onay": h["onay"]}).status_code == 410
    assert c.post("/api/guvenli-dosya/uygula", json={"onay": "uydurma"}).status_code == 410


def test_onay_suresi_dolar(ortam, monkeypatch):
    c, kok, _ = ortam
    _ac(c)
    nid = _id(c, kok / "not.txt")
    h = c.post("/api/guvenli-dosya/hazirla", json={"tur": "cop", "ogeler": [nid]}).json()
    simdi = gd.time.time()
    monkeypatch.setattr(gd.time, "time", lambda: simdi + gd.ONAY_OMUR + 1)
    assert c.post("/api/guvenli-dosya/uygula", json={"onay": h["onay"]}).status_code == 410
    assert (kok / "not.txt").exists()


# ── Açık: çöpe at + geri al ──────────────────────────────────────── #

def test_cope_at_kalici_silmez_ve_geri_al(ortam):
    c, kok, _ = ortam
    _ac(c)
    ids = [_id(c, kok / "not.txt"), _id(c, kok / "alt")]
    _, u = _hazirla_uygula(c, {"tur": "cop", "ogeler": ids})
    assert not (kok / "not.txt").exists() and not (kok / "alt").exists()
    cop = list((gd.VERI_DIZINI / "cop").rglob("rapor.md"))
    assert len(cop) == 1 and cop[0].read_text() == "# rapor"        # silinmedi, çöpte
    g = c.get("/api/guvenli-dosya/gunluk").json()["islemler"]
    assert g[0]["id"] == u["islem"] and g[0]["tur"] == "cop" and g[0]["geri_alindi"] is False
    r = c.post(f"/api/guvenli-dosya/geri-al/{u['islem']}")
    assert r.status_code == 200, r.text
    assert (kok / "not.txt").read_text() == "merhaba"
    assert (kok / "alt" / "rapor.md").read_text() == "# rapor"
    assert c.get("/api/guvenli-dosya/gunluk").json()["islemler"][0]["geri_alindi"] is True
    assert c.post(f"/api/guvenli-dosya/geri-al/{u['islem']}").status_code == 409   # iki kez olmaz
    (kok / "not.txt").rename(kok / "baska-ad.txt")                  # eski yer boşaldı: yine de iki kez olmaz
    r = c.post(f"/api/guvenli-dosya/geri-al/{u['islem']}")
    assert r.status_code == 409 and "zaten geri alındı" in r.json()["detail"]


def test_geri_al_ustune_yazmaz(ortam):
    c, kok, _ = ortam
    _ac(c)
    _, u = _hazirla_uygula(c, {"tur": "cop", "ogeler": [_id(c, kok / "not.txt")]})
    (kok / "not.txt").write_text("YENI")                            # aynı adla yeni dosya geldi
    assert c.post(f"/api/guvenli-dosya/geri-al/{u['islem']}").status_code == 409
    assert (kok / "not.txt").read_text() == "YENI"
    assert len(list((gd.VERI_DIZINI / "cop").rglob("*-not.txt"))) == 1


# ── Açık: taşı ───────────────────────────────────────────────────── #

def test_tasi_ve_geri_al(ortam):
    c, kok, _ = ortam
    _ac(c)
    _, u = _hazirla_uygula(c, {"tur": "tasi", "ogeler": [_id(c, kok / "not.txt")],
                               "hedef": _id(c, kok / "alt")})
    assert (kok / "alt" / "not.txt").read_text() == "merhaba" and not (kok / "not.txt").exists()
    assert c.post(f"/api/guvenli-dosya/geri-al/{u['islem']}").status_code == 200
    assert (kok / "not.txt").exists() and not (kok / "alt" / "not.txt").exists()


def test_tasi_ustune_yazmaz(ortam):
    c, kok, _ = ortam
    _ac(c)
    (kok / "alt" / "not.txt").write_text("hedefteki")
    r = c.post("/api/guvenli-dosya/hazirla", json={"tur": "tasi", "ogeler": [_id(c, kok / "not.txt")],
                                                  "hedef": _id(c, kok / "alt")})
    assert r.status_code == 409
    assert (kok / "alt" / "not.txt").read_text() == "hedefteki" and (kok / "not.txt").exists()


def test_klasor_kendi_icine_tasinmaz(ortam):
    c, kok, _ = ortam
    _ac(c)
    (kok / "alt" / "ic").mkdir()
    r = c.post("/api/guvenli-dosya/hazirla", json={"tur": "tasi", "ogeler": [_id(c, kok / "alt")],
                                                  "hedef": _id(c, kok / "alt" / "ic")})
    assert r.status_code == 400


def test_hedef_klasor_olmali(ortam):
    c, kok, _ = ortam
    _ac(c)
    r = c.post("/api/guvenli-dosya/hazirla", json={"tur": "tasi", "ogeler": [_id(c, kok / "not.txt")],
                                                  "hedef": _id(c, kok / "ikinci.txt")})
    assert r.status_code == 400


def test_uygulama_arasinda_hedef_dolarsa_hicbiri_tasinmaz(ortam):
    """Hazırla ile uygula arasında çakışma doğarsa işlem ya hep ya hiç: yarıda kalan geri sarılır."""
    c, kok, _ = ortam
    _ac(c)
    h = c.post("/api/guvenli-dosya/hazirla", json={
        "tur": "tasi", "ogeler": [_id(c, kok / "not.txt"), _id(c, kok / "ikinci.txt")],
        "hedef": _id(c, kok / "alt")}).json()
    (kok / "alt" / "ikinci.txt").write_text("araya girdi")
    assert c.post("/api/guvenli-dosya/uygula", json={"onay": h["onay"]}).status_code == 409
    assert (kok / "not.txt").read_text() == "merhaba"
    assert (kok / "ikinci.txt").read_text() == "iki"
    assert not (kok / "alt" / "not.txt").exists()
    assert (kok / "alt" / "ikinci.txt").read_text() == "araya girdi"


# ── Açık: yol kapıları (okumayla aynı + kök korunur) ─────────────── #

def test_kok_disi_kok_kendisi_gizli_ve_hassas_reddedilir(ortam):
    c, kok, disari = ortam
    _ac(c)
    kok_id = c.get("/api/dosya/kokler").json()["kokler"][0]["id"]
    assert c.post("/api/guvenli-dosya/hazirla", json={"tur": "cop", "ogeler": [kok_id]}).status_code == 403
    dis_id = d._kimlik(disari / "sir.txt")                          # kayda sokulmuş kök dışı yol
    assert c.post("/api/guvenli-dosya/hazirla", json={"tur": "cop", "ogeler": [dis_id]}).status_code == 403
    ssh_id = d._kimlik(kok / ".ssh" / "id_rsa")
    assert c.post("/api/guvenli-dosya/hazirla", json={"tur": "cop", "ogeler": [ssh_id]}).status_code == 403
    assert c.post("/api/guvenli-dosya/hazirla",
                  json={"tur": "cop", "ogeler": [ssh_id], "gizli": True}).status_code == 403
    assert c.post("/api/guvenli-dosya/hazirla", json={
        "tur": "tasi", "ogeler": [_id(c, kok / "not.txt")], "hedef": d._kimlik(disari)}).status_code == 403
    assert (disari / "sir.txt").exists() and (kok / ".ssh" / "id_rsa").exists()


def test_symlink_kok_disina_kacamaz(ortam):
    c, kok, disari = ortam
    _ac(c)
    (kok / "kacak").symlink_to(disari)
    r = c.post("/api/guvenli-dosya/hazirla", json={"tur": "tasi", "ogeler": [_id(c, kok / "not.txt")],
                                                  "hedef": d._kimlik(kok / "kacak")})
    assert r.status_code == 403
    assert (kok / "not.txt").exists()


def test_bos_ve_cok_fazla_oge(ortam):
    c, kok, _ = ortam
    _ac(c)
    assert c.post("/api/guvenli-dosya/hazirla", json={"tur": "cop", "ogeler": []}).status_code == 422
    nid = _id(c, kok / "not.txt")
    assert c.post("/api/guvenli-dosya/hazirla",
                  json={"tur": "cop", "ogeler": [nid] * (gd.AZAMI_OGE + 1)}).status_code == 422
    assert c.post("/api/guvenli-dosya/hazirla", json={"tur": "sil", "ogeler": [nid]}).status_code == 422


def test_gunluk_diske_yazilir_ve_yeniden_okunur(ortam):
    c, kok, _ = ortam
    _ac(c)
    _, u = _hazirla_uygula(c, {"tur": "cop", "ogeler": [_id(c, kok / "not.txt")]})
    assert (gd.VERI_DIZINI / "gunluk.json").exists()
    assert gd.gunluk()[0]["id"] == u["islem"]


# ── Kaynak bekçileri ─────────────────────────────────────────────── #

def test_kalici_silme_cagrisi_yok():
    """Çöp boşaltma da yok: modül hiçbir yolu kalıcı silmez (yalnız taşır)."""
    for mod in (gd, gapi):
        kaynak = Path(mod.__file__).read_text("utf-8")
        kod = "\n".join(s for s in kaynak.splitlines() if not s.lstrip().startswith("#"))
        for yasak in (".unlink(", "os.remove", "rmtree", ".rmdir(", "os.unlink", "subprocess"):
            assert yasak not in kod, (mod.__name__, yasak)
        assert "/home/" not in kaynak and ("ih" + "san") not in kaynak.lower() and "/mnt/" not in kaynak


def test_dosya_api_salt_okunur_kalir():
    """Yazma bu ayrı modülde yaşar; dosya_api.py'ye hiçbir yazma ucu eklenmedi."""
    yazanlar = {(r.path, tuple(sorted(r.methods))) for r in d.router.routes
                if {"POST", "PUT", "PATCH", "DELETE"} & set(r.methods or ())}
    assert yazanlar == {("/api/dosya/git", ("POST",))}


# ── Galeri kaynağı: aynı uç, galerinin kendi beş kapısı ──────────── #

from app.api import galeri_api as g  # noqa: E402


def _png() -> bytes:
    import io

    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (4, 3), (200, 30, 30)).save(b, "PNG")
    return b.getvalue()


@pytest.fixture()
def galeri(ortam, tmp_path, monkeypatch):
    c, _, _ = ortam
    gk = (tmp_path / "Resimlerim").resolve()
    (gk / "tatil").mkdir(parents=True)
    (gk / "a.png").write_bytes(_png())
    (gk / "tatil" / "b.png").write_bytes(_png())
    (gk / "notlar.txt").write_text("medya değil")
    gdis = (tmp_path / "GaleriDisi").resolve()
    gdis.mkdir()
    (gdis / "sir.png").write_bytes(_png())
    monkeypatch.setattr(g, "VERI", tmp_path / "gveri")
    monkeypatch.setattr(g, "ONBELLEK", tmp_path / "gveri" / "onbellek")
    monkeypatch.setattr(g, "AYAR_YOLU", tmp_path / "gveri" / "galeri-ayar.json")
    monkeypatch.setenv("YUKI_GALERI_KOKLER", str(gk))
    monkeypatch.setattr(g, "_TUM_ONBELLEK", (0.0, (), []))
    g._KAYIT.clear()
    c.app.include_router(g.router)
    return c, gk, gdis


def test_galeri_kapaliyken_404(galeri):
    c, gk, _ = galeri
    r = c.post("/api/guvenli-dosya/hazirla", json={"kaynak": "galeri", "tur": "cop", "ogeler": [g._kimlik(gk / "a.png")]})
    assert r.status_code == 404 and (gk / "a.png").exists()


def test_galeri_cope_at_tasi_geri_al(galeri):
    c, gk, _ = galeri
    _ac(c)
    assert c.get("/api/galeri/hepsi").json()["toplam"] == 2
    _, u = _hazirla_uygula(c, {"kaynak": "galeri", "tur": "cop", "ogeler": [g._kimlik(gk / "a.png")]})
    assert not (gk / "a.png").exists()
    assert c.get("/api/galeri/hepsi").json()["toplam"] == 1        # galeri önbelleği tazelendi
    assert c.post(f"/api/guvenli-dosya/geri-al/{u['islem']}").status_code == 200
    assert (gk / "a.png").exists() and c.get("/api/galeri/hepsi").json()["toplam"] == 2
    _, u2 = _hazirla_uygula(c, {"kaynak": "galeri", "tur": "tasi", "ogeler": [g._kimlik(gk / "a.png")],
                                "hedef": g._kimlik(gk / "tatil")})
    assert (gk / "tatil" / "a.png").exists() and not (gk / "a.png").exists()


def test_galeri_kapilari(galeri):
    c, gk, gdis = galeri
    _ac(c)
    for kid in (g._kimlik(gdis / "sir.png"),            # galeri kökü dışı
                g._kimlik(gk / "notlar.txt"),            # medya değil
                g._kimlik(gk / "tatil")):                # klasör: galeride yalnız dosya
        r = c.post("/api/guvenli-dosya/hazirla", json={"kaynak": "galeri", "tur": "cop", "ogeler": [kid]})
        assert r.status_code in (403, 404, 415), (kid, r.status_code)
    r = c.post("/api/guvenli-dosya/hazirla", json={"kaynak": "galeri", "tur": "tasi",
                                                  "ogeler": [g._kimlik(gk / "a.png")], "hedef": g._kimlik(gdis)})
    assert r.status_code == 403
    assert (gdis / "sir.png").exists() and (gk / "notlar.txt").exists() and (gk / "a.png").exists()


def test_galeri_kimligi_dosya_kaynagiyla_karismaz(galeri):
    """Galeri kimliği dosya kaynağında geçmez (ayrı kayıt, ayrı kökler)."""
    c, gk, _ = galeri
    _ac(c)
    r = c.post("/api/guvenli-dosya/hazirla", json={"tur": "cop", "ogeler": [g._kimlik(gk / "a.png")]})
    assert r.status_code in (403, 404)

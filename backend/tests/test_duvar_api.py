"""Duvar kâğıdı API testleri (2026-09-07).

Kapsanan davranışlar — hepsi ya güvenlik kapısı ya da sessiz-bozulma kapısı:
  · uzantı + İÇERİK imzası (uzantıya güvenilmez)
  · path traversal
  · boyut sınırı
  · silinen duvarın ayarlardan da düşmesi (yoksa sekme sessizce boşalır)
  · var olmayan duvar/sekme adının ayara yazılamaması
"""

import io
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from app.api import duvar_api


@pytest.fixture(autouse=True)
def gecici_depo(tmp_path, monkeypatch):
    """Her test kendi deposunda koşar — gerçek duvar kitaplığına dokunulmaz."""
    depo = tmp_path / "duvar"
    depo.mkdir()
    monkeypatch.setattr(duvar_api, "DEPO", depo)
    monkeypatch.setattr(duvar_api, "AYAR_YOLU", depo / "ayar.json")
    yield depo


@pytest.fixture
def istemci():
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(duvar_api.router)
    return TestClient(app)


# Gerçek imzalı en küçük örnekler
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
GIF = b"GIF89a" + b"\x00" * 40
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 40
MP4 = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 40
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 40
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 40


def _yukle(istemci, ad, veri):
    return istemci.post("/api/duvar/yukle",
                        files={"dosya": (ad, io.BytesIO(veri), "application/octet-stream")})


# ── Biçim kabulü ─────────────────────────────────────────────── #

@pytest.mark.parametrize("ad,veri,tip", [
    ("a.png", PNG, "resim"), ("a.gif", GIF, "resim"), ("a.jpg", JPG, "resim"),
    ("a.webp", WEBP, "resim"), ("a.mp4", MP4, "video"), ("a.webm", WEBM, "video"),
])
def test_gecerli_bicimler_kabul(istemci, ad, veri, tip):
    r = _yukle(istemci, ad, veri)
    assert r.status_code == 200, r.text
    assert r.json()["tip"] == tip


def test_desteklenmeyen_uzanti_reddedilir(istemci):
    r = _yukle(istemci, "kotu.exe", b"MZ\x90\x00")
    assert r.status_code == 400
    assert "Desteklenmeyen" in r.json()["detail"]


def test_uzanti_dogru_icerik_yanlis_reddedilir(istemci):
    """🔑 Asıl kapı: `.png` uzantılı HTML kabul edilmemeli.

    Uzantıya güvenilseydi depoya rastgele içerik girer, tarayıcıda bozuk
    görsel olarak görünür ve sebebi anlaşılmazdı.
    """
    r = _yukle(istemci, "sahte.png", b"<html><script>alert(1)</script></html>")
    assert r.status_code == 400
    assert "uyu" in r.json()["detail"].lower()


def test_boyut_siniri(istemci, monkeypatch):
    monkeypatch.setattr(duvar_api, "AZAMI_BOYUT", 1024)
    r = _yukle(istemci, "buyuk.png", PNG + b"\x00" * 4096)
    assert r.status_code == 413
    # Yarım dosya depoda kalmamalı
    assert not list(duvar_api.DEPO.glob("*.tmp"))
    assert not list(duvar_api.DEPO.glob("*.png"))


# ── Path traversal ───────────────────────────────────────────── #

@pytest.mark.parametrize("kotu", ["../../../etc/passwd", "..%2fgizli", "alt/dizin.png", "..\\win.ini"])
def test_path_traversal_http_uzerinden_reddedilir(istemci, kotu):
    r = istemci.get(f"/api/duvar/dosya/{kotu}")
    assert r.status_code in (400, 404), f"{kotu} geçti!"


@pytest.mark.parametrize("kotu", [
    "../../../etc/passwd", "../ayar.json", "alt/dizin.png", "..\\win.ini",
    "", "..", "./../gizli",
])
def test_path_traversal_kapisi_dogrudan_reddeder(gecici_depo, kotu):
    """🔑 Kapıyı DOĞRUDAN sına — HTTP katmanı onu maskeliyor.

    Bu testin HTTP'li kardeşi (`…http_uzerinden…`) mutasyonla sınandığında
    YEŞİL kaldı: Starlette bu yolları route eşleşmesinde zaten 404'lüyor,
    yani `_yol_coz` hiç çağrılmıyordu. Kapı sökülse bile test bunu göremezdi.
    İkinci savunma hattı ancak doğrudan çağrılarak ölçülür.
    """
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        duvar_api._yol_coz(kotu)
    assert e.value.status_code in (400, 404)


def test_depo_disindaki_GERCEK_dosyaya_erisilemez(gecici_depo):
    """🔑 Traversal kapısının TEK anlamlı testi: hedef gerçekten var olmalı.

    Yukarıdaki liste (`/etc/passwd` vb.) mutasyonla sınandığında YEŞİL kaldı:
    `tmp_path` altında o yollar mevcut olmadığı için `_yol_coz` son satırdaki
    `exists()` kontrolünden 404 fırlatıyordu — yani test geçiyordu ama
    traversal kapısı sökülü olsa da geçerdi. Kapı, ancak erişim GERÇEKTEN
    mümkün olduğunda ölçülebilir.
    """
    from fastapi import HTTPException
    gizli = gecici_depo.parent / "gizli.txt"
    gizli.write_text("sır")
    assert gizli.exists()                       # hedef var — kapı olmasa okunurdu
    with pytest.raises(HTTPException):
        duvar_api._yol_coz("../gizli.txt")


def test_yol_coz_gecerli_dosyayi_dondurur(gecici_depo):
    """Kapı iki yönlü olmalı: reddettiği kadar KABUL ettiğini de sına.

    Yoksa `raise HTTPException` yazıp her şeyi reddeden bir kapı da
    yukarıdaki testi geçerdi.
    """
    (gecici_depo / "abc__x.png").write_bytes(PNG)
    p = duvar_api._yol_coz("abc__x.png")
    assert p.exists() and p.name == "abc__x.png"


def test_yuklemede_dizin_adi_soyulur(istemci):
    """`../../kotu.png` yüklense bile depo dışına yazılmaz."""
    r = _yukle(istemci, "../../kotu.png", PNG)
    assert r.status_code == 200
    yeni = r.json()["id"]
    assert "/" not in yeni and ".." not in yeni
    assert (duvar_api.DEPO / yeni).exists()


# ── Ayar ─────────────────────────────────────────────────────── #

def test_olmayan_duvar_ayara_yazilamaz(istemci):
    r = istemci.put("/api/duvar/ayar", json={
        "mod": "sekme", "sekmeler": {"hq": "olmayan.png"}, "perde": 50, "bulanik": 0,
    })
    assert r.status_code == 200
    assert r.json()["ayar"]["sekmeler"] == {}


def test_olmayan_sekme_adi_elenir(istemci):
    d = _yukle(istemci, "a.png", PNG).json()["id"]
    r = istemci.put("/api/duvar/ayar", json={
        "mod": "sekme", "sekmeler": {"hq": d, "uydurma_sekme": d}, "perde": 50, "bulanik": 0,
    })
    s = r.json()["ayar"]["sekmeler"]
    assert s == {"hq": d}


def test_perde_araligi_zorlanir(istemci):
    r = istemci.put("/api/duvar/ayar", json={"mod": "tek", "perde": 999, "bulanik": 0})
    assert r.status_code == 422        # pydantic sınırı


def test_bozuk_ayar_dosyasi_varsayilana_duser(gecici_depo, istemci):
    duvar_api.AYAR_YOLU.write_text("{bu json değil")
    r = istemci.get("/api/duvar/ayar")
    assert r.status_code == 200
    assert r.json()["ayar"]["mod"] == "sekme"


# ── Silme ────────────────────────────────────────────────────── #

def test_silinen_duvar_ayardan_da_duser(istemci):
    """🔑 Yoksa sekme açılışta 404 yer ve arka plan SESSİZCE boş kalır."""
    d = _yukle(istemci, "a.png", PNG).json()["id"]
    istemci.put("/api/duvar/ayar", json={
        "mod": "sekme", "sekmeler": {"hq": d, "chat": d}, "perde": 50, "bulanik": 0,
    })
    r = istemci.delete(f"/api/duvar/{d}")
    assert r.status_code == 200
    assert r.json()["ayar_guncellendi"] is True
    assert istemci.get("/api/duvar/ayar").json()["ayar"]["sekmeler"] == {}


def test_silinen_duvar_tek_moddan_da_duser(istemci):
    d = _yukle(istemci, "a.png", PNG).json()["id"]
    istemci.put("/api/duvar/ayar", json={"mod": "tek", "tek": d, "perde": 50, "bulanik": 0})
    istemci.delete(f"/api/duvar/{d}")
    assert istemci.get("/api/duvar/ayar").json()["ayar"]["tek"] is None


def test_olmayan_duvar_silinemez(istemci):
    assert istemci.delete("/api/duvar/yok.png").status_code == 404


# ── Liste / dosya ────────────────────────────────────────────── #

def test_liste_tip_ve_sekmeleri_dondurur(istemci):
    _yukle(istemci, "r.png", PNG)
    _yukle(istemci, "v.mp4", MP4)
    d = istemci.get("/api/duvar/liste").json()
    assert {x["tip"] for x in d["duvarlar"]} == {"resim", "video"}
    # 🔴 ÜRÜNE TAŞINIRKEN DEĞİŞTİ: kişiselde burada "nmap" aranıyordu.
    # Üründe öyle bir sekme YOK (ürünleştirmede söküldü) — kopyalasaydık test
    # olmayan bir yüzeyi doğruluyor olurdu. Ürünün gerçek sekmeleri ölçüldü
    # (index.html `data-tab=`): chat · planner · hq · panel.
    assert set(d["sekmeler"]) == {"chat", "planner", "hq", "panel"}
    for yok in ("nmap", "map", "drive", "kripto", "odak"):
        assert yok not in d["sekmeler"], f"kişiselin sekmesi ürüne sızmış: {yok}"


def test_dosya_indirilebilir(istemci):
    d = _yukle(istemci, "a.png", PNG).json()["id"]
    r = istemci.get(f"/api/duvar/dosya/{d}")
    assert r.status_code == 200
    assert r.content.startswith(b"\x89PNG")
    assert "image/png" in r.headers["content-type"]


def test_ayar_dosyasi_listede_gorunmez(istemci):
    """`ayar.json` depoda yaşıyor ama duvar kâğıdı değil."""
    istemci.put("/api/duvar/ayar", json={"mod": "kapali", "perde": 50, "bulanik": 0})
    _yukle(istemci, "a.png", PNG)
    adlar = [x["id"] for x in istemci.get("/api/duvar/liste").json()["duvarlar"]]
    assert "ayar.json" not in adlar
    assert len(adlar) == 1

"""HQ › Güvenlik › YÜZ · KİMLİK KARTI — sunucu tarafı + panel bekçileri (2026-09-27).

Kişisel 517e975'in ürün karşılığı. Kart üç şey soruyor ve üçünü de ürün söylemiyordu:
  ① sahibin kaç yüz örneği var — `/status` yalnız sahip ADINI dönüyordu; eski müşteri
     verisinde ad 'İpek', örnekler 'ipek' altında olabilir (ikiz yazım, 8f04116)
  ② canlılık kontrolü açık mı — kapalıysa kilit bir FOTOĞRAFLA açılabilir; yalnız .env'de
  ③ GİRİŞİ DENE: tanınan kişi sahip mi — ön yüz adı birebir karşılaştırırsa ikiz yazımda
     "açılmazdı" der, kilit ekranı ise açar (sunucu `ad_anahtari` ile bakıyor)
Ad eşlemesi ön yüzde TEKRAR yazılmadı: tek kaynak `face_multi_auth.ad_anahtari`.
"""
import re
from pathlib import Path

import numpy as np
import pytest
from starlette.testclient import TestClient

from app.services import face_multi_auth as fma
from app.services import face_store

KOK = Path(__file__).resolve().parents[2]
FACES_JS = (KOK / "frontend" / "js" / "faces.js").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def temiz():
    face_store._sifirla()
    yield
    face_store._sifirla()


def _emb(tohum: int) -> np.ndarray:
    v = np.random.default_rng(tohum).normal(size=512).astype(np.float32)
    return v / np.linalg.norm(v)


def test_sahip_kaydi_YAZIMDAN_bagimsiz_bulunur():
    face_store.ekle("ipek", _emb(1))
    face_store.ekle("ipek", _emb(2))
    face_store.ekle("misafir", _emb(3))
    face_store.sahip_yaz("İpek")
    k = fma.sahip_kaydi()
    assert k and k["name"] == "ipek" and k["encodings"] == 2
    assert fma.sahip_mi("IPEK".replace("I", "İ")) and not fma.sahip_mi("misafir")


def test_sahip_yoksa_kayit_da_yok():
    face_store.ekle("misafir", _emb(3))
    assert fma.sahip_kaydi() is None and fma.sahip_mi("misafir") is False


def test_status_karta_ornek_sayisi_ve_canliligi_verir(monkeypatch):
    from app.main import app
    face_store.ekle("ipek", _emb(1))
    face_store.sahip_yaz("İpek")
    d = TestClient(app).get("/api/face/status").json()
    assert d["owner"] == "İpek" and d["sahip_kaydi"] == "ipek" and d["sahip_ornek"] == 1
    assert isinstance(d["canlilik"], bool)


def test_scan_tanidigi_kisinin_SAHIP_olup_olmadigini_soyler(monkeypatch):
    from app.api import face_api
    from app.main import app
    monkeypatch.setattr(face_api, "_kapali_mi", lambda: None)
    face_store.sahip_yaz("İpek")
    c = TestClient(app)
    for ad, beklenen in (("ipek", True), ("misafir", False)):
        async def _tani(veri, ad=ad):
            return {"known": True, "name": ad, "confidence": 0.9, "verdict": "high", "faces_detected": 1}
        monkeypatch.setattr(fma, "recognize_face", _tani)
        r = c.post("/api/face/scan", files={"file": ("k.jpg", b"\xff\xd8\xff" + b"0" * 32, "image/jpeg")},
                   data={"notify": "false"})
        assert r.status_code == 200 and r.json()["sahip"] is beklenen, (ad, r.text)


# ── panel (faces.js) ─────────────────────────────────────────────────────────
def test_giris_dene_sahipligi_SUNUCUDAN_okur():
    """③ — ön yüz adı kendisi karşılaştırmaz."""
    m = re.search(r"async function girisiDene\(.*?\n  \}", FACES_JS, re.S)
    assert m, "girisiDene bulunamadı"
    assert "d.sahip" in m.group(0)
    assert "=== _sahipAdi" not in m.group(0) and "toLocaleLowerCase" not in FACES_JS


def test_kamera_panelden_cikinca_ve_pencere_gizlenince_birakilir():
    """Ürün kusuru (09-27 harita): HQ içinde başka panele geçince kamera + 2,5 sn tarama
    döngüsü sürüyordu; `visibilitychange`/`pagehide` dinlenmiyordu."""
    assert "visibilitychange" in FACES_JS and "pagehide" in FACES_JS
    intro = (KOK / "frontend" / "js" / "intro-sequences.js").read_text(encoding="utf-8")
    m = re.search(r"window\.switchHqTab\s*=\s*function.*?\n  \};", intro, re.S) or \
        re.search(r"function switchHqTab\(.*?\n  \}", intro, re.S)
    assert m and "YuzSekmesi" in m.group(0), "switchHqTab yüz panelini kapatmıyor"


def test_kur_her_acilista_yeniden_cizer():
    """`kur(false)` `kuruldu` bayrağıyla erken dönüyordu → liste ikinci açılışta bayattı."""
    assert "if (kuruldu && !zorla) return;" not in FACES_JS


def test_tarayici_diyalogu_ve_innerHTML_yok():
    kod = re.sub(r"/\*.*?\*/|//[^\n]*", "", FACES_JS, flags=re.S)
    assert "confirm(" not in kod and "alert(" not in kod
    assert ".innerHTML" not in kod, "metin textContent ile basılır (XSS kapısı)"

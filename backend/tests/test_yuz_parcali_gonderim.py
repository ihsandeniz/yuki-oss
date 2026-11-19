"""Parçalı kare gönderimi — toplama ile analizin üst üste koşması.

🔑 **Neden bu dosya var (2026-09-10):** yüzle girişte istemci 40 kareyi ~4 sn
boyunca topluyor, sonra tek pakette yolluyordu; sunucu o 4 sn boyunca boş
duruyor ve analiz (40 × ~150 ms) ancak son kareden SONRA başlıyordu. Kullanıcı
ikisinin **toplamını** bekliyordu. Dilimler toplanırken gönderilince analiz
toplamanın altına gizleniyor — canlı ölçüm: **12,90 sn → 8,96-9,43 sn**.

Hızlandırma bir **kimlik doğrulama yolunu** böldüğü için buradaki testler
davranış testi değil, **kapı testidir**. Ölçülen şey "parçalar birleşiyor mu"
değil, *"bölme bir kapıyı gevşetti mi"*:

  ① sıra — kırpma sayımı açık→kapalı→açık arayan bir durum makinesidir;
     parçalar yanlış sırada birleşirse sayı değişir
  ② tekrar oynatma — aynı parça sırası ikinci kez kabul edilirse saldırgan
     kırpma içeren dilimi çoğaltıp sayıyı şişirir
  ③ tavan — bir meydan okumaya sınırsız kare (= sınırsız model çıkarımı)
     biriktirilememeli; `verify`nin istek-başı 24 MB sınırı parçalara
     bölününce istek sayısıyla çarpılmamalı
  ④ tüketim — parça eklemek bir giriş DENEMESİ değildir, meydan okumayı
     tüketmemeli; ama tüketilmiş bir meydan okumaya da parça eklenememeli
  ⑤ sızıntı — birikim doğrulamayla birlikte atılmalı, sonraki denemeye
     karışmamalı
  ⑥ geri düşme — `parca` verilmezse eski davranış BİREBİR korunmalı
     (istemci bir dilimi yollayamazsa bu yola düşer)

⚠️ Model çalıştırılmıyor: `analiz_et` kurgulanır (`test_face_liveness.py` ile
aynı desen). Göz açıklığı yine **gerçek** `face_regions.goz_acikligi()` ile
sentetik landmark geometrisinden okunur.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.services import face_liveness
from app.services.face_multi_auth import KareAnalizi
from tests.test_face_liveness import _emb, _landmark

IP = "127.0.0.1"


def _analiz(aciklik: float, embedding: np.ndarray) -> KareAnalizi:
    return KareAnalizi(
        embedding=embedding,
        bbox={"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5},
        yuz_sayisi=1,
        landmark_106=_landmark(aciklik),
        yaw=None, pitch=None,
    )


@pytest.fixture(autouse=True)
def temiz():
    face_liveness._sifirla()
    yield
    face_liveness._sifirla()


@pytest.fixture
def kurgu(monkeypatch):
    """`analiz_et` → açıklık dizisi. Kare baytı `a<açıklık>#<sıra>` biçiminde.

    🔑 Analiz **kareden okunur**, sıraya konmuş bir kuyruktan değil: parçalı
    gönderimde çağrı sırası ile birleştirme sırası AYNI DEĞİLDİR ve kuyruk
    deseni tam da bu testin ölçmek istediği hatayı gizlerdi.
    """
    emb = _emb(1)

    async def sahte(veri: bytes):
        aciklik = float(veri.decode().split("#")[0][1:])
        if aciklik < 0:
            raise ValueError("Yüz bulunamadı.")
        return _analiz(aciklik, emb)

    from app.services import face_multi_auth
    monkeypatch.setattr(face_multi_auth, "analiz_et", sahte)
    return emb


_sayac = [0]


def kare(aciklik: float) -> bytes:
    """Verilen açıklığı üreten, baytça BENZERSİZ bir kare (kopya kapısı için)."""
    _sayac[0] += 1
    return f"a{aciklik}#{_sayac[0]}".encode()


async def meydan(kirpma: int | None = None) -> str:
    m = await face_liveness.olustur(IP)
    if kirpma is not None:
        face_liveness._meydanlar[m["challenge_id"]].kirpma = kirpma
    return m["challenge_id"]


# Sıraya duyarlı kurgu — kapalı kareler tek başına kırpma saymaz:
#   dogru sıra (0,1,2) → 3 kırpma · yanlış sıra (1,0,2) → 2 kırpma
_P0 = [0.35, 0.10, 0.35, 0.10, 0.35]
_P1 = [0.10, 0.10, 0.10, 0.10]
_P2 = [0.35, 0.36, 0.35]


def _dizi(acikliklar):
    return [kare(a) for a in acikliklar]


# ── ① sıra ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_parcalar_sirayla_birlestirilir(kurgu):
    """Parçalar VARIŞ sırasına göre değil, `parca` sırasına göre birleşmeli."""
    cid = await meydan(kirpma=3)
    p0, p1, p2 = _dizi(_P0), _dizi(_P1), _dizi(_P2)

    # Bilerek TERS varış: 1 önce, 0 sonra.
    assert (await face_liveness.parca_ekle(cid, IP, p1, 1))["ok"] is True
    assert (await face_liveness.parca_ekle(cid, IP, p0, 0))["ok"] is True

    s = await face_liveness.dogrula(cid, IP, p2, parca=2)
    assert s["ok"] is True, s.get("reason")
    assert s["blinks_detected"] == 3
    assert s["frames_used"] == len(_P0) + len(_P1) + len(_P2)


@pytest.mark.asyncio
async def test_yanlis_sira_kirpmayi_dusurur(kurgu):
    """Kurgunun kendi doğrulaması: sıra bozulursa sayı GERÇEKTEN düşüyor.

    Bu test olmadan yukarıdaki test, sıra hiç önemsizken de yeşil kalırdı.
    """
    cid = await meydan(kirpma=3)
    # Sıraları bilerek ters etiketle → birleşim (P1, P0, P2) olur.
    assert (await face_liveness.parca_ekle(cid, IP, _dizi(_P1), 0))["ok"] is True
    assert (await face_liveness.parca_ekle(cid, IP, _dizi(_P0), 1))["ok"] is True

    s = await face_liveness.dogrula(cid, IP, _dizi(_P2), parca=2)
    assert s["ok"] is False
    assert s["blinks_detected"] == 2


# ── ② tekrar oynatma ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_ayni_parca_sirasi_ikinci_kez_reddedilir(kurgu):
    cid = await meydan(kirpma=2)
    assert (await face_liveness.parca_ekle(cid, IP, _dizi(_P0), 0))["ok"] is True
    ikinci = await face_liveness.parca_ekle(cid, IP, _dizi(_P0), 0)
    assert ikinci["ok"] is False
    assert "zaten alındı" in ikinci["reason"]


# ── ③ tavan ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_kare_tavani_parcalara_bolerek_asilamaz(kurgu):
    cid = await meydan(kirpma=2)
    tavan = face_liveness.FACE_LIVENESS_MAX_FRAMES
    assert (await face_liveness.parca_ekle(cid, IP, _dizi([0.35] * tavan), 0))["ok"] is True
    tasan = await face_liveness.parca_ekle(cid, IP, _dizi([0.35]), 1)
    assert tasan["ok"] is False
    assert "tavan" in tasan["reason"].lower()


@pytest.mark.asyncio
async def test_bayt_tavani_parcalara_bolerek_asilamaz(kurgu, monkeypatch):
    monkeypatch.setattr(face_liveness, "MAKS_BIRIKIM_BAYT", 64)
    cid = await meydan(kirpma=2)
    buyuk = [b"a0.35#" + b"x" * 40 for _ in range(2)]
    assert (await face_liveness.parca_ekle(cid, IP, buyuk[:1], 0))["ok"] is True
    tasan = await face_liveness.parca_ekle(cid, IP, buyuk[1:], 1)
    assert tasan["ok"] is False
    assert "büyük" in tasan["reason"]


# ── ④ tüketim ───────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_parca_eklemek_meydan_okumayi_tuketmez(kurgu):
    """Parça eklemek bir giriş denemesi değildir."""
    cid = await meydan(kirpma=3)
    await face_liveness.parca_ekle(cid, IP, _dizi(_P0), 0)
    await face_liveness.parca_ekle(cid, IP, _dizi(_P1), 1)
    assert face_liveness._meydanlar[cid].kullanildi is False
    s = await face_liveness.dogrula(cid, IP, _dizi(_P2), parca=2)
    assert s["ok"] is True, s.get("reason")


@pytest.mark.asyncio
async def test_tuketilmis_meydana_parca_eklenemez(kurgu):
    cid = await meydan(kirpma=3)
    await face_liveness.parca_ekle(cid, IP, _dizi(_P0), 0)
    await face_liveness.parca_ekle(cid, IP, _dizi(_P1), 1)
    await face_liveness.dogrula(cid, IP, _dizi(_P2), parca=2)

    s = await face_liveness.parca_ekle(cid, IP, _dizi(_P0), 5)
    assert s["ok"] is False


@pytest.mark.asyncio
async def test_baska_istemci_parca_ekleyemez(kurgu):
    cid = await meydan(kirpma=2)
    s = await face_liveness.parca_ekle(cid, "10.0.0.9", _dizi(_P0), 0)
    assert s["ok"] is False
    assert "başka bir istemciye" in s["reason"]


@pytest.mark.asyncio
async def test_suresi_dolmus_meydana_parca_eklenemez(kurgu, monkeypatch):
    cid = await meydan(kirpma=2)
    monkeypatch.setattr(face_liveness, "FACE_LIVENESS_TTL", -1.0)
    s = await face_liveness.parca_ekle(cid, IP, _dizi(_P0), 0)
    assert s["ok"] is False
    assert "süresi doldu" in s["reason"]


# ── ⑤ sızıntı ───────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_birikim_dogrulamadan_sonra_atilir(kurgu):
    """Kalan birikim, SONRAKİ denemenin kırpmalarına karışırdı."""
    cid = await meydan(kirpma=3)
    await face_liveness.parca_ekle(cid, IP, _dizi(_P0), 0)
    await face_liveness.parca_ekle(cid, IP, _dizi(_P1), 1)
    await face_liveness.dogrula(cid, IP, _dizi(_P2), parca=2)
    m = face_liveness._meydanlar.get(cid)
    assert m is None or (m.parcalar == {} and m.biriken == 0)


# ── ⑥ geri düşme (eski yol) ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_parcasiz_dogrulama_birikimi_yok_sayar(kurgu):
    """`parca` yoksa DAVRANIŞ ESKİSİ: birikim atılır, yalnız gelen kareler bakılır.

    İstemci bir dilimi yollayamazsa bu yola düşer. Yarım birikim sessizce
    karışsaydı, sebebi hiçbir yerde yazmayan bir canlılık reddi üretirdi.
    """
    cid = await meydan(kirpma=3)
    # Sunucuda yarım birikim var…
    await face_liveness.parca_ekle(cid, IP, _dizi(_P0), 0)
    # …ama istemci `parca` göndermeden TÜM diziyi yolluyor.
    tam = _dizi(_P0 + _P1 + _P2)
    s = await face_liveness.dogrula(cid, IP, tam)
    assert s["ok"] is True, s.get("reason")
    assert s["frames_used"] == len(tam), "birikim karışmamalı"


# ── yüzsüz kareler ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_parcadaki_yuzsuz_kareler_sayiliyor(kurgu):
    """Yüzsüz kare parçada da kayda geçmeli — yoksa oran kapısı yanılırdı."""
    cid = await meydan(kirpma=3)
    # Parça 0'ın yarısı yüzsüz (açıklık < 0 → analiz ValueError verir).
    await face_liveness.parca_ekle(cid, IP, _dizi([-1.0] * 6 + _P0), 0)
    await face_liveness.parca_ekle(cid, IP, _dizi(_P1), 1)
    s = await face_liveness.dogrula(cid, IP, _dizi(_P2), parca=2)
    assert s["ok"] is False
    assert "yüz görünmüyor" in s["reason"]


# ── kapı SIRASI: ucuz kapı modelden ÖNCE ────────────────────────────────────
@pytest.mark.asyncio
async def test_kopya_kareler_model_calismadan_reddedilir(monkeypatch):
    """Kopya kare kapısı bayt özetiyle koşar — 40 kez model çalıştırmadan.

    🔴 Bu test bir REGRESYONDAN doğdu: parçalı gönderim eklenirken birleştirme
    analizin önüne alınmış, kopya kapısı analizden SONRAYA düşmüştü. "Aynı
    fotoğrafı 40 kez gönder" saldırısı reddedilmeden önce tam bedelini
    ödetiyordu. Kapının varlığı yetmez, **sırası** da kapıdır.
    """
    cagri = []

    async def sayan(veri: bytes):
        cagri.append(veri)
        raise AssertionError("kopya kapısından önce model çalıştı")

    from app.services import face_multi_auth
    monkeypatch.setattr(face_multi_auth, "analiz_et", sayan)

    cid = await meydan(kirpma=2)
    ayni = [b"ayni-kare"] * 20
    s = await face_liveness.dogrula(cid, IP, ayni)
    assert s["ok"] is False
    assert "kopyası" in s["reason"]
    assert cagri == [], "ucuz kapı modelden önce koşmadı"


# ── uç seviyesi: açık uç yalnız giriş MÜMKÜNKEN açık olmalı ─────────────────
# `/api/face/frames` kimlik doğrulamasından muaf (`_SKIP_PATHS`). Yüzle giriş
# hiç mümkün değilken (kilit kurulu değil / kayıtlı sahip yok) açık kalması,
# hiçbir girişe yol açmayan bir kanalı bedavaya açmak olurdu. Kapı `/verify`
# ile AYNI yerde durmalı — ikisi ayrışırsa açık olan yüzey sessizce genişler.
def _istemci():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import face_api
    app = FastAPI()
    app.state.limiter = face_api.limiter
    app.include_router(face_api.router)
    return TestClient(app)


_JPEG = b"\xff\xd8\xff" + b"\x00" * 64


def test_frames_kilit_kurulu_degilse_kapali(monkeypatch):
    from app.api import face_api
    from app.services import app_lock

    monkeypatch.setattr(face_api, "AUTH_TOKEN", "", raising=False)
    monkeypatch.setattr("app.config.AUTH_TOKEN", "", raising=False)
    monkeypatch.setattr(app_lock, "kurulu", lambda: False)

    r = _istemci().post("/api/face/frames",
                        data={"challenge_id": "x", "parca": "0"},
                        files=[("files", ("k.jpg", _JPEG, "image/jpeg"))])
    assert r.status_code == 503


def test_frames_kayitli_yuz_yoksa_kapali(monkeypatch):
    from app.services import app_lock, face_multi_auth

    monkeypatch.setattr(app_lock, "kurulu", lambda: True)
    monkeypatch.setattr(face_multi_auth, "owner_enrolled", lambda: False)

    r = _istemci().post("/api/face/frames",
                        data={"challenge_id": "x", "parca": "0"},
                        files=[("files", ("k.jpg", _JPEG, "image/jpeg"))])
    assert r.status_code == 404

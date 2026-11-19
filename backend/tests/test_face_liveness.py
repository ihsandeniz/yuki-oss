"""Canlılık (liveness) kapıları — yüzle girişin güvenlik yüzeyi.

Bu dosya bir güvenlik testidir, bir davranış testi değil. Ölçtüğü şey
"özellik çalışıyor mu" değil, **saldırı reddediliyor mu**.

Kapsanan saldırılar:
  ① aynı fotoğrafı N kez göndermek
  ② donuk (hiç oynamayan) bir görüntü dizisi
  ③ istenenden az kırpma
  ④ 🔑 kimlik değiştirme: bir kısım karede saldırganın canlı yüzü (kırpar),
     bir kısmında sahibin fotoğrafı (tanınır) — ikisi ayrı ayrı geçerdi
  ⑤ meydan okumayı yeniden kullanmak / süresi geçmişini kullanmak /
     başka bir istemcinin meydan okumasını kullanmak
  ⑥ landmark üretilemediğinde kontrolü sessizce atlamak

⚠️ Model çalıştırılmıyor: `analiz_et` yerine kurgulanmış `KareAnalizi` verilir.
Ama **göz açıklığı gerçek `face_regions.goz_acikligi()` ile hesaplanır** —
landmark geometrisi sentetik olarak kurulur. Yani ölçülen şey bizim eşik/durum
makinemizdir, sahte bir açıklık sayısı değil.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.services import face_liveness, face_regions
from app.services.face_multi_auth import KareAnalizi

IP = "127.0.0.1"


# ── sentetik landmark: istenen göz açıklığını ÜRETEN geometri ───────────────
def _landmark(aciklik: float) -> np.ndarray:
    """106 nokta üret; `goz_acikligi()` bu diziden tam `aciklik` okusun.

    `goz_acikligi` gözün köşe eksenini (`*_GOZ_KOSE`) referans alır, kalan göz
    noktalarını o eksene DİK izdüşürür ve yayılımı köşe mesafesine böler.
    Köşeleri (0,0)-(10,0) koyarsak bölen 10 olur; kalan noktaları ±(aciklik*10)/2
    koyunca oran tam `aciklik` çıkar.
    """
    L = np.zeros((face_regions.TOPLAM_NOKTA, 2), dtype=float)
    yari = aciklik * 10.0 / 2.0
    for kose_idx, goz_idx in ((face_regions.SAG_GOZ_KOSE, face_regions.SAG_GOZ),
                              (face_regions.SOL_GOZ_KOSE, face_regions.SOL_GOZ)):
        L[kose_idx[0]] = (0.0, 0.0)
        L[kose_idx[1]] = (10.0, 0.0)
        digerleri = [i for i in goz_idx if i not in kose_idx]
        for sira, i in enumerate(digerleri):
            L[i] = (5.0, yari if sira % 2 == 0 else -yari)
    return L


def _emb(tohum: int) -> np.ndarray:
    rng = np.random.default_rng(tohum)
    v = rng.standard_normal(512).astype(np.float32)
    return v / np.linalg.norm(v)


def _analiz(aciklik: float, embedding: np.ndarray, landmark: bool = True) -> KareAnalizi:
    return KareAnalizi(
        embedding=embedding,
        bbox={"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5},
        yuz_sayisi=1,
        landmark_106=_landmark(aciklik) if landmark else None,
        yaw=None, pitch=None,      # poz düzeltmesi devre dışı → çarpan 1.0
    )


def test_sentetik_landmark_gercekten_istenen_acikligi_veriyor():
    """Kurgu doğrulaması: aşağıdaki tüm testler buna yaslanıyor.

    Bu test olmasaydı, geometriyi yanlış kurmuş ve bütün canlılık testlerini
    sessizce anlamsızlaştırmış olabilirdik.
    """
    for hedef in (0.05, 0.12, 0.30, 0.42):
        olculen = face_regions.goz_acikligi(_landmark(hedef), "sag")
        assert olculen == pytest.approx(hedef, abs=1e-9)


# ── kırpma sayacı (durum makinesi) ──────────────────────────────────────────
@pytest.mark.parametrize("dizi,beklenen", [
    ([0.35, 0.35, 0.35], 0),                                   # hiç kırpma yok
    ([0.35, 0.10, 0.35], 1),                                   # tek kırpma
    ([0.35, 0.10, 0.35, 0.09, 0.40], 2),                       # iki kırpma
    ([0.35, 0.10, 0.11, 0.09, 0.35], 1),                       # uzun kapalı = TEK kırpma
    ([0.10, 0.35], 0),                                         # kapalı başlarsa sayılmaz
    ([0.35, 0.20, 0.35], 0),                                   # 0.20 kapalı sayılmaz (>0.18)
    ([0.35, 0.10, 0.20, 0.10, 0.35], 1),                       # 0.20 açık da sayılmaz (<0.225)
])
def test_kirpma_sayaci(dizi, beklenen):
    assert face_liveness._kirpma_say(dizi) == beklenen


def test_histerezis_gurultuyu_yutar():
    """Eşiğin tam üstünde titreşen gürültü sahte kırpma ÜRETMEMELİ.

    Tek eşikli bir sayaç bu dizide 3 kırpma sayardı; histerezis 0 sayar.
    """
    gurultulu = [0.179, 0.181, 0.179, 0.181, 0.179, 0.181]
    assert face_liveness._kirpma_say(gurultulu) == 0


# ── meydan okuma ────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def temiz():
    face_liveness._sifirla()
    yield
    face_liveness._sifirla()


async def _meydan():
    return await face_liveness.olustur(IP)


@pytest.mark.asyncio
async def test_meydan_okuma_uretiliyor():
    m = await _meydan()
    assert m["action"] == "blink"
    assert m["blinks"] in face_liveness.KIRPMA_SECENEKLERI
    assert len(m["challenge_id"]) >= 16


@pytest.mark.asyncio
async def test_meydan_okuma_kimligi_tahmin_edilemez():
    kimlikler = {(await _meydan())["challenge_id"] for _ in range(20)}
    assert len(kimlikler) == 20


@pytest.mark.asyncio
async def test_meydansiz_dogrulama_reddedilir():
    s = await face_liveness.dogrula(None, IP, [b"x"] * 12)
    assert s["ok"] is False


@pytest.mark.asyncio
async def test_bilinmeyen_meydan_reddedilir():
    s = await face_liveness.dogrula("uydurma-kimlik", IP, [b"x"] * 12)
    assert s["ok"] is False
    assert "bulunamadı" in s["reason"]


@pytest.mark.asyncio
async def test_suresi_dolmus_meydan_reddedilir(monkeypatch):
    m = await _meydan()
    monkeypatch.setattr(face_liveness, "FACE_LIVENESS_TTL", -1.0)
    s = await face_liveness.dogrula(m["challenge_id"], IP, [b"x"] * 12)
    assert s["ok"] is False
    assert "süresi doldu" in s["reason"]


@pytest.mark.asyncio
async def test_baska_istemcinin_meydani_reddedilir():
    m = await _meydan()
    s = await face_liveness.dogrula(m["challenge_id"], "10.0.0.9", [b"x"] * 12)
    assert s["ok"] is False
    assert "başka bir istemciye" in s["reason"]


@pytest.mark.asyncio
async def test_meydan_tek_kullanimlik(monkeypatch, _kurgu):
    """Aynı meydan okumayla ikinci deneme = kaydedilmiş dizinin tekrar oynatılması."""
    m = await _meydan()
    analizler = _gecerli_dizi(m["blinks"])
    _kurgu(analizler)
    kareler = [f"k{i}".encode() for i in range(len(analizler))]

    ilk = await face_liveness.dogrula(m["challenge_id"], IP, kareler)
    assert ilk["ok"] is True

    ikinci = await face_liveness.dogrula(m["challenge_id"], IP, kareler)
    assert ikinci["ok"] is False


# ── dizi kapıları ───────────────────────────────────────────────────────────
def _gecerli_dizi(kirpma: int, kimlik_tohumu: int = 1) -> list[KareAnalizi]:
    """Açık-kapalı-açık örüntüsüyle `kirpma` kez kırpan, tek kişilik dizi."""
    emb = _emb(kimlik_tohumu)
    acikliklar = [0.35, 0.36]
    for _ in range(kirpma):
        acikliklar += [0.35, 0.10, 0.35]
    acikliklar += [0.34, 0.36, 0.35]
    return [_analiz(a, emb) for a in acikliklar]


@pytest.fixture
def _kurgu(monkeypatch):
    """`analiz_et`'i sıraya konmuş analizlerle değiştir."""
    def kur(analizler: list[KareAnalizi]):
        sira = list(analizler)

        async def sahte(veri: bytes):
            return sira.pop(0)

        from app.services import face_multi_auth
        monkeypatch.setattr(face_multi_auth, "analiz_et", sahte)
        return sira
    return kur


@pytest.mark.asyncio
async def test_gecerli_dizi_gecer(_kurgu):
    m = await _meydan()
    analizler = _gecerli_dizi(m["blinks"])
    _kurgu(analizler)
    s = await face_liveness.dogrula(m["challenge_id"], IP,
                                    [f"k{i}".encode() for i in range(len(analizler))])
    assert s["ok"] is True, s.get("reason")
    assert s["blinks_detected"] >= m["blinks"]
    assert "video" in s["limits"], "sınır bilgisi veriyle taşınmalı"


@pytest.mark.asyncio
async def test_az_kare_reddedilir(_kurgu):
    m = await _meydan()
    s = await face_liveness.dogrula(m["challenge_id"], IP, [b"a", b"b", b"c"])
    assert s["ok"] is False
    assert "Yetersiz kare" in s["reason"]


@pytest.mark.asyncio
async def test_ayni_fotograf_tekrar_reddedilir(_kurgu):
    """① En basit saldırı: tek fotoğrafı N kez göndermek."""
    m = await _meydan()
    _kurgu(_gecerli_dizi(m["blinks"]))
    s = await face_liveness.dogrula(m["challenge_id"], IP, [b"ayni-kare"] * 14)
    assert s["ok"] is False
    assert "kopyası" in s["reason"]


@pytest.mark.asyncio
async def test_donuk_goruntu_reddedilir(_kurgu):
    """② Kareler farklı ama gözler hiç oynamıyor — fotoğrafı hafifçe oynatmak."""
    m = await _meydan()
    emb = _emb(1)
    _kurgu([_analiz(0.35, emb) for _ in range(14)])
    s = await face_liveness.dogrula(m["challenge_id"], IP,
                                    [f"k{i}".encode() for i in range(14)])
    assert s["ok"] is False
    assert "hareket yok" in s["reason"]


@pytest.mark.asyncio
async def test_yetersiz_kirpma_reddedilir(_kurgu):
    """③ İstenenden az kırpma — rastgele sayının tüm anlamı bu."""
    m = await _meydan()
    if m["blinks"] <= 1:
        pytest.skip("meydan okuma 1 kırpma istedi")
    analizler = _gecerli_dizi(1)        # yalnız 1 kırpma
    _kurgu(analizler)
    s = await face_liveness.dogrula(m["challenge_id"], IP,
                                    [f"k{i}".encode() for i in range(len(analizler))])
    assert s["ok"] is False
    assert s["blinks_detected"] < m["blinks"]


@pytest.mark.asyncio
async def test_kimlik_degistirme_reddedilir(_kurgu):
    """🔑 ④ EN KRİTİK: saldırgan kendi yüzüyle kırpar, sahibin fotoğrafını gösterir.

    Bu kapı olmasaydı canlılık saldırganın kırpmasından, tanıma da sahibin
    fotoğrafından geçer ve giriş açılırdı. İki kontrol ayrı ayrı "doğru"
    davranırken sistem bütün olarak kırılırdı.
    """
    m = await _meydan()
    saldirgan, sahip = _emb(1), _emb(999)

    analizler = [_analiz(0.35, saldirgan), _analiz(0.36, saldirgan)]
    for _ in range(max(m["blinks"], 3)):
        analizler += [_analiz(0.35, saldirgan), _analiz(0.10, saldirgan),
                      _analiz(0.35, saldirgan)]
    analizler += [_analiz(0.35, sahip)] * 3          # ← sahibin fotoğrafı
    _kurgu(analizler)

    s = await face_liveness.dogrula(m["challenge_id"], IP,
                                    [f"k{i}".encode() for i in range(len(analizler))])
    assert s["ok"] is False
    assert "birden fazla kişi" in s["reason"]


@pytest.mark.asyncio
async def test_landmark_yoksa_gecmez(_kurgu):
    """⑥ Ölçemiyorsak "geçti" DEMEYİZ — en tehlikeli başarısızlık biçimi budur."""
    m = await _meydan()
    emb = _emb(1)
    _kurgu([_analiz(0.35, emb, landmark=False) for _ in range(14)])
    s = await face_liveness.dogrula(m["challenge_id"], IP,
                                    [f"k{i}".encode() for i in range(14)])
    assert s["ok"] is False
    assert "ölçülemedi" in s["reason"]


@pytest.mark.asyncio
async def test_yuzsuz_kareler_cogunluktaysa_reddedilir(monkeypatch):
    m = await _meydan()

    async def hep_yuzsuz(veri: bytes):
        raise ValueError("Yüz bulunamadı.")

    from app.services import face_multi_auth
    monkeypatch.setattr(face_multi_auth, "analiz_et", hep_yuzsuz)
    s = await face_liveness.dogrula(m["challenge_id"], IP,
                                    [f"k{i}".encode() for i in range(14)])
    assert s["ok"] is False
    assert "yüz görünmüyor" in s["reason"]


@pytest.mark.asyncio
async def test_gecen_dizi_analizleri_geri_veriyor(_kurgu):
    """Tanıma, canlılığın ölçtüğü AYNI karelerden yapılmalı.

    Ayrı bir kare için ayrı bir analiz koşulsaydı, canlılığı geçen yüz ile
    tanınan yüzün aynı olduğu garanti edilemezdi.
    """
    m = await _meydan()
    analizler = _gecerli_dizi(m["blinks"])
    _kurgu(analizler)
    s = await face_liveness.dogrula(m["challenge_id"], IP,
                                    [f"k{i}".encode() for i in range(len(analizler))])
    assert s["ok"] is True
    assert len(s["_analizler"]) == len(analizler)

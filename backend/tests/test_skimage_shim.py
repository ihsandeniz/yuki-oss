"""`scripts/pydeps-shim/skimage` gerçek scikit-image ile SAYISAL olarak aynı mı?

🔑 Neden bu testin ölçütü sertçe sayısal:

Shim, `insightface`'in yüz hizalama matrisini üretiyor. Yanlış ama makul bir
matris **hata vermez** — `cv2.warpAffine` çalışır, model çıktı üretir, sistem
yeşil görünür ve yalnız *tanıma doğruluğu* sessizce düşer. Bu, ürünün en pahalı
arıza sınıfı: ölçülmediği sürece görünmez. O yüzden ölçüt "benzer sonuç" değil,
`atol=1e-12` içinde **aynı matris**.

📏 Altın değerler gerçek `scikit-image 0.26.0` ile üretildi
(`scripts/pydeps-shim/altin-uret.py` → `tests/veri/skimage-shim-altin.json`).
Böylece bu test, scikit-image **kurulu olmayan** ortamda (ürün venv'i, CI)
gerçek kütüphanenin davranışını zorlayabiliyor.

⚠️ Üreticinin ilk koşusu kendi shim'ini import edip anlamsız altın değer
üretmişti ("üreten = ölçen"). Aşağıdaki `test_altin_gercek_skimageden_uretildi`
o kapıyı kalıcı hâle getirir: altın dosyası shim'in kendisinden üretilmişse
tüm takım kırmızı yanar.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

SHIM_KOK = Path(__file__).resolve().parents[2] / "scripts" / "pydeps-shim"
ALTIN = Path(__file__).resolve().parent / "veri" / "skimage-shim-altin.json"

# insightface/utils/face_align.py:6 ile birebir
ARCFACE_DST = np.array(
    [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
     [41.5493, 92.3655], [70.7299, 92.2041]],
    dtype=np.float32)


@pytest.fixture(scope="module")
def trans():
    """Shim'in `transform` modülü.

    ⚠️ Ortamda GERÇEK scikit-image varsa (geliştirici makinesi) o zaten
    import edilmiş olabilir; bu test onu değil **shim'i** ölçmek zorunda.
    Bu yüzden shim kökü `sys.path`'in BAŞINA konur ve önceden yüklenmiş
    `skimage` modülleri düşürülür. Sürüm damgası da ayrıca doğrulanır —
    yanlış modülü ölçmek, ölçmemekten kötüdür.
    """
    for ad in [m for m in sys.modules if m == "skimage" or m.startswith("skimage.")]:
        del sys.modules[ad]
    sys.path.insert(0, str(SHIM_KOK))
    try:
        import skimage
        from skimage import transform as _t
        assert "yuki-shim" in skimage.__version__, (
            f"Shim yerine başka bir skimage ölçülüyor: {skimage.__version__}"
        )
        yield _t
    finally:
        sys.path.remove(str(SHIM_KOK))
        for ad in [m for m in sys.modules if m == "skimage" or m.startswith("skimage.")]:
            del sys.modules[ad]


@pytest.fixture(scope="module")
def altin() -> dict:
    assert ALTIN.exists(), (
        f"Altın değer dosyası yok: {ALTIN}\n"
        "Üret: ../AliceAi/backend/venv/bin/python scripts/pydeps-shim/altin-uret.py"
    )
    with open(ALTIN, encoding="utf-8") as f:
        return json.load(f)


def _esit(gercek, beklenen, ad: str) -> None:
    """`nan` içeren dejenere matrisler de dâhil, birebir karşılaştır."""
    g = np.asarray(gercek, dtype=np.float64)
    b = np.asarray(beklenen, dtype=np.float64)
    assert g.shape == b.shape, f"{ad}: biçim {g.shape} != {b.shape}"
    # nan konumları aynı olmalı — biri nan öbürü sayı ise sessiz sapma demektir
    assert np.array_equal(np.isnan(g), np.isnan(b)), (
        f"{ad}: nan yerleşimi farklı\nshim:\n{g}\naltın:\n{b}"
    )
    maske = ~np.isnan(b)
    np.testing.assert_allclose(
        g[maske], b[maske], rtol=0.0, atol=1e-12,
        err_msg=f"{ad}: matris sapması (rtol=0, atol=1e-12)",
    )


# ── kapı: altın değerler gerçekten gerçek kütüphaneden mi geldi ──────────
def test_altin_gercek_skimageden_uretildi(altin):
    surum = altin.get("skimage_surumu", "")
    assert surum, "altın dosyasında skimage sürümü yazmıyor"
    assert "yuki-shim" not in surum, (
        f"🔴 Altın değerler SHIM'in kendisinden üretilmiş ({surum}) — bu test "
        f"hiçbir şey ölçmez. `altin-uret.py`'yi scikit-image kurulu bir python "
        f"ile yeniden koş."
    )


def test_altin_dosyasi_dolu(altin):
    assert len(altin["estimate"]) >= 10
    assert len(altin["kurucu"]) >= 5
    assert len(altin["bilesim"]) >= 3


# ── 1) estimate: ArcFace hizalama yolu (arcface_onnx.py → norm_crop) ─────
def test_estimate_altin_degerlerle_ayni(trans, altin):
    for vaka in altin["estimate"]:
        tform = trans.SimilarityTransform()
        # ⚠️ İKİ GİRDİ DE float32 — keyfi değil, `insightface`'in fiilen verdiği
        # dtype bu (`kps` float32, `arcface_dst` float32). Umeyama hesabı girdi
        # dtype'ında koşar; buraya float64 verilirse sonuç ~5e-6 kayar ve test
        # shim'i değil kendi varsayımını ölçmüş olur (ilk koşuda tam bu oldu).
        tform.estimate(np.array(vaka["lmk"], dtype=np.float32),
                       np.array(vaka["dst"], dtype=np.float32))
        _esit(tform.params, vaka["beklenen_params"], f"estimate/{vaka['ad']}")


def test_estimate_dejenere_girdide_false_doner(trans):
    """Dejenere girdi `nan` üretir; shim bunu **bildirir**.

    Gerçek scikit-image dönüş değerine bakmaz-gibi davranır (deprecated API),
    `insightface` de bakmıyor. Ama `nan` bir matrisle `warpAffine` boş kare
    üretir — o sessizliği hiç değilse ölçülebilir kılıyoruz.
    """
    tform = trans.SimilarityTransform()
    ok = tform.estimate(np.array([[7.0, 7.0]] * 5, dtype=np.float32),
                        ARCFACE_DST.astype(np.float64))
    assert ok is False
    assert np.isnan(tform.params).any()

    saglikli = trans.SimilarityTransform()
    ok2 = saglikli.estimate(
        np.array([[120.0, 150.0], [200.0, 150.0], [160.0, 195.0],
                  [128.0, 240.0], [192.0, 240.0]], dtype=np.float32),
        ARCFACE_DST.astype(np.float64))
    assert ok2 is True
    assert np.isfinite(saglikli.params).all()


# ── 2) kurucu argümanları ────────────────────────────────────────────────
def test_kurucu_altin_degerlerle_ayni(trans, altin):
    for vaka in altin["kurucu"]:
        kw = dict(vaka["kwargs"])
        if "translation" in kw:
            kw["translation"] = tuple(kw["translation"])
        t = trans.SimilarityTransform(**kw)
        _esit(t.params, vaka["beklenen_params"], f"kurucu/{vaka['ad']}")


# ── 3) bileşim: landmark + attribute yolu (face_align.transform) ─────────
def test_bilesim_altin_degerlerle_ayni(trans, altin):
    for vaka in altin["bilesim"]:
        center = vaka["center"]
        output_size = vaka["output_size"]
        scale_ratio = vaka["scale"]
        rot = float(vaka["rotation"]) * np.pi / 180.0

        # face_align.transform() ile BİREBİR aynı sıra
        t1 = trans.SimilarityTransform(scale=scale_ratio)
        cx = center[0] * scale_ratio
        cy = center[1] * scale_ratio
        t2 = trans.SimilarityTransform(translation=(-1 * cx, -1 * cy))
        t3 = trans.SimilarityTransform(rotation=rot)
        t4 = trans.SimilarityTransform(translation=(output_size / 2, output_size / 2))
        t = t1 + t2 + t3 + t4
        _esit(t.params, vaka["beklenen_params"], f"bilesim/{vaka['ad']}")


def test_bilesim_sirasi_onemli(trans):
    """`(a + b) == b.params @ a.params` — ters çevrilirse yüz kırpması bozulur.

    Bu, shim'in en kolay yanlış yazılabilecek satırı: matris çarpımı değişmeli
    değildir ve iki sıra da "çalışır" görünür. Testi ayrı tutuyoruz ki bileşim
    altın değerleri bir gün yeniden üretilirken bu kural sessizce kaymasın.
    """
    a = trans.SimilarityTransform(scale=2.0)
    b = trans.SimilarityTransform(translation=(10.0, 20.0))
    birlesik = a + b
    np.testing.assert_allclose(birlesik.params, b.params @ a.params, rtol=0, atol=1e-15)
    # ters sıra FARKLI olmalı — aksi hâlde test hiçbir şey ayırt etmiyordur
    assert not np.allclose(birlesik.params, a.params @ b.params)


# ── 4) insightface'in fiilen çağırdığı yol, uçtan uca ───────────────────
def test_estimate_norm_face_align_ile_ayni_sonuc(trans, altin):
    """`face_align.estimate_norm`'un tamamını shim'le koş.

    Amaç: shim'i tek tek çağrılarla değil, **insightface'in yazdığı sırayla**
    zorlamak. `image_size` dalları (112'nin katı / 128'in katı) da buradan geçer.
    """
    vakalar = {v["ad"]: v for v in altin["estimate"]}
    for ad in ("ortalanmis_yuz", "boyut_256_128kati", "boyut_224_112kati"):
        vaka = vakalar[ad]
        image_size = vaka["image_size"]
        if image_size % 112 == 0:
            ratio = float(image_size) / 112.0
            diff_x = 0.0
        else:
            ratio = float(image_size) / 128.0
            diff_x = 8.0 * ratio
        dst = ARCFACE_DST * ratio
        dst[:, 0] += diff_x

        tform = trans.SimilarityTransform()
        tform.estimate(np.array(vaka["lmk"], dtype=np.float32), dst)
        M = tform.params[0:2, :]
        assert M.shape == (2, 3)
        _esit(tform.params, vaka["beklenen_params"], f"estimate_norm/{ad}")


# ── 5) sağlanmayan yüzey: sessiz değil, adıyla söylüyor ─────────────────
def test_saglanmayan_alt_modul_teshis_edilebilir_hata_verir(trans):
    import skimage
    with pytest.raises(ImportError) as e:
        _ = skimage.io
    mesaj = str(e.value)
    assert "skimage.io" in mesaj
    assert "pydeps-shim" in mesaj, "hata mesajı nereye bakılacağını söylemeli"


def test_desteklenmeyen_boyut_reddedilir(trans):
    with pytest.raises(NotImplementedError):
        trans.SimilarityTransform(dimensionality=3)


def test_matris_ve_parametre_birlikte_verilemez(trans):
    with pytest.raises(ValueError):
        trans.SimilarityTransform(matrix=np.eye(3), scale=2.0)


def test_bos_kurucu_birim_matris(trans):
    np.testing.assert_array_equal(trans.SimilarityTransform().params, np.eye(3))


def test_yanlis_turle_bilesim_reddedilir(trans):
    with pytest.raises(TypeError):
        _ = trans.SimilarityTransform() + math.pi

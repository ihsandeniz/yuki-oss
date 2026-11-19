#!/usr/bin/env python3
"""Altın değerleri **gerçek** scikit-image ile üret.

Shim'in testi kendi kendini doğrulayamaz — "üreten = ölçen" tuzağı. Bu script
gerçek `scikit-image`'i kullanarak beklenen matrisleri hesaplar ve JSON'a yazar;
`backend/tests/test_skimage_shim.py` o dosyaya karşı ölçer. Böylece test, CI'da
scikit-image kurulu OLMADAN da gerçek kütüphanenin davranışını zorlar.

Kullanım (scikit-image kurulu bir python gerekir — ürün venv'inde YOKTUR):

    ../AliceAi/backend/venv/bin/python scripts/pydeps-shim/altin-uret.py

⚠️ **Ne zaman yeniden koşulur:** `insightface` sürümü değişip `skimage`
kullanımı genişlediğinde, ya da scikit-image'in `_umeyama`'sı değiştiğinde.
Üretilen dosyanın başında hangi sürümle üretildiği yazar — testler onu rapor
eder, böylece "hangi gerçeğe karşı ölçüyoruz" sorusu kayıt altındadır.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

# 🔴 ÖNCE BU, sonra `import skimage`.
#
# Bu script `scripts/pydeps-shim/` içinde durur ve shim de tam orada
# (`./skimage/`). Python bir script'i koşarken **script'in kendi dizinini
# `sys.path[0]` yapar** → süslü hiçbir şey yapmadan `import skimage` SHIM'i
# bulur ve altın değerler ölçülecek şeyin kendisinden üretilir.
#
# Bu satırlar bir temkin değil, **yaşanmış bir hatanın kapısı**: ilk koşuda
# tam bu oldu ve çıktı "scikit-image 0.0.0+yuki-shim" dedi. Yakalanmasının
# tek sebebi sürümün rapora yazılıyor olmasıydı; yazılmasaydı 25 vakalık
# tamamen anlamsız bir altın dosyası testleri sonsuza dek yeşil tutardı.
_BURASI = str(Path(__file__).resolve().parent)
sys.path[:] = [p for p in sys.path
               if os.path.abspath(p or os.getcwd()) != _BURASI]

import numpy as np  # noqa: E402
import skimage  # noqa: E402
from skimage import transform as trans  # noqa: E402

if "yuki-shim" in skimage.__version__:
    sys.exit(
        "✗ Gerçek scikit-image yerine SHIM import edildi — altın değer üretilemez.\n"
        "  scikit-image kurulu bir python ile koş (ürün venv'inde YOKTUR):\n"
        "    ../AliceAi/backend/venv/bin/python scripts/pydeps-shim/altin-uret.py"
    )

HEDEF = Path(__file__).resolve().parents[2] / "backend" / "tests" / "veri" / "skimage-shim-altin.json"

# insightface/utils/face_align.py:6 — ArcFace'in referans 5 noktası
ARCFACE_DST = np.array(
    [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
     [41.5493, 92.3655], [70.7299, 92.2041]],
    dtype=np.float32)


def _m(a) -> list:
    """Matrisi tam çift duyarlıkla JSON'a yaz (repr üzerinden değil, float ile)."""
    return np.asarray(a, dtype=np.float64).tolist()


def estimate_vakalari() -> list[dict]:
    """`tform.estimate(lmk, dst)` — arcface hizalama yolu.

    Vakalar gerçek hayatta görülen çeşitliliği kapsar: ortalanmış yüz, küçük
    uzaktaki yüz, yana dönük yüz, eğik (roll) yüz, kadraj dışına taşan yüz.
    Tek bir "güzel" vaka test etmek, kestirimin dejenere davranışını gizler.
    """
    rng = np.random.default_rng(20260905)
    vakalar = []

    ornekler = {
        # (ad, 5×2 landmark: sol göz, sağ göz, burun, sol ağız, sağ ağız)
        "ortalanmis_yuz": [[120.0, 150.0], [200.0, 150.0], [160.0, 195.0],
                           [128.0, 240.0], [192.0, 240.0]],
        "kucuk_uzak_yuz": [[302.0, 210.0], [322.0, 209.0], [312.0, 221.0],
                           [304.0, 233.0], [320.0, 233.0]],
        "yana_donuk": [[110.0, 148.0], [178.0, 156.0], [131.0, 196.0],
                       [116.0, 238.0], [172.0, 245.0]],
        "egik_roll_25derece": [[118.0, 132.0], [190.0, 168.0], [146.0, 190.0],
                               [110.0, 228.0], [172.0, 262.0]],
        "kadraj_disi_negatif": [[-14.0, 90.0], [64.0, 88.0], [20.0, 136.0],
                                [-6.0, 182.0], [58.0, 180.0]],
    }
    for ad, lmk in ornekler.items():
        vakalar.append({"ad": ad, "lmk": lmk, "image_size": 112})

    # 112'nin katı olmayan ama 128'in katı olan boyut → face_align'da diff_x dalı
    vakalar.append({"ad": "boyut_256_128kati", "lmk": ornekler["ortalanmis_yuz"], "image_size": 256})
    vakalar.append({"ad": "boyut_224_112kati", "lmk": ornekler["ortalanmis_yuz"], "image_size": 224})

    # Rastgele ama tohumlu — insan seçiminin kaçırdığı geometrileri yakalar
    for i in range(5):
        lmk = (rng.random((5, 2)) * 300.0).round(4)
        vakalar.append({"ad": f"rastgele_{i}", "lmk": lmk.tolist(), "image_size": 112})

    # 🔴 Dejenere: 5 nokta da aynı doğru üzerinde → rank düşük dalı
    vakalar.append({
        "ad": "dejenere_dogrusal",
        "lmk": [[10.0, 10.0], [20.0, 20.0], [30.0, 30.0], [40.0, 40.0], [50.0, 50.0]],
        "image_size": 112,
    })
    # 🔴 Dejenere: tüm noktalar aynı → rank 0
    vakalar.append({
        "ad": "dejenere_tek_nokta",
        "lmk": [[7.0, 7.0]] * 5,
        "image_size": 112,
    })

    for v in vakalar:
        # face_align.estimate_norm'un aynısı
        image_size = v["image_size"]
        if image_size % 112 == 0:
            ratio = float(image_size) / 112.0
            diff_x = 0.0
        else:
            ratio = float(image_size) / 128.0
            diff_x = 8.0 * ratio
        dst = ARCFACE_DST * ratio
        dst[:, 0] += diff_x

        tform = trans.SimilarityTransform()
        tform.estimate(np.array(v["lmk"], dtype=np.float32), dst)
        v["dst"] = _m(dst)
        v["beklenen_params"] = _m(tform.params)
    return vakalar


def kurucu_vakalari() -> list[dict]:
    """`SimilarityTransform(scale=/rotation=/translation=)` — tek tek."""
    vakalar = [
        {"ad": "bos", "kwargs": {}},
        {"ad": "olcek", "kwargs": {"scale": 1.7531}},
        {"ad": "olcek_kucuk", "kwargs": {"scale": 0.213}},
        {"ad": "donme_30", "kwargs": {"rotation": math.radians(30.0)}},
        {"ad": "donme_negatif", "kwargs": {"rotation": -1.2345}},
        {"ad": "oteleme", "kwargs": {"translation": (-41.5, 96.25)}},
        {"ad": "ucu_birden", "kwargs": {"scale": 2.5, "rotation": 0.4, "translation": (12.0, -7.5)}},
    ]
    for v in vakalar:
        t = trans.SimilarityTransform(**v["kwargs"])
        # JSON tuple taşımaz → listeye çevir
        v["kwargs"] = {k: (list(x) if isinstance(x, tuple) else x) for k, x in v["kwargs"].items()}
        v["beklenen_params"] = _m(t.params)
    return vakalar


def bilesim_vakalari() -> list[dict]:
    """`t1 + t2 + t3 + t4` — face_align.transform()'un birebir aynısı.

    Bu yol `landmark.py` (2d106/3d68) ve `attribute.py` (yaş/cinsiyet)
    tarafından her karede koşar. Sıra yanlış olursa kırpma bozulur ve hata
    ancak model çıktısının kalitesinde görünür — patlamaz.
    """
    vakalar = []
    for ad, center, output_size, scale, rotation in [
        ("landmark_tipik", (160.0, 190.0), 192, 0.8123, 0.0),
        ("landmark_donmus", (160.0, 190.0), 192, 0.8123, 27.5),
        ("landmark_negatif_donme", (77.5, 240.25), 192, 1.4, -63.0),
        ("attribute_96", (300.0, 120.0), 96, 2.05, 12.0),
    ]:
        scale_ratio = scale
        rot = float(rotation) * np.pi / 180.0
        t1 = trans.SimilarityTransform(scale=scale_ratio)
        cx = center[0] * scale_ratio
        cy = center[1] * scale_ratio
        t2 = trans.SimilarityTransform(translation=(-1 * cx, -1 * cy))
        t3 = trans.SimilarityTransform(rotation=rot)
        t4 = trans.SimilarityTransform(translation=(output_size / 2, output_size / 2))
        t = t1 + t2 + t3 + t4
        vakalar.append({
            "ad": ad,
            "center": list(center),
            "output_size": output_size,
            "scale": scale,
            "rotation": rotation,
            "beklenen_params": _m(t.params),
        })
    return vakalar


def main() -> None:
    veri = {
        "_aciklama": "GERÇEK scikit-image ile üretilmiş altın değerler. Elle düzenleme — "
                     "yeniden üretmek için: scripts/pydeps-shim/altin-uret.py",
        "skimage_surumu": skimage.__version__,
        "numpy_surumu": np.__version__,
        "estimate": estimate_vakalari(),
        "kurucu": kurucu_vakalari(),
        "bilesim": bilesim_vakalari(),
    }
    HEDEF.parent.mkdir(parents=True, exist_ok=True)
    with open(HEDEF, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"✓ {HEDEF}")
    print(f"  scikit-image {skimage.__version__} · numpy {np.__version__}")
    print(f"  estimate {len(veri['estimate'])} · kurucu {len(veri['kurucu'])} · bileşim {len(veri['bilesim'])} vaka")


if __name__ == "__main__":
    main()

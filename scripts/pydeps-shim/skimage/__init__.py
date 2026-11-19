"""scikit-image'in **asgari yerine geçeni** — yalnız `insightface` içindir.

🔑 NEDEN VAR ( Dalga 2 FAZ 4, 2026-09-05):

`insightface` çalışmak için gerçek `scikit-image`'i tek bir sınıf yüzünden ister:

    insightface/utils/face_align.py:3   → from skimage import transform as trans
    insightface/utils/transform.py:4    → from skimage import transform as trans

Kullandığı tek şey `transform.SimilarityTransform`. Ama `scikit-image`'i kurmak
beraberinde `scipy` + `networkx` + `imageio` + `tifffile` + `lazy-loader`
zincirini getiriyor. Ölçüldü (2026-09-05, gerçek wheel'ler açılarak):

    zincirle    → 269 MB disk / 63 MB indirme
    zincirsiz   →  77 MB disk / 17 MB indirme

Yani indirilecek yükün **%78'i** tek bir benzerlik dönüşümü için geliyordu.
Yüz tanıma **Free** kademede olduğu için bu yükü potansiyel her müşteri çeker.
geliştirici kararı (2026-09-05): kırp.

⚠️ **`insightface`'in kendi kodu DEĞİŞTİRİLMEDİ.** Yama yok, monkey-patch yok.
Yapılan tek şey, indirilen paket ağacına `skimage` adında asgari bir paket
koymak — `import` onu bulur, `insightface` farkı anlamaz. Üçüncü parti kodun
**yoluna** giriyoruz ama **içine** girmiyoruz; sürüm yükseltmesi bu dosyayı
bozmaz, yalnız kapsamının hâlâ yeterli olup olmadığı yeniden ölçülmelidir.

⚠️ **Bu paket `sys.path`'in SONUNDA duran `pydeps` ağacındadır.** Ortamda
gerçek `scikit-image` varsa **o kazanır** (geliştirici makinesi, kişisel Alice).
Gölgeleme yönü bilerek böyle: asgari olan asla tam olanı ezmez.

📏 Kapsam ölçüldü (`grep -rn skimage insightface/`): `thirdparty/face3d/*`
dışında yalnız yukarıdaki iki dosya kullanıyor. `face3d` yolu ölü
(`thirdparty/__init__.py` boş) ve `skimage.io` / `skimage.measure` ister —
onları BİLEREK sağlamıyoruz. İsteyen olursa aşağıdaki `__getattr__` neyin
eksik olduğunu **adıyla** söyler; sessizce yanlış sonuç vermez.
"""

from __future__ import annotations

__version__ = "0.0.0+yuki-shim"

# Bu paketin fiilen sağladığı tek alt modül.
__all__ = ["transform"]

# Kasten sağlanmayanlar — istenirse ne olduğunu açıkça söylemek için.
_SAGLANMAYAN = {
    "io": "görüntü okuma/yazma (cv2 kullanın)",
    "measure": "bölge/kontur ölçümü",
    "filters": "görüntü filtreleri",
    "feature": "öznitelik çıkarımı",
    "color": "renk uzayı dönüşümleri",
    "util": "yardımcılar",
    "exposure": "histogram/pozlama",
    "morphology": "morfolojik işlemler",
}


def __getattr__(ad: str):
    """Eksik alt modül istendiğinde **teşhis edilebilir** hata ver.

    Varsayılan `ImportError` burada yetersiz kalırdı: "skimage.io yok" mesajı,
    okuyanı gerçek scikit-image'i kurmaya yönlendirir — oysa doğru cevap
    çoğu zaman "o kod yolu zaten ölü" ya da "cv2 ile yap". Yanlış teşhis,
    teşhissizlikten kötüdür.
    """
    if ad in _SAGLANMAYAN:
        raise ImportError(
            f"skimage.{ad} bu kurulumda YOK. Bu, Yuki'nin yüz tanıma yükündeki "
            f"asgari `skimage` yerine geçenidir; yalnız `transform.SimilarityTransform` "
            f"sağlar ({_SAGLANMAYAN[ad]} için gerçek scikit-image gerekir). "
            f"Buraya düştüyseniz ya beklenmedik bir kod yolu açıldı ya da "
            f"insightface sürümü değişti → scripts/pydeps-shim/ yeniden ölçülmeli."
        )
    raise AttributeError(f"module 'skimage' has no attribute {ad!r}")

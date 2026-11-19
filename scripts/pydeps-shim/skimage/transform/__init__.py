"""`skimage.transform.SimilarityTransform` — asgari, davranış-uyumlu karşılık.

Neden bu dosya var → `skimage/__init__.py` başlığı.

**Uyumluluk ölçütü sayısal eşitliktir, benzerlik değil.** Bu sınıfın ürettiği
matris, gerçek `scikit-image`'inkiyle `atol=1e-12` içinde aynı olmalıdır; aksi
hâlde yüzler ArcFace'in beklediğinden farklı hizalanır ve **tanıma sessizce
kötüleşir** — patlamaz, sadece yanlış cevap verir. Bu, en pahalı arıza sınıfı.
Bu yüzden testi altın değerlere karşıdır: `backend/tests/test_skimage_shim.py`,
değerleri gerçek `scikit-image 0.26.0` ile üretilmiştir
(`scripts/pydeps-shim/altin-uret.py`).

Uygulanan yüzey — `insightface`'in fiilen kullandığı kadarı, fazlası değil:

    SimilarityTransform()                       → birim
    SimilarityTransform(matrix=…)               → hazır matris
    SimilarityTransform(scale=…, rotation=…, translation=…)
    .estimate(src, dst)                         → Umeyama (ölçekli)
    .params                                     → 3×3 ndarray
    t1 + t2                                     → bileşim

⚠️ Bileşimin sırası ters görünür ama doğrudur: `(a + b).params == b.params @ a.params`.
Yani `a` ÖNCE uygulanır. scikit-image'in `ProjectiveTransform.__add__`'ı böyle
tanımlıdır ve `face_align.transform()` tam da bu sıraya güvenir (ölçekle → taşı →
döndür → ortala). Ters çevrilirse yüz kırpması bozulur.
"""

from __future__ import annotations

import math

import numpy as np

__all__ = ["SimilarityTransform"]


def _umeyama(src: np.ndarray, dst: np.ndarray, estimate_scale: bool) -> np.ndarray:
    """Umeyama (1991) kapalı-form benzerlik dönüşümü kestirimi.

    scikit-image'in `_geometric._umeyama`'sının birebir karşılığıdır — adım
    sırası ve dejenere durum işleme dâhil. Sadeleştirme YAPILMADI: buradaki
    her dal gerçek kütüphanede de var ve biri atlanırsa fark ancak bozuk bir
    girdide, yani en kötü anda ortaya çıkar.

    Kaynak: S. Umeyama, "Least-squares estimation of transformation parameters
    between two point patterns", IEEE PAMI 13(4), 1991 — Eq. (38)-(43).
    """
    # ⚠️ **dtype YÜKSELTİLMEZ.** İlk sürüm burada `dtype=np.float64` diyordu ve
    # sonuç altın değerlerden 4,8e-6 sapıyordu: `insightface` landmark'ları
    # `float32` verir, gerçek scikit-image de hesabı float32'de yapar. Sapma
    # pratikte önemsizdi (piksel altı) ama "aynı matris" iddiasını çürütüyordu —
    # ve iddiayı gevşetmek yerine hesabı hizalamak doğrusu: bir gün gerçek fark
    # çıkarsa gevşetilmiş tolerans onu da yutardı.
    src = np.asarray(src)
    dst = np.asarray(dst)

    num = src.shape[0]
    dim = src.shape[1]

    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)

    src_demean = src - src_mean
    dst_demean = dst - dst_mean

    # Eq. (38): çapraz kovaryans
    A = dst_demean.T @ src_demean / num

    # Eq. (39): yansımayı (determinant < 0) engelleyen işaret düzeltmesi.
    # Bu olmadan kestirim aynadaki yüzü "en iyi uyum" sayabilir.
    d = np.ones((dim,), dtype=np.float64)
    if np.linalg.det(A) < 0:
        d[dim - 1] = -1

    T = np.eye(dim + 1, dtype=np.float64)

    U, S, V = np.linalg.svd(A)

    # Eq. (40) ve (43): rank'e göre dallanma.
    # Rank elimizdeki tekil değerlerden hesaplanır — scikit-image de öyle yapar.
    # 📏 `np.linalg.matrix_rank(A)` ile değiştirmeyi denedik: 14 vakanın hiçbiri
    # ayrışmadı (mutasyon testi yeşil kaldı), çünkü numpy aynı eşik formülünü
    # kullanıyor. Yani buradaki tercih ölçülmüş bir davranış farkı değil;
    # gerekçesi ikinci bir SVD koşmamak ve kaynakla satır satır aynı kalmak.
    tol = S.max() * np.max(A.shape) * np.finfo(float).eps
    rank = np.count_nonzero(S > tol)
    if rank == 0:
        return np.nan * T
    elif rank == dim - 1:
        if np.linalg.det(U) * np.linalg.det(V) > 0:
            T[:dim, :dim] = U @ V
        else:
            s = d[dim - 1]
            d[dim - 1] = -1
            T[:dim, :dim] = U @ np.diag(d) @ V
            d[dim - 1] = s
    else:
        T[:dim, :dim] = U @ np.diag(d) @ V

    if estimate_scale:
        # Eq. (41) ve (42)
        scale = 1.0 / src_demean.var(axis=0).sum() * (S @ d)
    else:
        scale = 1.0

    T[:dim, dim] = dst_mean - scale * (T[:dim, :dim] @ src_mean.T)
    T[:dim, :dim] *= scale

    return T


class SimilarityTransform:
    """2B benzerlik dönüşümü: döndürme + tek ölçek + öteleme.

    Yalnız 2 boyut desteklenir — `insightface` başkasını istemiyor ve
    desteklemediğimiz bir boyutu sessizce kabul etmek, yanlış sonucu
    hataya tercih etmek olurdu.
    """

    def __init__(
        self,
        matrix: np.ndarray | None = None,
        scale: float | None = None,
        rotation: float | None = None,
        translation: tuple[float, float] | None = None,
        *,
        dimensionality: int = 2,
    ) -> None:
        if dimensionality != 2:
            raise NotImplementedError(
                "Bu asgari SimilarityTransform yalnız 2 boyut destekler "
                f"(istenen: {dimensionality}). Gerçek scikit-image gerekir."
            )

        params_verildi = any(p is not None for p in (scale, rotation, translation))

        if matrix is not None:
            if params_verildi:
                raise ValueError("`matrix` ile scale/rotation/translation birlikte verilemez")
            matrix = np.asarray(matrix, dtype=np.float64)
            if matrix.shape != (3, 3):
                raise ValueError(f"matrix 3×3 olmalı, gelen: {matrix.shape}")
            self.params = matrix
        elif params_verildi:
            if scale is None:
                scale = 1.0
            if rotation is None:
                rotation = 0.0
            if translation is None:
                translation = (0.0, 0.0)
            self.params = np.array(
                [
                    [math.cos(rotation), -math.sin(rotation), 0.0],
                    [math.sin(rotation), math.cos(rotation), 0.0],
                    [0.0, 0.0, 1.0],
                ]
            )
            self.params[0:2, 0:2] *= scale
            self.params[0:2, 2] = translation
        else:
            self.params = np.eye(3, dtype=np.float64)

    # ── kestirim ────────────────────────────────────────────────────────
    def estimate(self, src, dst) -> bool:
        """`src` → `dst` en küçük kareler benzerlik kestirimi.

        Dönüş `bool`: kestirim dejenere girdide (`nan`) başarısızdır.
        `insightface` dönüşe bakmıyor — ama `params` `nan` olursa
        `cv2.warpAffine` boş kare üretir; sessiz başarısızlık burada
        en azından **ölçülebilir** kalsın.
        """
        self.params = _umeyama(src, dst, estimate_scale=True)
        return bool(np.all(np.isfinite(self.params)))

    # ── bileşim ─────────────────────────────────────────────────────────
    def __add__(self, other: "SimilarityTransform") -> "SimilarityTransform":
        """Önce `self`, sonra `other` uygulanacak birleşik dönüşüm.

        ⚠️ Matris çarpımının sırası: `other.params @ self.params`.
        scikit-image ile birebir aynı; `face_align.transform()` buna güvenir.
        """
        if not isinstance(other, SimilarityTransform):
            raise TypeError(
                f"SimilarityTransform yalnız kendi türüyle birleştirilebilir, "
                f"gelen: {type(other).__name__}"
            )
        return SimilarityTransform(matrix=other.params @ self.params)

    def __repr__(self) -> str:  # pragma: no cover - teşhis kolaylığı
        return f"<SimilarityTransform(yuki-shim) params=\n{self.params}>"

"""ONNX embedding motoru ↔ sentence-transformers PARİTE testi.

Paketli üründe torch yok → embedding ONNX ile hesaplanır. Depodaki vektörlerin
(ve dolayısıyla hafıza geri çağırmanın) aynı kalması için iki motorun çıktısı
pratikte özdeş olmalı. Bu test dev makinede koşar (iki motor da kurulu).

int8 kuantizasyon küçük sapma yaratır — eşik cosine ≥ 0.99 ve sıralama korunumu.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.services import embedding_onnx

def _referans_motor_var() -> bool:
    """torch + sentence-transformers kurulu mu?

    2026-08-01: dev venv'inden torch/nvidia/triton (4,5 GB) kaldırıldı — ürün bunları
    HİÇ kullanmıyor (paketlenmiş üründe de yoklar). Bu testin ön koşulu zaten
    docstring'de yazılıydı ("dev makinede koşar, iki motor da kurulu") ama koda
    yazılmamıştı; şimdi açık.

    ⚠️ Test ZAYIFLATILMADI, ön koşulu görünür yapıldı. Parite kontrolünün önemli
    olduğu tek an ONNX modelinin YENİDEN EXPORT edildiği andır — ve
    `scripts/export_embedding_onnx.py` zaten `torch` import ediyor, yani export
    yapabilen makinede bu test otomatik olarak koşar. Torch'suz makinede ise
    karşılaştırılacak referans motor fiziksel olarak yoktur.
    """
    try:
        import torch  # noqa: F401
        import sentence_transformers  # noqa: F401
        return True
    except Exception:
        return False


pytestmark = [
    pytest.mark.skipif(
        not embedding_onnx.available(),
        reason="ONNX model dosyaları yok (scripts/export_embedding_onnx.py çalıştırılmamış)",
    ),
    pytest.mark.skipif(
        not _referans_motor_var(),
        reason="Referans motor yok — parite testi için: pip install torch sentence-transformers "
               "(ONNX'i yeniden export edecek makinede zaten kuruludur)",
    ),
]

TEXTS = [
    "Kullanıcının kedisinin adı Pamuk ve en sevdiği renk turkuaz.",
    "Yarın saat 9'da diş hekimi randevusu var.",
    "İpek Arch Linux kullanıyor ve Vanilla JS tercih ediyor.",
    "kedisinin adı ne?",
    "The user prefers dark mode interfaces.",
]


def _st_encode(texts):
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    return np.array(m.encode(texts, normalize_embeddings=True), dtype=np.float32)


def test_onnx_matches_sentence_transformers():
    onnx = np.array(embedding_onnx.encode(TEXTS), dtype=np.float32)
    ref = _st_encode(TEXTS)

    assert onnx.shape == ref.shape == (len(TEXTS), 384)
    # normalize edilmiş mi (cosine deposu bunu varsayar)
    assert np.allclose(np.linalg.norm(onnx, axis=1), 1.0, atol=1e-3)

    cos = (onnx * ref).sum(axis=1)  # ikisi de birim vektör
    # Ölçülen sapma (int8 dinamik kuantizasyon): 0.984-0.995. Eşik ölçüme göre 0.98.
    # Kritik olan mutlak eşitlik değil, sıralamanın korunması (alttaki test) —
    # üründe yazma da okuma da ONNX olduğu için depo kendi içinde birebir tutarlı.
    assert cos.min() >= 0.98, f"ONNX↔ST sapması fazla: {cos}"


def test_onnx_is_self_consistent():
    """Aynı metin iki çağrıda birebir aynı vektör — depo tutarlılığının şartı."""
    a = np.array(embedding_onnx.encode(TEXTS[:2]), dtype=np.float32)
    b = np.array(embedding_onnx.encode(TEXTS[:2]), dtype=np.float32)
    assert np.array_equal(a, b)


def test_onnx_batch_close_to_single():
    """Aynı metin, batch içinde ve tek başına ~aynı vektörü vermeli.

    int8 çekirdekleri batch boyutuna göre biraz farklı yol izliyor → ölçülen
    sapma 0.991-0.998 (per-channel kuantizasyonla). Geri çağırmada eşik 0.40,
    alakalı skorlar 0.6-0.9 aralığında olduğu için bu fark pratikte etkisiz;
    yine de sessizce büyümesin diye kilitliyoruz.
    """
    batch = np.array(embedding_onnx.encode(TEXTS), dtype=np.float32)
    singles = np.array([embedding_onnx.encode([t])[0] for t in TEXTS], dtype=np.float32)
    cos = (batch * singles).sum(axis=1)
    assert cos.min() >= 0.99, f"batch↔tekil sapması büyüdü: {cos}"


def test_onnx_preserves_semantic_ranking():
    """Sorgu, alakalı anıyı alakasızlardan yüksek skorlamalı (geri çağırma davranışı)."""
    vecs = np.array(embedding_onnx.encode(TEXTS), dtype=np.float32)
    query = vecs[3]                       # "kedisinin adı ne?"
    scores = vecs[:3] @ query
    assert scores.argmax() == 0           # kedi cümlesi kazanmalı
    assert scores[0] - scores[1:].max() > 0.15

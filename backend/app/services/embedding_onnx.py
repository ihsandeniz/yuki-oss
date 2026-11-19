"""ONNX embedding motoru — torch'suz, paketlenebilir (Ultra semantik hafızanın motoru).

Ürün paketi (`pybundle`) boyut nedeniyle torch/sentence-transformers İÇERMEZ; buna
karşılık `onnxruntime` + `tokenizers` zaten içindedir. Bu modül aynı modelin
(paraphrase-multilingual-MiniLM-L12-v2) ONNX int8 sürümünü çalıştırır:

    tokenize → transformer → mean pooling (maskeli) → L2 normalize

Çıktı sentence-transformers `encode(..., normalize_embeddings=True)` ile birebir
aynı sözleşmedir: 384 boyut, normalize, cosine'e hazır. Model dosyaları yoksa
`available()` False döner ve memory.py sentence-transformers'a düşer (geliştirme).

Dosyalar: models/embedding-onnx/{model_int8.onnx, tokenizer.json, meta.json}
Üretimi: scripts/export_embedding_onnx.py (dev-only, bir kez).
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from app.config import EMBED_ONNX_DIR

logger = logging.getLogger(__name__)

MODEL_FILE = "model_int8.onnx"
TOKENIZER_FILE = "tokenizer.json"
MAX_LENGTH = 128

_session = None
_tokenizer = None
_lock = threading.Lock()
_broken = False   # yükleme kalıcı olarak başarısız (bozuk/yarım dosya) → motor yok say


def _dir() -> Path:
    return Path(EMBED_ONNX_DIR)


def available() -> bool:
    """Motor kullanılabilir mi? Dosyalar yerinde VE yükleme daha önce patlamamış.

    False dönmesi ölümcül değildir: çağıran (llm.py) semantik hafızayı kapatıp
    lite hafızaya düşer — sohbet çalışmaya devam eder. Model indirilmemiş/iptal
    edilmiş Ultra kullanıcısı bu yüzden sohbetsiz kalmaz.
    """
    if _broken:
        return False
    d = _dir()
    return (d / MODEL_FILE).is_file() and (d / TOKENIZER_FILE).is_file()


def reset() -> None:
    """Model indirildikten sonra çağrılır — 'bozuk' işaretini temizler (yeniden dene)."""
    global _session, _tokenizer, _broken
    with _lock:
        _session = None
        _tokenizer = None
        _broken = False


def _load():
    """Oturum + tokenizer'ı thread-safe yükle (memory.py deseni).

    Yükleme patlarsa motor `_broken` işaretlenir → `available()` False döner →
    üst katman semantik hafızayı kapatır (sohbet ölmez).
    """
    global _session, _tokenizer, _broken
    if _session is not None:
        return _session, _tokenizer
    with _lock:
        if _session is None:
            import onnxruntime as ort
            from tokenizers import Tokenizer

            d = _dir()
            try:
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 2  # masaüstü uygulaması — CPU'yu domine etme
                sess = ort.InferenceSession(
                    str(d / MODEL_FILE), opts, providers=["CPUExecutionProvider"]
                )
                tok = Tokenizer.from_file(str(d / TOKENIZER_FILE))
            except Exception as e:
                _broken = True
                logger.warning(
                    "Embedding: ONNX motoru yüklenemedi (%s) → semantik hafıza kapalı, "
                    "lite hafıza devrede. Sebep: %s", d, e,
                )
                raise
            tok.enable_truncation(max_length=MAX_LENGTH)
            tok.enable_padding()
            _tokenizer = tok
            _session = sess
            logger.info("Embedding: ONNX motoru yüklendi (%s)", d)
    return _session, _tokenizer


def encode(texts: list[str]) -> list[list[float]]:
    """Metinleri normalize edilmiş 384-dim vektörlere çevir (bloklayıcı — executor'da çağır)."""
    import numpy as np

    sess, tok = _load()
    encs = tok.encode_batch(list(texts))
    input_ids = np.array([e.ids for e in encs], dtype=np.int64)
    attention = np.array([e.attention_mask for e in encs], dtype=np.int64)

    outputs = sess.run(None, {"input_ids": input_ids, "attention_mask": attention})
    hidden = outputs[0]                                    # (batch, seq, dim)

    mask = attention.astype(np.float32)[..., None]         # (batch, seq, 1)
    summed = (hidden * mask).sum(axis=1)
    counts = np.clip(mask.sum(axis=1), 1e-9, None)
    pooled = summed / counts                               # mean pooling

    norms = np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)
    return (pooled / norms).astype(np.float32).tolist()

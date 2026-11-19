"""Embedding modelini ONNX'e (int8) çevir — paketlenmiş üründe torch'suz hafıza.

NEDEN: ürün paketi (`pybundle`) boyut için torch/sentence-transformers İÇERMEZ.
Ultra'nın semantik hafızası embedding'siz çalışamaz. onnxruntime + tokenizers
zaten pakette olduğu için model ONNX'e çevrilip gömülür → aynı model, aynı
384-dim vektörler, torch yok.

DEV-ONLY: bu script ürüne girmez, sadece bir kez çalıştırılır.

    venv/bin/python scripts/export_embedding_onnx.py

Çıktı: backend/models-cache/embedding-onnx/{model_int8.onnx, tokenizer.json, meta.json}
(models-cache = indir-gerektiğinde model konvansiyonu — lite build hariç tutar.)
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import torch
from transformers import AutoModel, AutoTokenizer

MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
OUT_DIR = Path(__file__).resolve().parents[1] / "models-cache" / "embedding-onnx"
MAX_LEN = 128  # sentence-transformers'ın bu modeldeki varsayılan max_seq_length


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_onnx = OUT_DIR / "model_fp32.onnx"
    int8_onnx = OUT_DIR / "model_int8.onnx"

    print(f"→ model indiriliyor/yükleniyor: {MODEL_ID}")
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModel.from_pretrained(MODEL_ID).eval()

    print("→ tokenizer.json yazılıyor (tokenizers kütüphanesi tek başına okur)")
    tmp = OUT_DIR / "_tok"
    tok.save_pretrained(tmp)
    shutil.copy(tmp / "tokenizer.json", OUT_DIR / "tokenizer.json")
    shutil.rmtree(tmp, ignore_errors=True)

    print("→ ONNX export (dinamik batch + sequence)")
    dummy = tok(["merhaba dünya", "test"], padding=True, truncation=True,
                max_length=MAX_LEN, return_tensors="pt")
    torch.onnx.export(
        model,
        (dummy["input_ids"], dummy["attention_mask"]),
        str(raw_onnx),
        input_names=["input_ids", "attention_mask"],
        output_names=["last_hidden_state"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "seq"},
            "attention_mask": {0: "batch", 1: "seq"},
            "last_hidden_state": {0: "batch", 1: "seq"},
        },
        opset_version=17,
        do_constant_folding=True,
    )

    print("→ int8 dinamik kuantizasyon (boyut ~4×  küçülür)")
    from onnxruntime.quantization import QuantType, quantize_dynamic
    # per_channel + reduce_range: aynı boyutta belirgin daha az sapma
    # (kanal başına ölçek → embedding/MatMul ağırlıklarında doğruluk artar).
    quantize_dynamic(
        str(raw_onnx), str(int8_onnx),
        weight_type=QuantType.QInt8, per_channel=True, reduce_range=True,
    )
    raw_onnx.unlink(missing_ok=True)
    for junk in OUT_DIR.glob("model_fp32*"):   # quantize yan dosyaları
        junk.unlink(missing_ok=True)

    (OUT_DIR / "meta.json").write_text(json.dumps({
        "model_id": MODEL_ID,
        "dim": model.config.hidden_size,
        "max_length": MAX_LEN,
        "pooling": "mean",
        "normalize": True,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    size = int8_onnx.stat().st_size / 1024 / 1024
    print(f"✅ bitti: {int8_onnx} ({size:.0f} MB) + tokenizer.json")


if __name__ == "__main__":
    main()

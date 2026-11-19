#!/usr/bin/env bash
# ── İndir-gerektiğinde EMBEDDING paketi üret ────────────────────────────────
# backend/models-cache/embedding-onnx (ONNX int8 + tokenizer) → .tar.gz + SHA256,
# electron/models-manifest.json'u OTOMATİK günceller, release yükleme komutunu basar.
# Kardeşi: build-model-package.sh (whisper). Aynı sözleşme, farklı model.
#
# Model yoksa önce:  cd backend && venv/bin/python scripts/export_embedding_onnx.py
# Kullanım       :  bash scripts/build-embedding-package.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # → depo kökü
CACHE="$HERE/backend/models-cache"
MODEL_REL="embedding-onnx"
OUT_DIR="$HERE/dist/models"
ASSET="embedding-onnx-int8.tar.gz"
MODEL_ID="embedding-onnx"
MANIFEST="$HERE/electron/models-manifest.json"
RELEASE_TAG="v0.4.0-models"
REPO="ihsandeniz/yuki-oss"

if [[ ! -f "$CACHE/$MODEL_REL/model_int8.onnx" ]]; then
  echo "✗ ONNX modeli yok: $CACHE/$MODEL_REL/model_int8.onnx" >&2
  echo "  Önce: cd backend && venv/bin/python scripts/export_embedding_onnx.py" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
echo "▸ Paketleniyor: $MODEL_REL → $ASSET"
tar -czf "$OUT_DIR/$ASSET" -C "$CACHE" "$MODEL_REL"

SHA="$(sha256sum "$OUT_DIR/$ASSET" | cut -d' ' -f1)"
DL_BYTES="$(stat -c%s "$OUT_DIR/$ASSET")"
RAW_BYTES="$(du -sb "$CACHE/$MODEL_REL" | cut -f1)"

echo ""
echo "✓ Paket hazır: $OUT_DIR/$ASSET"
printf "  Açık boyut     : %s (%d bayt)\n" "$(numfmt --to=iec "$RAW_BYTES" 2>/dev/null || echo "$RAW_BYTES")" "$RAW_BYTES"
printf "  İndirme boyutu : %s (%d bayt)\n" "$(numfmt --to=iec "$DL_BYTES" 2>/dev/null || echo "$DL_BYTES")" "$DL_BYTES"
printf "  SHA256         : %s\n" "$SHA"

python3 - "$MANIFEST" "$MODEL_ID" "$SHA" "$RAW_BYTES" "$DL_BYTES" "$RELEASE_TAG" "$ASSET" <<'PY'
import json, sys
manifest_path, mid, sha, raw, dl, tag, asset = sys.argv[1:8]
with open(manifest_path, encoding="utf-8") as f:
    data = json.load(f)
m = data["models"][mid]
m["sha256"] = sha
m["sizeBytes"] = int(raw)
m["downloadBytes"] = int(dl)
m["url"] = f"{data['releaseBase']}/{tag}/{asset}"
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"✓ Manifest güncellendi: {mid} (url/sha256/sizeBytes/downloadBytes)")
PY

echo ""
echo "▸ SONRAKİ ADIM — asset'i release'e yükle (Geliştirici):"
echo "    gh release upload $RELEASE_TAG \"$OUT_DIR/$ASSET\" --repo $REPO --clobber"
echo "  (release yoksa: gh release create $RELEASE_TAG \"$OUT_DIR/$ASSET\" --repo $REPO --title 'Model paketleri' --notes 'indir-gerektiğinde model asset'leri')"

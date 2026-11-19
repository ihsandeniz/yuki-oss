#!/usr/bin/env bash
# ── İndir-gerektiğinde model paketi üret ────────────────────────────────────
# backend/models-cache içindeki whisper HF-cache ağacını .tar.gz'e paketler, SHA256 +
# boyutları hesaplar, electron/models-manifest.json'u OTOMATİK günceller ve release
# yükleme komutunu basar. Çıktı: dist/models/whisper-small-int8.tar.gz
#
# Kullanım:  bash scripts/build-model-package.sh
# Sonra   :  betiğin bastığı `gh release upload …` komutunu çalıştır (asset'i yayınla).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # → depo kökü
CACHE="$HERE/backend/models-cache"
MODEL_REL="hub/models--Systran--faster-whisper-small"
OUT_DIR="$HERE/dist/models"
ASSET="whisper-small-int8.tar.gz"
MODEL_ID="whisper-small"
MANIFEST="$HERE/electron/models-manifest.json"
RELEASE_TAG="v0.4.0-models"
REPO="ihsandeniz/yuki-oss"

if [[ ! -d "$CACHE/$MODEL_REL" ]]; then
  echo "✗ Model bulunamadı: $CACHE/$MODEL_REL" >&2
  echo "  (backend/models-cache içinde whisper 'small' HF-cache ağacı olmalı)" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
echo "▸ Paketleniyor: $MODEL_REL → $ASSET"
# -C ile göreli yol 'hub/…' olarak saklanır → hedefte models-cache/hub/… olarak açılır.
tar -czf "$OUT_DIR/$ASSET" -C "$CACHE" "$MODEL_REL"

SHA="$(sha256sum "$OUT_DIR/$ASSET" | cut -d' ' -f1)"
DL_BYTES="$(stat -c%s "$OUT_DIR/$ASSET")"
RAW_BYTES="$(du -sb "$CACHE/$MODEL_REL" | cut -f1)"

echo ""
echo "✓ Paket hazır: $OUT_DIR/$ASSET"
printf "  Açık boyut     : %s (%d bayt)\n" "$(numfmt --to=iec "$RAW_BYTES" 2>/dev/null || echo "$RAW_BYTES")" "$RAW_BYTES"
printf "  İndirme boyutu : %s (%d bayt)\n" "$(numfmt --to=iec "$DL_BYTES" 2>/dev/null || echo "$DL_BYTES")" "$DL_BYTES"
printf "  SHA256         : %s\n" "$SHA"

# Manifest'i otomatik güncelle (python3 — jq bağımlılığı yok)
python3 - "$MANIFEST" "$MODEL_ID" "$SHA" "$RAW_BYTES" "$DL_BYTES" <<'PY'
import json, sys
manifest_path, mid, sha, raw, dl = sys.argv[1:6]
with open(manifest_path, encoding="utf-8") as f:
    data = json.load(f)
m = data["models"][mid]
m["sha256"] = sha
m["sizeBytes"] = int(raw)
m["downloadBytes"] = int(dl)
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"✓ Manifest güncellendi: {mid} (sha256/sizeBytes/downloadBytes)")
PY

echo ""
echo "▸ SONRAKİ ADIM — asset'i release'e yükle (Geliştirici):"
echo "    gh release create $RELEASE_TAG \"$OUT_DIR/$ASSET\" \\"
echo "      --repo $REPO --title 'Yuki Modelleri' --notes 'İndir-gerektiğinde model paketleri' 2>/dev/null \\"
echo "    || gh release upload $RELEASE_TAG \"$OUT_DIR/$ASSET\" --repo $REPO --clobber"
echo ""
echo "  (release zaten varsa ikinci komut asset'i ekler/değiştirir)"
echo "  Yüklendikten sonra manifest'teki url zaten doğru: .../download/$RELEASE_TAG/$ASSET"

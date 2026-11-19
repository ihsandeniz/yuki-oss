#!/usr/bin/env bash
# ── buffalo_l yüz modeli paketi ────────────────────────────────────
# `insightface`in indirdiği buffalo_l ağacını .tar.gz'e paketler, SHA256 + boyut
# hesaplar, models-manifest.json'u günceller ve release yükleme komutunu basar.
#
# Kullanım:  bash scripts/build-face-model-package.sh [--kaynak <dizin>]
# Sonra   :  betiğin bastığı `gh release upload …` komutunu çalıştır.
#
# 🔴 NEDEN VAR: model bugüne kadar YÖNETİLMİYORDU. insightface ilk `prepare()`
# çağrısında kendi indiricisiyle 289 MB'lık zip'i çekiyor — ilerleme göstergesi
# yok, iptal yok, SHA doğrulaması yok, "modelleri kaldır" onu görmüyor.
#
# ⚠️ Ve indirdiği yer bizim seçtiğimiz yer DEĞİLDİ: `INSIGHTFACE_HOME` ortam
# değişkeni set ediliyordu ama insightface onu HİÇ OKUMUYOR (kök,
# `FaceAnalysis(root='~/.insightface')` varsayılan parametresinden gelir).
# 2026-09-06'da ölçüldü: `~/.insightface` 601 MB — açılmış model + silinmemiş zip.
# Backend artık `root=` parametresini açıkça geçiyor
# (`app/services/insightface_havuzu.py::model_koku`); bu script onun beklediği
# ağaç yapısını üretir.
#
# 📐 DİZİN YAPISI — presenceDir ile extractTo AYNI OLMAMALI:
#     extractTo   = "insightface"                    → models-cache/insightface/
#     tar içeriği = "models/buffalo_l/*.onnx"
#     presenceDir = "insightface/models/buffalo_l"
#   Aynı olsalardı açıcı hedefi tar'dan önce mkdir'lediği için BOŞ arşiv
#   "kuruldu" sayılırdı (2026-09-05'te ölçülerek bulunmuştu).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # → depo kökü
KAYNAK_KOK="${HOME}/.insightface"
OUT_DIR="$HERE/dist/models"
ASSET="buffalo-l.tar.gz"
MODEL_ID="face-model"
MANIFEST="$HERE/electron/models-manifest.json"
RELEASE_TAG="v0.4.0-models"
REPO="ihsandeniz/yuki-oss"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --kaynak) KAYNAK_KOK="$2"; shift 2 ;;
    *) echo "bilinmeyen argüman: $1" >&2; exit 2 ;;
  esac
done

MODEL_DIR="$KAYNAK_KOK/models/buffalo_l"
if [[ ! -d "$MODEL_DIR" ]]; then
  echo "✗ Model bulunamadı: $MODEL_DIR" >&2
  echo "  Önce bir kez yüz tanıma çalıştır (insightface modeli kendisi indirir)," >&2
  echo "  ya da --kaynak ile modelin bulunduğu kökü ver." >&2
  exit 1
fi

# Beklenen beş model dosyası — biri eksikse paket sessizce yarım gider ve hata
# müşteride, ilk 'Tanı' anında çıkar.
GEREKEN=(det_10g.onnx w600k_r50.onnx 2d106det.onnx 1k3d68.onnx genderage.onnx)
for f in "${GEREKEN[@]}"; do
  [[ -f "$MODEL_DIR/$f" ]] || { echo "✗ Eksik model dosyası: $f" >&2; exit 1; }
done

mkdir -p "$OUT_DIR"
echo "▸ Paketleniyor: $MODEL_DIR → $ASSET"
# -C ile göreli yol 'models/buffalo_l/…' olarak saklanır → hedefte
# models-cache/insightface/models/buffalo_l/… olarak açılır.
tar -czf "$OUT_DIR/$ASSET" -C "$KAYNAK_KOK" "models/buffalo_l"

SHA="$(sha256sum "$OUT_DIR/$ASSET" | cut -d' ' -f1)"
DL_BYTES="$(stat -c%s "$OUT_DIR/$ASSET")"
RAW_BYTES="$(du -sb "$MODEL_DIR" | cut -f1)"

echo ""
echo "✓ Paket hazır: $OUT_DIR/$ASSET"
printf "  Açık boyut     : %s (%d bayt)\n" "$(numfmt --to=iec "$RAW_BYTES" 2>/dev/null || echo "$RAW_BYTES")" "$RAW_BYTES"
printf "  İndirme boyutu : %s (%d bayt)\n" "$(numfmt --to=iec "$DL_BYTES" 2>/dev/null || echo "$DL_BYTES")" "$DL_BYTES"
printf "  SHA256         : %s\n" "$SHA"

# ── Manifest güncelle ───────────────────────────────────────────────────────
# Kayıt `plannedModels` altına yazılır. `models`a terfi YALNIZ asset gerçekten
# inebiliyorsa yapılır (--dogrula) — `models` altındaki her girdi indirilebilir
# SAYILIR ve url'i ölü bir girdi UI'da "indir" görünüp indirme anında patlar.
python3 - "$MANIFEST" "$MODEL_ID" "$ASSET" "$SHA" "$DL_BYTES" "$RAW_BYTES" \
         "$RELEASE_TAG" "$REPO" <<'PY'
import json, sys
manifest, mid, asset, sha, dl, raw, tag, repo = sys.argv[1:9]
with open(manifest, encoding="utf-8") as f:
    m = json.load(f)

kayit = {
    "name": "Yüz Tanıma Modeli",
    "feature": "Yüz tanıma — buffalo_l",
    # 🌐 Kayıt burada BAŞTAN yazılıyor — i18n alanı unutulursa model indirme
    # penceresi EN kullanıcıya Türkçe ad gösterir.
    "i18n": {"en": {"name": "Face Recognition Model",
                    "feature": "Face recognition — buffalo_l"}},
    "asset": asset,
    "url": f"https://github.com/{repo}/releases/download/{tag}/{asset}",
    "sha256": sha,
    "sizeBytes": int(raw),
    "downloadBytes": int(dl),
    # 📐 presenceDir ≠ extractTo (bkz. dosya başı)
    "presenceDir": "insightface/models/buffalo_l",
    "extractTo": "insightface",
    "tier": "lite",
    "_note": ("InsightFace buffalo_l (5 ONNX: det_10g · w600k_r50 · 2d106det · "
              "1k3d68 · genderage). PLATFORMDAN BAĞIMSIZ — tek asset yeter, "
              "pydeps'in aksine assets{} şemasına gerek yok. Backend kökü "
              "INSIGHTFACE_HOME'dan okur ve FaceAnalysis'e root= olarak GEÇER; "
              "insightface ortam değişkeni okumaz. Üretici: "
              "scripts/build-face-model-package.sh"),
}

# Zaten `models` altındaysa oraya yaz (terfi geri alınmasın), yoksa planned'a.
hedef = "models" if mid in m.get("models", {}) else "plannedModels"
m.setdefault(hedef, {})[mid] = kayit
with open(manifest, "w", encoding="utf-8") as f:
    json.dump(m, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"✓ manifest güncellendi → {hedef}.{mid}")
PY

echo ""
echo "▸ Sıradaki adım — asset'i yayınla:"
echo "    gh release upload $RELEASE_TAG \"$OUT_DIR/$ASSET\" --repo $REPO --clobber"
echo "  Sonra terfi ettir (asset'in GERÇEKTEN indiğini ölçer):"
echo "    bash scripts/build-pydeps-package.sh --dogrula   # face-pydeps + face-model"

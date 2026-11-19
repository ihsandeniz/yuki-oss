#!/usr/bin/env bash
# ── İndir-gerektiğinde PYTHON PAKET yükü üret ───────────────────────────────
# `build-model-package.sh`'ın kardeşi. Fark tek ve kritik:
#
#   🔑 MODEL PLATFORMDAN BAĞIMSIZ, PYTHON PAKETİ DEĞİL.
#   `.onnx` her yerde aynı; scipy/onnx içinde derlenmiş `.so` (Linux) / `.pyd`
#   (Windows) var. Bu yüzden yük başına TEK asset yetmez → PLATFORM BAŞINA bir asset.
#   Manifest'e `assets: { "linux-x64": {...}, "win-x64": {...} }` olarak yazılır.
#
# NEDEN VAR ( Dalga 2, 2026-09-05): yüz tanıma modeli (326 MB) mevcut
# `model-manager.js` katmanıyla inebiliyor, ama modeli OKUYACAK Python paketleri
# kutuda yok. Onları pakete koymak her müşteriye yük bindirirdi (yüz tanımayı hiç
# açmayana bile) ve `model-manager.js:3-4`'ün kendi yazdığı ilkeyi delerdi:
# *"çekirdek paket küçük kalsın, kullanıcı sadece kullandığı özelliğin modelini indirsin"*.
# geliştirici kararı (B): kütüphane de indirilebilir olsun.
#
# ⚠️ LİSTE KURALI: buraya YALNIZ kutuda OLMAYAN paketler yazılır. Kutudakini
# tekrarlamak boşuna MB'dir — backend pydeps'i `sys.path`'e SONA eklediği için
# kutunun kopyası zaten kazanır. Script bu kuralı mekanik olarak DENETLER
# (`backend/pybundle-kilit.txt` ile kesişim → hata).
#
# Kullanım:  bash scripts/build-pydeps-package.sh
#            bash scripts/build-pydeps-package.sh --yalniz linux-x64
# Sonra   :  betiğin bastığı `gh release upload …` komutunu çalıştır.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # → depo kökü
OUT_DIR="$HERE/dist/pydeps"
MANIFEST="$HERE/electron/models-manifest.json"
RELEASE_TAG="${RELEASE_TAG:-v0.4.0-models}"
REPO="ihsandeniz/yuki-oss"
PYVER="3.14"
BUNDLE_PY="$HERE/backend/pybundle/bin/python$PYVER"

PYDEPS_ID="face-pydeps"
EXTRACT_TO="pydeps/face"                    # models-cache içindeki açma hedefi
# ⚠️ presenceDir, extractTo ile AYNI OLMAMALI. `_extract` hedefi tar'dan önce
# mkdir'liyor; ikisi aynıysa varlık kapısı açıcının kendi ürettiği dizini ölçer ve
# BOŞ arşiv "kuruldu" sayılır (2026-09-05'te ölçülerek bulundu, model-manager.js
# içinde `_dolu()` ile koda da bağlandı). Burada bir kat daha derine bakıyoruz:
# arşivin gerçekten TAŞIMASI gereken paket dizini.
PRESENCE_DIR="pydeps/face/insightface"

# ── Paket listesi ───────────────────────────────────────────────────────────
# Ölçüldü 2026-09-05: bunların hiçbiri pybundle'da YOK. Kutuda ZATEN olanlar
# (numpy · onnxruntime · opencv-python-headless · tqdm · requests · pillow · packaging)
# bilerek dışarıda — bkz. LİSTE KURALI.
#
# ⚠️ `ml_dtypes` görünmez bağımlılık: `onnx` onu modül tepesinde import ediyor
#    (`onnx/_mapping.py:8`) ama PyPI meta verisinde bizim çözümleme yolumuzda
#    görünmüyordu → ilk kurulumda `ModuleNotFoundError` verdi.
#
# ✂️ KIRPILDI (FAZ 4, geliştirici kararı 2026-09-05): `scikit-image` + `scipy` +
#    `networkx` + `imageio` + `tifffile` + `lazy-loader` zinciri buradan çıkarıldı.
#    Yükün %78'iydi (62 MB indirme / 192 MB disk) ve TEK bir sınıf için geliyordu:
#    `insightface/utils/{face_align,transform}.py` → `SimilarityTransform`.
#    Yerine `scripts/pydeps-shim/skimage` konuyor (aşağıda, SHIM bölümü).
#    Yüz tanıma **Free** kademede; bu yükü potansiyel her müşteri indirecekti.
PAKETLER=(
  insightface
  onnx
  ml_dtypes
)

# ── Shim: gerçek scikit-image'in yerine geçen asgari `skimage` ───────────────
# insightface'in KENDİ KODU değişmiyor; ağaca `skimage` adında asgari bir paket
# koyuyoruz, `import` onu buluyor. Sayısal eşdeğerlik gerçek scikit-image 0.26.0
# altın değerlerine karşı test ediliyor: `backend/tests/test_skimage_shim.py`
# (atol=1e-12) + gerçek insightface'le uçtan uca ölçüldü (matrisler ve
# `norm_crop` piksel çıktısı BİREBİR aynı, 2026-09-05).
SHIM_KAYNAK="$HERE/scripts/pydeps-shim/skimage"

# ── Platformlar ─────────────────────────────────────────────────────────────
# ad|pip --platform etiketi|yerel mi
PLATFORMLAR=(
  "linux-x64|manylinux2014_x86_64|yerel"
  "win-x64|win_amd64|capraz"
)

YALNIZ=""; DOGRULA=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yalniz)  YALNIZ="${2:-}"; shift 2 ;;
    --dogrula) DOGRULA=1; shift ;;
    # Doğrulama başka bir manifest kaydına da uygulanabilir (ör. face-model).
    # Üretim tarafı hâlâ yalnız pydeps'i biliyor; `--id` sadece --dogrula içindir.
    --id) PYDEPS_ID="${2:?--id bir manifest kaydı ister}"; shift 2 ;;
    *) echo "✗ bilinmeyen seçenek: $1" >&2; exit 2 ;;
  esac
done

# ── --dogrula: asset'ler GERÇEKTEN inebiliyor mu → plannedModels'tan models'a terfi ──
# Kanıtsız terfi yok. Bu vault'ta "push ✅" iki kez kanıtsız yazıldı ve ikisi de yanlıştı.
if [[ "$DOGRULA" == "1" ]]; then
  python3 - "$MANIFEST" "$PYDEPS_ID" <<'PY'
import json, sys, urllib.request, urllib.error
mpath, pid = sys.argv[1:3]
with open(mpath, encoding="utf-8") as f:
    data = json.load(f)
kayit = data.get("plannedModels", {}).get(pid) or data.get("models", {}).get(pid)
if not kayit:
    sys.exit(f"✗ manifest'te {pid} yok — önce yükü üret")

# İki kayıt biçimi var, doğrulama İKİSİNİ de bilmeli:
#   assets{} → platforma özel (pydeps: linux-x64 / win-x64, derlenmiş .so/.pyd)
#   düz url  → platformdan bağımsız (buffalo_l: saf .onnx, tek dosya yeter)
# İkinci biçim için ayrı bir doğrulayıcı yazmak, "asset gerçekten iniyor mu"
# sorusuna iki ayrı yerde cevap üretirdi; er geç ayrışırlar (surum.js dersi).
assets = kayit.get("assets") or {}
if not assets:
    url = kayit.get("url") or ""
    if not url:
        sys.exit(f"✗ {pid} için ne assets{{}} ne url var")
    assets = {"tek": {"url": url}}

kotu = 0
for ad, a in sorted(assets.items()):
    url = a.get("url", "")
    try:
        # HEAD bazı CDN'lerde reddedilir; Range ile 1 bayt iste → 206/200 ikisi de sağlam
        req = urllib.request.Request(url, headers={"Range": "bytes=0-0",
                                                   "User-Agent": "Yuki-ModelManager"})
        with urllib.request.urlopen(req, timeout=30) as r:
            kod = r.status
        print(f"  {'✓' if kod in (200, 206) else '✗'} {ad:10} HTTP {kod}")
        if kod not in (200, 206):
            kotu += 1
    except urllib.error.HTTPError as e:
        print(f"  ✗ {ad:10} HTTP {e.code}"); kotu += 1
    except Exception as e:
        print(f"  ✗ {ad:10} {type(e).__name__}: {e}"); kotu += 1

if kotu:
    sys.exit(f"\n✗ {kotu} asset inemiyor — TERFİ YOK. Önce `gh release upload` koş.")

data.setdefault("models", {})[pid] = kayit
data.get("plannedModels", {}).pop(pid, None)
with open(mpath, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2); f.write("\n")
print(f"\n✓ {pid} terfi etti: plannedModels → models (artık indirilebilir)")
PY
  exit $?
fi

[[ -x "$BUNDLE_PY" ]] || { echo "✗ pybundle python yok: $BUNDLE_PY" >&2; exit 1; }

# ── Kesişim denetimi: kutuda zaten olan paketi yüke koyma ───────────────────
KILIT="$HERE/backend/pybundle-kilit.txt"
if [[ -f "$KILIT" ]]; then
  CAKISAN="$(python3 - "$KILIT" "${PAKETLER[@]}" <<'PY'
import re, sys
kilit = sys.argv[1]; istenen = sys.argv[2:]
norm = lambda s: re.sub(r"[-_.]+", "-", s).lower()
kutuda = set()
for satir in open(kilit, encoding="utf-8"):
    satir = satir.strip()
    if satir and not satir.startswith("#") and "==" in satir:
        kutuda.add(norm(satir.split("==")[0]))
print(" ".join(sorted(p for p in istenen if norm(p) in kutuda)))
PY
)"
  if [[ -n "$CAKISAN" ]]; then
    echo "✗ Bu paketler pybundle'da ZATEN var: $CAKISAN" >&2
    echo "  Yüke koymak boşuna MB — backend pydeps'i sys.path'e SONA ekler," >&2
    echo "  kutunun kopyası zaten kazanır. Listeden çıkar." >&2
    exit 1
  fi
  echo "✓ kesişim denetimi temiz (${#PAKETLER[@]} paket, hiçbiri kutuda yok)"
else
  echo "⚠ $KILIT yok — kesişim denetimi atlandı (bundle-envanter.py koş)"
fi

mkdir -p "$OUT_DIR"
declare -A SONUC   # "ad|alan" → değer

for satir in "${PLATFORMLAR[@]}"; do
  IFS='|' read -r AD ETIKET TIP <<< "$satir"
  [[ -n "$YALNIZ" && "$YALNIZ" != "$AD" ]] && continue

  echo ""
  echo "▸ $AD ($ETIKET) ağacı kuruluyor…"
  AGAC="$(mktemp -d)"
  trap 'rm -rf "$AGAC"' EXIT

  if [[ "$TIP" == "yerel" ]]; then
    # Yerel: kutunun KENDİ python'uyla kur → ABI etiketleri birebir doğru.
    # PYTHONNOUSERSITE=1 ŞART — ledger: pybundle python'u ~/.local'ı kendi
    # site-packages'ından ÖNCE görüyor, onsuz ölçüm yanıltıcı.
    PYTHONNOUSERSITE=1 "$BUNDLE_PY" -m pip install \
      --target "$AGAC" --no-deps --no-cache-dir --quiet "${PAKETLER[@]}"
  else
    # Çapraz: vendor-msvc-runtime.py'nin kullandığı desen (--platform + --python-version)
    python3 -m pip install \
      --target "$AGAC" --no-deps --no-cache-dir --quiet \
      --only-binary=:all: --platform "$ETIKET" --python-version "$PYVER" \
      "${PAKETLER[@]}"
  fi

  # Gereksiz: konsol betikleri (hedefte PATH'e girmiyor) + derleme önbelleği
  rm -rf "$AGAC/bin" "$AGAC/Scripts"
  find "$AGAC" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

  # Ağacın gerçekten dolu olduğunu ölç — boş yükü sessizce yayınlama
  ADET="$(find "$AGAC" -maxdepth 1 -name '*.dist-info' | wc -l)"
  if [[ "$ADET" -lt "${#PAKETLER[@]}" ]]; then
    echo "✗ $AD: ${#PAKETLER[@]} paket beklendi, $ADET dist-info bulundu" >&2
    exit 1
  fi

  # ── Shim'i ağaca koy + üç kapı ────────────────────────────────────────────
  [[ -d "$SHIM_KAYNAK" ]] || { echo "✗ shim yok: $SHIM_KAYNAK" >&2; exit 1; }

  # ① Gerçek scikit-image sızdı mı? `--no-deps` bunu engellemeli, ama listeye
  #    bir gün skimage isteyen bir paket eklenirse shim sessizce ÜZERİNE yazılır
  #    ve yük 192 MB büyür — kimse fark etmez. Kapı burada.
  if [[ -e "$AGAC/skimage" ]]; then
    echo "✗ $AD: ağaçta zaten bir 'skimage' var — gerçek scikit-image sızmış." >&2
    echo "  Shim onun üzerine yazılırsa hangi kodun koştuğu belirsizleşir." >&2
    exit 1
  fi
  cp -r "$SHIM_KAYNAK" "$AGAC/skimage"
  find "$AGAC/skimage" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

  # ② Kopyalanan gerçekten SHIM mi (dosya adı değil, içeriği damgalıyoruz)
  grep -q "yuki-shim" "$AGAC/skimage/__init__.py" || {
    echo "✗ $AD: kopyalanan skimage shim damgası taşımıyor" >&2; exit 1; }

  # ③ 🔑 Ağaç FİİLEN çalışıyor mu — yalnız yerel platformda koşabilir.
  #    Cross-install edilen Windows ağacı burada import edilemez (.pyd),
  #    o yüzden atlanır; atlandığı SÖYLENİR (sessiz atlama, yeşil sanılır).
  if [[ "$TIP" == "yerel" ]]; then
    if PYTHONNOUSERSITE=1 PYTHONPATH="$AGAC" "$BUNDLE_PY" - <<'PY'
import sys
import skimage
from insightface.utils import face_align
import numpy as np
assert "yuki-shim" in skimage.__version__, f"shim değil: {skimage.__version__}"
# gerçek hizalama yolu koşsun — import etmek yetmez, HESAP yapsın
M = face_align.estimate_norm(
    np.array([[120.,150.],[200.,150.],[160.,195.],[128.,240.],[192.,240.]], dtype=np.float32),
    image_size=112)
assert M.shape == (2, 3) and np.isfinite(M).all(), M
sys.exit(0)
PY
    then
      echo "  ✓ $AD: shim'li ağaçta insightface hizalaması koştu"
    else
      echo "✗ $AD: kırpılmış ağaçta insightface hizalaması KOŞMADI" >&2
      echo "  (skimage kullanımı genişlemiş olabilir → scripts/pydeps-shim/ yeniden ölç)" >&2
      exit 1
    fi
  else
    echo "  ⏭ $AD: çapraz kurulum — import denemesi bu makinede yapılamaz (atlandı)"
  fi

  ASSET="${PYDEPS_ID}-${AD}.tar.gz"
  # TEKRARLANABİLİR arşiv: aynı girdi → aynı SHA256. Bayrakları koymadan iki koşu
  # farklı hash veriyordu (dosya mtime'ı + dizin sırası + sahiplik arşive giriyor).
  # Tekrarlanamayan hash, yayınlanmış asset'i yeniden üretip DOĞRULAMAYI imkânsız kılar.
  # gzip -n: gzip başlığına zaman damgası yazma.
  tar --sort=name --mtime='@0' --owner=0 --group=0 --numeric-owner \
      -cf - -C "$AGAC" . | gzip -n -9 > "$OUT_DIR/$ASSET"
  SHA="$(sha256sum "$OUT_DIR/$ASSET" | cut -d' ' -f1)"
  DL="$(stat -c%s "$OUT_DIR/$ASSET")"
  RAW="$(du -sb "$AGAC" | cut -f1)"
  rm -rf "$AGAC"; trap - EXIT

  SONUC["$AD|asset"]="$ASSET"; SONUC["$AD|sha"]="$SHA"
  SONUC["$AD|dl"]="$DL";       SONUC["$AD|raw"]="$RAW"

  printf "  ✓ %-9s açık %-8s indirme %-8s %s\n" "$AD" \
    "$(numfmt --to=iec "$RAW")" "$(numfmt --to=iec "$DL")" "${SHA:0:12}…"
done

# ── Manifest'i güncelle ─────────────────────────────────────────────────────
ARGS=()
for satir in "${PLATFORMLAR[@]}"; do
  IFS='|' read -r AD _ _ <<< "$satir"
  [[ -n "${SONUC["$AD|asset"]:-}" ]] || continue
  ARGS+=("$AD" "${SONUC["$AD|asset"]}" "${SONUC["$AD|sha"]}" "${SONUC["$AD|raw"]}" "${SONUC["$AD|dl"]}")
done

python3 - "$MANIFEST" "$PYDEPS_ID" "$EXTRACT_TO" "$PRESENCE_DIR" "$RELEASE_TAG" "${ARGS[@]}" <<'PY'
import json, sys
mpath, pid, extract_to, presence_dir, tag = sys.argv[1:6]
rest = sys.argv[6:]
with open(mpath, encoding="utf-8") as f:
    data = json.load(f)

base = data["releaseBase"]
# 🔑 Kayıt `plannedModels` altına yazılır, `models` altına DEĞİL.
# Manifest'in kendi kuralı: *"`models` altındaki her girdi indirilebilir sayılır;
# url'i geçersiz bir girdi UI'da 'indir' olarak görünüp indirme anında patlar."*
# Asset henüz release'e yüklenmemişken url 404'tür. `--dogrula` yüklemeyi ÖLÇÜP
# terfi ettirir — kanıtsız terfi yok.
kayit = data.setdefault("plannedModels", {}).get(pid) or data.get("models", {}).get(pid) or {
    "name": "Yüz Tanıma Kütüphanesi",
    "feature": "Yüz tanıma (Free)",
    "i18n": {"en": {"name": "Face Recognition Library", "feature": "Face recognition (Free)"}},
}
kayit["kind"] = "pydeps"          # model-manager.js bunu görünce assets{} bekler
kayit["presenceDir"] = presence_dir
kayit["extractTo"] = extract_to
kayit.setdefault("tier", "lite")
kayit["_note"] = ("Python paket ağacı — PLATFORMA ÖZEL (derlenmiş .so/.pyd taşır). "
                  "backend sys.path'e SONA ekler; kutudaki paketleri gölgelemez. "
                  "Üretici: scripts/build-pydeps-package.sh")

assets = kayit.setdefault("assets", {})
for i in range(0, len(rest), 5):
    ad, asset, sha, raw, dl = rest[i:i+5]
    assets[ad] = {
        "asset": asset,
        "url": f"{base}/{tag}/{asset}",
        "sha256": sha,
        "sizeBytes": int(raw),
        "downloadBytes": int(dl),
    }

data.setdefault("plannedModels", {})[pid] = kayit
data.get("models", {}).pop(pid, None)   # yanlışlıkla models'a düşmüşse geri al
with open(mpath, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"\n✓ Manifest güncellendi: plannedModels.{pid} → {', '.join(sorted(assets))}")
print("  (henüz 'models' altında DEĞİL — asset yüklenip `--dogrula` geçene kadar indirilemez)")
PY

echo ""
echo "▸ SONRAKİ ADIM — asset'leri release'e yükle (geliştirici):"
for satir in "${PLATFORMLAR[@]}"; do
  IFS='|' read -r AD _ _ <<< "$satir"
  [[ -n "${SONUC["$AD|asset"]:-}" ]] || continue
  echo "    gh release upload $RELEASE_TAG \"$OUT_DIR/${SONUC["$AD|asset"]}\" --repo $REPO --clobber"
done
echo ""
echo "  ⚠️ Yüklenmeden manifest'teki url 404 verir — model-manager.js"
echo "     'İndirme başarısız — sunucu HTTP 404 döndü' der (sessizce geçmez)."

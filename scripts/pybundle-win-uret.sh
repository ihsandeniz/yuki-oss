#!/usr/bin/env bash
# Windows Python kutusunu (backend/pybundle-win/) LINUX'TA sıfırdan üretir — çapraz kurulum.
#
#   bash scripts/pybundle-win-uret.sh            # yoksa üret
#   bash scripts/pybundle-win-uret.sh --zorla    # varsa silip yeniden üret
#
# Linux kutusunun (pybundle-uret.sh) Windows ikizi. Windows makinesi ya da wine GEREKMEZ:
#   1. python-build-standalone'un Windows (msvc) CPython'u indirilir, sha256 denetlenir.
#   2. backend/pybundle-win-kilit.txt'teki paketler `uv pip install --python-platform
#      x86_64-pc-windows-msvc` ile YALNIZ hazır Windows wheel'lerinden Lib/site-packages'a
#      açılır (--no-deps: liste zaten tam envanter, bkz. scripts/bundle-envanter.py).
#   3. Kutudaki eski pip silinir (kilitteki pip kurulur) — yoksa iki pip dist-info'su
#      yan yana kalır, bundle-envanter.py "ÇİFT KAYIT" der.
#   4. vendor-msvc-runtime.py: temiz Windows'ta çözülemeyen MSVC C++ importlarını kapatır
#      (yoksa VC++ Redistributable'sız makinede onnxruntime/OCR ölür — ayrıntı o betikte).
#
# Kutu .gitignore'da (yüzlerce MB). Sınav: backend/tests/test_bundle_kilit.py (kilit ↔ kutu)
# + backend/tests/test_msvc_runtime.py + scripts/test_windows_paket.py.
set -euo pipefail

KOK="$(cd "$(dirname "$0")/.." && pwd)"
HEDEF="$KOK/backend/pybundle-win"
KILIT="$KOK/backend/pybundle-win-kilit.txt"

PY_SURUM="3.14.3"
PBS_ETIKET="20260310"
ARSIV="cpython-${PY_SURUM}+${PBS_ETIKET}-x86_64-pc-windows-msvc-install_only.tar.gz"
SHA256="a9bc849fb4812463fddf824f43fdca88e894406545fa320c6230fa82b331ef32"
URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_ETIKET}/${ARSIV}"

if [[ "${1:-}" == "--zorla" ]]; then rm -rf "$HEDEF"; fi
if [[ -f "$HEDEF/python.exe" ]]; then
  echo "✓ pybundle-win zaten var ($HEDEF) — yeniden üretmek için --zorla"
  exit 0
fi
command -v uv >/dev/null || { echo "✗ uv gerekli (https://docs.astral.sh/uv/) — pip Windows wheel'ini Linux'ta hedef dizine açamaz" >&2; exit 1; }

GECICI="$(mktemp -d)"
trap 'rm -rf "$GECICI"' EXIT

echo "→ Windows CPython $PY_SURUM indiriliyor ($PBS_ETIKET)"
curl -fsSL "$URL" -o "$GECICI/$ARSIV"
echo "$SHA256  $GECICI/$ARSIV" | sha256sum -c --quiet
tar -xzf "$GECICI/$ARSIV" -C "$GECICI"          # → $GECICI/python/{python.exe,Lib,DLLs,…}
[[ -f "$GECICI/python/python.exe" ]] || { echo "✗ arşivde python.exe yok" >&2; exit 1; }

SP="$GECICI/python/Lib/site-packages"
# Gelen pip'i sil: kilitteki pip sürümü aşağıda kurulur (tek dist-info kalsın).
rm -rf "$SP"/pip "$SP"/pip-*.dist-info

grep -vE '^\s*(#|$)' "$KILIT" > "$GECICI/kilit.txt"
echo "→ paketler Windows wheel'lerinden kuruluyor ($(wc -l < "$GECICI/kilit.txt") paket)"
uv pip install \
  --target "$SP" \
  --python-platform x86_64-pc-windows-msvc \
  --python-version "${PY_SURUM%.*}" \
  --no-deps --link-mode copy --quiet \
  -r "$GECICI/kilit.txt"
# Kaynaktan derlemeye izin var, çünkü bazı paketler yalnız sdist (ör. antlr4-python3-runtime 4.9.3).
# Ama Linux'ta derlenen her şey saf Python olmak ZORUNDA. Aşağıdaki iki kapı Linux ikilisi
# sızmasını durdurur: .so dosyası olmamalı, her WHEEL etiketi ya win_amd64 ya da py*-none-any olmalı.

# uv --target'ın bıraktığı Linux'a özgü artık yok; yine de Windows'ta anlamsız .so olmamalı.
if find "$SP" -name '*.so' | grep -q .; then
  echo "✗ kutuda Linux .so dosyası var — yanlış platform wheel'i geldi" >&2
  find "$SP" -name '*.so' | head >&2
  exit 1
fi

YANLIS_ETIKET="$(grep -h '^Tag:' "$SP"/*.dist-info/WHEEL | grep -vE 'win_amd64|-none-any$' || true)"
if [[ -n "$YANLIS_ETIKET" ]]; then
  echo "✗ Windows'a uymayan wheel etiketi:" >&2; echo "$YANLIS_ETIKET" | sort -u >&2
  exit 1
fi

mv "$GECICI/python" "$HEDEF"

echo "→ MSVC C++ runtime gömülüyor"
python3 "$KOK/scripts/vendor-msvc-runtime.py"

echo "✓ pybundle-win hazır: $HEDEF ($(du -sh "$HEDEF" | cut -f1))"

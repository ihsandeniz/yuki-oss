#!/usr/bin/env bash
# Linux Python kutusunu (backend/pybundle/) sıfırdan üretir.
#
#   bash scripts/pybundle-uret.sh            # yoksa üret
#   bash scripts/pybundle-uret.sh --zorla    # varsa silip yeniden üret
#
# Kutu .gitignore'da (yüzlerce MB). İçerik backend/pybundle-kilit.txt'ten gelir:
# python-build-standalone CPython + kilitli paket listesi, bağımlılık çözümü YOK
# (--no-deps: liste zaten tam envanter, bkz. scripts/bundle-envanter.py).
#
# 🔴 PYTHONNOUSERSITE=1 + --ignore-installed zorunlu: yoksa pip makinedeki
# ~/.local paketlerini "kurulu" sayıp kutuya koymaz, motor açılışta
# ModuleNotFoundError ile düşer (2026-10-18 ölçümü: 25 paket eksik kaldı).
set -euo pipefail

KOK="$(cd "$(dirname "$0")/.." && pwd)"
HEDEF="$KOK/backend/pybundle"
KILIT="$KOK/backend/pybundle-kilit.txt"

PY_SURUM="3.14.3"
PBS_ETIKET="20260310"
ARSIV="cpython-${PY_SURUM}+${PBS_ETIKET}-x86_64-unknown-linux-gnu-install_only.tar.gz"
SHA256="26009c96926828784c81e36727f4af950c9c4bc9368dc744280a6345c38e95e8"
URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_ETIKET}/${ARSIV}"

if [[ "${1:-}" == "--zorla" ]]; then rm -rf "$HEDEF"; fi
if [[ -x "$HEDEF/bin/python3" ]]; then
  echo "✓ pybundle zaten var ($HEDEF) — yeniden üretmek için --zorla"
  exit 0
fi

GECICI="$(mktemp -d)"
trap 'rm -rf "$GECICI"' EXIT

echo "→ CPython $PY_SURUM indiriliyor ($PBS_ETIKET)"
curl -fsSL "$URL" -o "$GECICI/$ARSIV"
echo "$SHA256  $GECICI/$ARSIV" | sha256sum -c --quiet
tar -xzf "$GECICI/$ARSIV" -C "$GECICI"          # → $GECICI/python/
mv "$GECICI/python" "$HEDEF"

# pip kutuda hazır geliyor: kilitteki sürüme YERİNDE yükselt (eskisini kaldırır).
# --ignore-installed ile kurulursa iki pip dist-info'su yan yana kalır ve
# bundle-envanter.py "ÇİFT KAYIT" der (test_bundle_kilit kırılır).
PIP_SATIRI="$(grep -E '^pip==' "$KILIT" || true)"
if [[ -n "$PIP_SATIRI" ]]; then
  PYTHONNOUSERSITE=1 "$HEDEF/bin/python3" -s -m pip install -q --disable-pip-version-check "$PIP_SATIRI"
fi
grep -vE '^pip==' "$KILIT" > "$GECICI/kilit-pipsiz.txt"

echo "→ paketler kuruluyor ($(grep -cvE '^\s*(#|$)' "$GECICI/kilit-pipsiz.txt") paket)"
PYTHONNOUSERSITE=1 "$HEDEF/bin/python3" -s -m pip install \
  --no-deps --ignore-installed --no-warn-script-location --disable-pip-version-check \
  -r "$GECICI/kilit-pipsiz.txt"

# Duman testi: kutu kendi başına motorun ana bağımlılıklarını görebiliyor mu
PYTHONNOUSERSITE=1 "$HEDEF/bin/python3" -s -c "import fastapi, uvicorn, pydantic, typing_inspection, anthropic" \
  && echo "✓ pybundle hazır: $HEDEF ($(du -sh "$HEDEF" | cut -f1))"

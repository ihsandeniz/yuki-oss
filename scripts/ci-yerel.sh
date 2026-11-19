#!/usr/bin/env bash
# ci-yerel.sh — .github/workflows/pytest.yml'nin YEREL AYNASI (CI FAZ 1, 2026-10-10).
#
# Ajanlar push etmediği için GitHub'daki CI çoğu zaman koşmaz; bu betik aynı adımları
# temiz bir kopyada koşar: `git archive HEAD` (yalnız commit'li dosyalar, `.env` YOK),
# taze python3.14 venv, `requirements.txt` + `requirements-dev.txt`, gömme modeli
# (indir + sha256), `pytest -q`, `compileall app`, electron `node --test`.
# Commit'lenmemiş değişiklik test EDİLMEZ — CI de onu görmez.
#
# Kullanım:
#   scripts/ci-yerel.sh                 # HEAD
#   scripts/ci-yerel.sh <commit|dal>    # başka bir ref
# Ortam:
#   CI_YEREL_DIZIN   çalışma dizini (varsayılan: mktemp; koşu sonunda silinir)
#   CI_YEREL_ONBELLEK model önbelleği (varsayılan: ~/.cache/yuki-ci)
#   CI_YEREL_TUT=1   çalışma dizinini silme
#
# Ağır iş: vault'ta `python3 projects/vault-araclari/donanim.py kos -- scripts/ci-yerel.sh` ile koş.
# pytest.yml değişirse bu dosyayı da güncelle. Model adresi + sha256 ikisinde de YAZILMAZ:
# tek kaynak electron/models-manifest.json, indirici scripts/model-getir.py (gizli depoda `gh` ile).
set -euo pipefail

REF="${1:-HEAD}"
DEPO="$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)"
ONBELLEK="${CI_YEREL_ONBELLEK:-$HOME/.cache/yuki-ci}"
if [[ -n "${CI_YEREL_DIZIN:-}" ]]; then
  IS="$CI_YEREL_DIZIN"; mkdir -p "$IS"
else
  IS="$(mktemp -d -t yuki-ci-yerel.XXXXXX)"
fi
temizle() { [[ "${CI_YEREL_TUT:-0}" == 1 || -n "${CI_YEREL_DIZIN:-}" ]] || rm -rf "$IS"; }
trap temizle EXIT

PY="${CI_YEREL_PYTHON:-python3.14}"
command -v "$PY" >/dev/null || { echo "❌ $PY yok (CI 3.14 kullanıyor)"; exit 2; }

# .env'den sızabilecek ayarlar ortamda da olmasın — CI runner'ında hiçbiri yok.
unset MEMORY_BACKEND MEMORY_ENABLED DATABASE_URL OPENROUTER_API_KEY EMBED_BACKEND EMBED_ONNX_DIR ALICE_DATA_DIR || true

BASLA=$(date +%s)
adim() { echo; echo "── $1  (+$(( $(date +%s) - BASLA )) sn)"; }

adim "kopya: git archive $REF → $IS/kod"
rm -rf "$IS/kod"; mkdir -p "$IS/kod"
git -C "$DEPO" archive "$REF" | tar -x -C "$IS/kod"
echo "commit: $(git -C "$DEPO" rev-parse --short "$REF")"

adim "venv + bağımlılıklar ($PY)"
rm -rf "$IS/venv"
"$PY" -m venv "$IS/venv"
"$IS/venv/bin/python" -m pip install -q --upgrade pip
"$IS/venv/bin/pip" install -q -r "$IS/kod/backend/requirements.txt" -r "$IS/kod/backend/requirements-dev.txt"
"$IS/venv/bin/python" -m playwright install chromium   # pytest.yml "Playwright chromium" aynası
KURULUM=$(( $(date +%s) - BASLA ))

adim "gömme modeli ($ONBELLEK)"
ONNX_SHA256="$("$PY" "$IS/kod/scripts/model-getir.py" embedding-onnx --sha --manifest "$IS/kod/electron/models-manifest.json")"
MODEL="$ONBELLEK/$ONNX_SHA256/embedding-onnx"
if [[ ! -f "$MODEL/model_int8.onnx" || ! -f "$MODEL/tokenizer.json" ]]; then
  "$PY" "$IS/kod/scripts/model-getir.py" embedding-onnx "$ONBELLEK/$ONNX_SHA256" --manifest "$IS/kod/electron/models-manifest.json"
else
  echo "önbellekte: $MODEL"
fi
ls -l "$MODEL/model_int8.onnx" "$MODEL/tokenizer.json"

SONUC=0
adim "pytest (tam takım)"
T0=$(date +%s)
( cd "$IS/kod/backend" && EMBED_ONNX_DIR="$MODEL" YUKI_TARAYICI_ZORUNLU=1 "$IS/venv/bin/python" -m pytest -q -p no:cacheprovider ) || SONUC=1
PYTEST_SN=$(( $(date +%s) - T0 ))

adim "compileall app"
( cd "$IS/kod/backend" && "$IS/venv/bin/python" -m compileall -q app ) || SONUC=1

adim "electron: node --test"
( cd "$IS/kod/electron" && node --test *.test.js ) > "$IS/electron.txt" 2>&1 || SONUC=1
tail -9 "$IS/electron.txt"

TOPLAM=$(( $(date +%s) - BASLA ))
echo
echo "════ ci-yerel: $([[ $SONUC == 0 ]] && echo YEŞİL || echo KIRMIZI) · toplam ${TOPLAM} sn (kurulum ${KURULUM} sn · pytest ${PYTEST_SN} sn) · ref $REF"
exit $SONUC

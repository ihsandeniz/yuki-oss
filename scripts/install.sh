#!/usr/bin/env bash
# Yuki — Linux kaynak kurulumu (indir, oku, çalıştır — boruyla kabuğa verme yok).
#
#   curl -LO https://github.com/ihsandeniz/yuki-oss/releases/download/<sürüm>/install.sh
#   less install.sh && bash install.sh
#   ya da klondan:  bash scripts/install.sh
#
# Ne yapar: kaynağı (bu klon ya da --kaynak <tar.gz>) ~/.local/share/yuki altına kopyalar,
# orada Python 3.12+ ile venv kurar (~1.3 GB paket), ~/.local/bin/yuki başlatıcısını ve
# menü girdisini yazar. sudo istemez, sistem dosyasına dokunmaz. Kaldırma: --kaldir.
#
# Seçenekler:  --onek <dizin>   kurulum yeri (varsayılan $XDG_DATA_HOME/yuki)
#              --kaynak <dosya> kaynak tar.gz (varsayılan: betiğin bulunduğu klon)
#              --menusuz        .desktop girdisi yazma
#              --kaldir         kurulumu ve başlatıcıyı sil (kullanıcı verisi ~/.yuki kalır)
# Çıkış: 0 tamam · 1 kurulum hatası · 2 kullanım/ön koşul hatası
set -euo pipefail

VERI="${XDG_DATA_HOME:-$HOME/.local/share}"
ONEK="$VERI/yuki"
BIN="$HOME/.local/bin"
KAYNAK=""
MENU=1
KALDIR=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --onek)    ONEK="${2:?--onek dizin ister}"; shift 2 ;;
    --kaynak)  KAYNAK="${2:?--kaynak dosya ister}"; shift 2 ;;
    --menusuz) MENU=0; shift ;;
    --kaldir)  KALDIR=1; shift ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "bilinmeyen seçenek: $1" >&2; exit 2 ;;
  esac
done

MASAUSTU="$VERI/applications/yuki.desktop"

# Güvenlik kapısı: önek boş, / ya da $HOME olamaz (rm -rf burada koşar).
case "$(realpath -m "$ONEK")" in
  ""|/|"$(realpath -m "$HOME")") echo "🔴 tehlikeli önek: $ONEK" >&2; exit 2 ;;
esac

if [[ $KALDIR == 1 ]]; then
  rm -rf -- "$ONEK"; rm -f -- "$BIN/yuki" "$MASAUSTU"
  echo "✓ Yuki kaldırıldı (kullanıcı verisi ~/.yuki duruyor)"; exit 0
fi

# Python 3.12+ bul.
PY=""
for aday in python3.14 python3.13 python3.12 python3; do
  if command -v "$aday" >/dev/null && "$aday" -c 'import sys; sys.exit(sys.version_info < (3,12))' 2>/dev/null; then
    PY="$(command -v "$aday")"; break
  fi
done
[[ -n "$PY" ]] || { echo "🔴 Python 3.12 ya da yenisi gerekli (python3 --version)" >&2; exit 2; }
"$PY" -c 'import venv, ensurepip' 2>/dev/null || { echo "🔴 venv modülü yok — Debian/Ubuntu: sudo apt install python3-venv" >&2; exit 2; }

# Kaynağı yerleştir (eski kurulumu yeni klasörle değiştir; venv yeniden kurulur).
YENI="$ONEK.yeni.$$"
trap 'rm -rf -- "$YENI"' EXIT
mkdir -p "$YENI"
if [[ -n "$KAYNAK" ]]; then
  tar -xzf "$KAYNAK" -C "$YENI" --strip-components="${YUKI_TAR_STRIP:-1}"
else
  KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  if git -C "$KOK" rev-parse >/dev/null 2>&1; then
    git -C "$KOK" archive --format=tar HEAD | tar -x -C "$YENI"   # yalnız izlenen dosyalar
  else
    cp -a "$KOK/." "$YENI/"
  fi
fi
[[ -f "$YENI/backend/requirements.txt" ]] || { echo "🔴 kaynakta backend/requirements.txt yok" >&2; exit 1; }

echo "→ paketler kuruluyor (~1.3 GB, birkaç dakika)…"
"$PY" -m venv "$YENI/backend/venv"
"$YENI/backend/venv/bin/pip" install --disable-pip-version-check -q -r "$YENI/backend/requirements.txt"

rm -rf -- "$ONEK"; mv "$YENI" "$ONEK"; trap - EXIT

mkdir -p "$BIN"
cat > "$BIN/yuki" <<BAS
#!/usr/bin/env bash
# Yuki başlatıcısı (install.sh yazdı). Port: YUKI_PORT (varsayılan 8001).
cd "$ONEK/backend"
export MEMORY_BACKEND="\${MEMORY_BACKEND:-sqlite}"
PORT="\${YUKI_PORT:-8001}"
if [[ "\${1:-}" != "--no-ui" ]]; then
  ( for _ in \$(seq 60); do curl -fs "http://127.0.0.1:\$PORT/health" >/dev/null 2>&1 && exec xdg-open "http://127.0.0.1:\$PORT/ui"; sleep 1; done ) >/dev/null 2>&1 &
fi
exec ./venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "\$PORT"
BAS
chmod +x "$BIN/yuki"

if [[ $MENU == 1 ]]; then
  mkdir -p "$(dirname "$MASAUSTU")"
  printf '[Desktop Entry]\nType=Application\nName=Yuki\nComment=Yuki assistant\nExec=%s\nTerminal=true\nCategories=Utility;\n' "$BIN/yuki" > "$MASAUSTU"
fi

echo "✓ Yuki kuruldu: $ONEK"
echo "  Başlat: yuki   (yalnız motor: yuki --no-ui) → http://127.0.0.1:${YUKI_PORT:-8001}/ui"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "  ! $BIN PATH'te değil — ekle: export PATH=\"$BIN:\$PATH\"";; esac

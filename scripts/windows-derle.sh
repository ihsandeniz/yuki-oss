#!/usr/bin/env bash
# Temiz klondan tek komutla Windows kurulum paketi — LINUX'TA (çapraz derleme):
#
#   bash scripts/windows-derle.sh
#
# Adımlar: Windows Python kutusu (pybundle-win, çapraz kurulum) → (varsa) süreç bekçisi →
# npm ci → electron-builder --win (nsis + zip).
# Çıktı: electron/dist/Yuki-Setup-<sürüm>.exe (kullanıcı başına kurulum, yönetici izni istemez)
#        + electron/dist/Yuki-<sürüm>-win-x64-lite.zip (uygulama içi tam güncellemenin indirdiği varlık)
#        + electron/dist/win-unpacked/ (kurulmamış hâli; sınav bunu kullanır)
# Gerekenler: bash, curl, python3, uv, node 20+, npm, wine (64 bit), Xvfb. Windows makinesi GEREKMEZ.
#
# 🔴 NEDEN wine'lı makensis: electron-builder'ın indirdiği Linux makensis'i (nsis-3.0.4.1
#    paketi, sürüm dizesi "v27-Nov-2019.cvs") kendi ürettiği betikteki `!addincludedir`'i
#    tanımıyor → "Invalid command" ile durur (ölçüldü 2026-11-12, electron-builder 24.13.3;
#    26.18.1 varsayılan olarak aynı nsis-3.0.4.1 arşivini indirir).
#    Aynı paketteki Windows makensis.exe (v3.04) wine altında sorunsuz. ELECTRON_BUILDER_NSIS_DIR
#    ile geçici bir kopya veriyoruz; içindeki linux/makensis, wine makensis.exe'yi çağıran
#    küçük bir sarmalayıcı.
# 🔴 NEDEN ayrı WINEPREFIX + sanal ekran: electron-builder exe'ye simge yazmak için (rcedit)
#    wine'ı çağırır. Varsayılan ~/.wine'ı ilk kez kurarken Mono/Gecko penceresi açıp beklenir
#    (gerçek ekranda takılı kalan bir pencere). Kendi önekimiz + mscoree/mshtml kapalı + Xvfb.
set -euo pipefail

KOK="$(cd "$(dirname "$0")/.." && pwd)"
cd "$KOK"

# NSIS önbelleği iki düzende olabilir (eski önbellek dizini 24'ten kalmış olabilir):
#   electron-builder 24: <önbellek>/nsis/nsis-3.0.4.1/makensis.exe
#   electron-builder 26: <önbellek>/nsis-3.0.4.1/nsis-3.0.4.1-<ek>/makensis.exe
# Bulunanı yazar, yoksa boş döner. `--nsis-bul` yalnız bunu yapar (test_windows_paket.py W8).
nsis_onbellek_bul() {
  local kok="${ELECTRON_BUILDER_CACHE:-$HOME/.cache/electron-builder}" d
  for d in "$kok"/nsis-3.0.4.1/nsis-3.0.4.1-* "$kok/nsis/nsis-3.0.4.1"; do
    [[ -f "$d/makensis.exe" && -f "$d/elevate.exe" ]] && { printf '%s\n' "$d"; return 0; }
  done
  return 0
}
if [[ "${1:-}" == "--nsis-bul" ]]; then nsis_onbellek_bul; exit 0; fi

for arac in uv wine Xvfb 7z perl; do
  command -v "$arac" >/dev/null || { echo "✗ '$arac' gerekli (README → Build the Windows installer)" >&2; exit 1; }
done

bash scripts/pybundle-win-uret.sh
python3 scripts/vendor-msvc-runtime.py --check

# Süreç bekçisi isteğe bağlı (Linux ile aynı kural): ikili yoksa boş klasörle devam.
if [[ ! -f electron/bekci-bin/win/yuki-bekci.exe ]]; then
  echo "• süreç bekçisi (Windows) yok — atlanıyor (isteğe bağlı; scripts/bekci-getir.py win --run <id>)"
  mkdir -p electron/bekci-bin/win
fi

GECICI="$(mktemp -d)"
XVFB_PID=""
temizle() {
  [[ -n "$XVFB_PID" ]] && kill "$XVFB_PID" 2>/dev/null || true
  WINEPREFIX="$GECICI/wine" wineserver -k 2>/dev/null || true
  rm -rf "$GECICI"
}
trap temizle EXIT

export WINEPREFIX="${YUKI_WINEPREFIX:-$GECICI/wine}"
export WINEDEBUG=-all WINEARCH=win64 WINEDLLOVERRIDES="mscoree,mshtml="
# Sanal ekran: -displayfd boş bir numara seçer ve HAZIR olunca yazar (rastgele numara çakışabilir,
# beklemesiz başlatmada wine ekran gelmeden koşabilir).
Xvfb -displayfd 3 -screen 0 1280x800x24 -nolisten tcp 3>"$GECICI/ekran" >/dev/null 2>&1 &
XVFB_PID=$!
for _ in $(seq 100); do [[ -s "$GECICI/ekran" ]] && break; sleep 0.1; done
[[ -s "$GECICI/ekran" ]] || { echo "✗ Xvfb açılmadı" >&2; exit 1; }
export DISPLAY=":$(tr -dc 0-9 < "$GECICI/ekran")"

cd electron
npm ci --no-audit --no-fund
python3 ../scripts/update_payload.py shell-id

# NSIS: önbellekte varsa kopyası, yoksa electron-builder'ın kendi indirdiği arşiv (aynı URL —
# 26'da app-builder-lib/out/toolsets/windows.js::getLegacyNsisBin, varsayılan toolsets.nsis "0.0.0")
# geçici klasöre açılır. 26 override kökünde elevate.exe'yi de arar; eski arşivde kökte var.
NSIS_ONBELLEK="$(nsis_onbellek_bul)"
if [[ -z "$NSIS_ONBELLEK" ]]; then
  echo "• NSIS önbellekte yok — indiriliyor"
  mkdir -p "$GECICI/nsis-indir"
  curl -fsSL https://github.com/electron-userland/electron-builder-binaries/releases/download/nsis-3.0.4.1/nsis-3.0.4.1.7z \
    -o "$GECICI/nsis-indir/nsis.7z"
  echo "VKMiizYdmNdJOWpRGz4trl4lD++BvYP2irAXpMilheUP0pc93iKlWAoP843Vlraj8YG19CVn0j+dCo/hURz9+Q==  $GECICI/nsis-indir/nsis.7z" \
    | python3 -c 'import base64,hashlib,sys; h,p=sys.stdin.read().split(); sys.exit(0 if base64.b64encode(hashlib.sha512(open(p,"rb").read()).digest()).decode()==h else 1)' \
    || { echo "✗ NSIS arşivi sha512 tutmadı" >&2; exit 1; }
  7z x -y -o"$GECICI/nsis" "$GECICI/nsis-indir/nsis.7z" >/dev/null
else
  cp -a "$NSIS_ONBELLEK" "$GECICI/nsis"
fi
mv "$GECICI/nsis/linux/makensis" "$GECICI/nsis/linux/makensis.linux-bozuk"
cat > "$GECICI/nsis/linux/makensis" <<'SARMAL'
#!/usr/bin/env bash
# electron-builder'ın Linux makensis'i yerine wine'daki Windows makensis.exe (bkz. windows-derle.sh).
# electron-builder betiğe ve -D tanımlarına Unix mutlak yolları yazar ("/home/…"); Windows makensis
# bunları bulamaz ("!include: could not find"), "Z:/home/…" de bulamaz → "Z:\home\…" (ters eğik
# çizgi şart, ölçüldü 2026-11-12). Seçenekler (/r, /oname=) dokunulmaz: yalnız bilinen kök
# dizinlerle başlayan yollar çevrilir; tırnaklı yol kapanış tırnağına kadar, tırnaksız boşluğa kadar.
DIR="$(cd "$(dirname "$0")/.." && pwd)"
cevir() {
  perl -pe '
    BEGIN { $k = q{(?:home|tmp|var|opt|mnt|usr|root|run|srv)} }
    sub w { my ($on, $yol) = @_; $yol =~ s#/#\\#g; return $on . "Z:\\" . $yol }
    s{(")/($k/[^"]*)}{w($1, $2)}ge;
    s{(^|[=\x27 ])/($k/[^\s"\x27]*)}{w($1, $2)}ge;'
}
args=()
for a in "$@"; do args+=("$(printf '%s\n' "$a" | cevir)"); done
cevir | exec wine "$DIR/makensis.exe" "${args[@]}"
SARMAL
chmod +x "$GECICI/nsis/linux/makensis"
export ELECTRON_BUILDER_NSIS_DIR="$GECICI/nsis"

npx electron-builder --win --publish never --config electron-builder-win.yml
ls -la dist/Yuki-Setup-*.exe dist/*-win-x64-lite.zip

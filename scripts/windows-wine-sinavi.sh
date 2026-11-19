#!/usr/bin/env bash
# Windows kurulum sınavı (wine) — yabancı biri Yuki-Setup.exe'yi Python'suz bir Windows'ta
# kurup açarsa ne olur? Gerçek Windows değil, wine: BOŞ bir wine öneki (içinde Python yok),
# sanal ekran (Xvfb), normal kullanıcı. Kurulum sessiz kipte (/S) — NSIS kullanıcı başına kurar.
#
#   bash scripts/windows-wine-sinavi.sh [dist/Yuki-Setup-<sürüm>.exe]
#
# Ölçülenler (AppImage kap sınavıyla aynı ölçüm betiği: appimage_kap_olcum.py):
#   kurulum (Yuki.exe kullanıcı dizinine indi) · pencere · motor (/health 200) · arayüz motordan ·
#   sihirbaz · JS istisnası 0 · motor = paketteki pybundle-win\python.exe · önekte başka python yok.
# Ekranlar: 1280 ve 390 genişlik, normal (animasyonlu) mod.
# Ortam: YUKI_SINAV_SURE (sn, 600) · YUKI_CDP_PORT (9333; 9222 tarayıcıyla çakışabilir)
# Gerekenler: wine (64 bit), Xvfb, python3 (ölçüm için geçici venv'e playwright kurulur).
# Boş yer: geçici dizinde ~3 GB (wine öneki + kurulu uygulama). /tmp küçük bir tmpfs ise
# TMPDIR=<geniş dizin> ver — dolu diskte kurulum dosyası HİÇBİR ŞEY kurmadan çıkış 2/53 verir
# (ölçüldü 11-12, kota dolu /tmp'de); kurulum_rc satırı bunu gösterir.
#
# Bu sınav gerçek Windows'un yerini TUTMAZ: wine kendi msvcp140/vcruntime'ını getirir
# (VC++ redist'siz Windows'u ölçmez), Defender/SmartScreen yok. Bkz. RAPOR "ölçülmeyen".
set -uo pipefail

KOK="$(cd "$(dirname "$0")/.." && pwd)"
KUR="${1:-$(ls -t "$KOK"/electron/dist/Yuki-Setup-*.exe 2>/dev/null | head -1)}"
SURE="${YUKI_SINAV_SURE:-600}"
CDP_PORT="${YUKI_CDP_PORT:-9333}"
[[ -f "$KUR" ]] || { echo "🔴 kurulum dosyası bulunamadı: ${KUR:-<yok>}" >&2; exit 2; }

CIKTI="$KOK/electron/dist/wine-sinavi"
mkdir -p "$CIKTI"
# Önceki koşunun ekranları/günlüğü kalırsa bozuk bir paket eski ekranlarla "ekran var" görünür.
find "$CIKTI" -maxdepth 1 -type f \( -name '*.png' -o -name '*.log' -o -name 'istisnalar.json' \) -delete
GECICI="$(mktemp -d)"
UYG_PID=""; XVFB_PID=""
temizle() {
  [[ -n "$UYG_PID" ]] && kill "$UYG_PID" 2>/dev/null
  WINEPREFIX="$GECICI/onek" wineserver -k 2>/dev/null
  [[ -n "$XVFB_PID" ]] && kill "$XVFB_PID" 2>/dev/null
  rm -rf "$GECICI"
}
trap temizle EXIT

export WINEPREFIX="$GECICI/onek" WINEDEBUG=-all WINEARCH=win64 WINEDLLOVERRIDES="mscoree,mshtml="
# Sanal ekran: -displayfd boş bir numara seçer ve HAZIR olunca yazar (rastgele numara çakışabilir,
# beklemesiz başlatmada wine ekran gelmeden koşabilir).
Xvfb -displayfd 3 -screen 0 1400x900x24 -nolisten tcp 3>"$GECICI/ekran" >/dev/null 2>&1 &
XVFB_PID=$!
for _ in $(seq 100); do [[ -s "$GECICI/ekran" ]] && break; sleep 0.1; done
[[ -s "$GECICI/ekran" ]] || { echo "✗ Xvfb açılmadı" >&2; exit 1; }
export DISPLAY=":$(tr -dc 0-9 < "$GECICI/ekran")"

echo "Windows (wine) sınavı · $(basename "$KUR") ($(du -h "$KUR" | cut -f1)) · $(wine --version) · çıktı=$CIKTI"
LOG="$CIKTI/sinav.log"
: > "$LOG"
not() { echo "SINAV $*" | tee -a "$LOG"; }

timeout 300 wineboot --init >/dev/null 2>&1; wineserver -w
# Önekte Python yok (kullanıcının makinesinde Python olmadığı varsayımı).
not onek_python "$(find "$WINEPREFIX/drive_c" -iname 'python*.exe' 2>/dev/null | wc -l)"

# Kullanıcının yaptığı: kurulum dosyasını çalıştırmak (burada sessiz kip).
# 🔴 powershell.exe=d: wine'ın powershell.exe'si komut çalıştırmayan bir kabuk, HER komuta 0 döner
# (`-C "exit 1"` → 0, ölçüldü 2026-11-12, wine 11.21). electron-builder 26'nın NSIS'i "uygulama açık
# mı" denetimini PowerShell varsa onunla yapar → kabuk "Yuki açık" der, sessiz kurulum kapatmayı
# dener, sonunda IDCANCEL ile çıkar: çıkış 2, hiçbir şey kurulmaz. Kabuk kapatılınca NSIS 26'nın
# kendi yedek yoluna (tasklist | findstr) geçer; o wine'da doğru cevap verir. Bu, PowerShell'i
# kapalı bir Windows'a denk; gerçek PowerShell'li yol wine'da ölçülemez. Yalnız kurulum adımında.
WINEDLLOVERRIDES="$WINEDLLOVERRIDES;powershell.exe=d" timeout 600 wine "$KUR" /S >"$CIKTI/kurulum.log" 2>&1
not kurulum_rc $?
wineserver -w
EXE="$(find "$WINEPREFIX/drive_c/users" -iname 'Yuki.exe' -path '*Programs*' 2>/dev/null | head -1)"
not kurulum "${EXE:+ok ${EXE#"$WINEPREFIX"/}}"
[[ -n "$EXE" ]] || { echo "🔴 kurulum Yuki.exe bırakmadı"; exit 1; }
not kisayol "$(find "$WINEPREFIX/drive_c/users" -iname 'Yuki.lnk' 2>/dev/null | wc -l)"

# playwright 1.49.1 (kap sınavının sürümü) ana makinenin Python 3.14'ünde kurulamıyor: greenlet
# derlenemiyor (ölçüldü 11-12). Ana makinede 3.14 tekerleği olan 1.59.0 kullanılır; yalnız CDP
# bağlantısı için (tarayıcı indirilmez).
python3 -m venv "$GECICI/olcum-venv" >/dev/null 2>&1 && "$GECICI/olcum-venv/bin/pip" -q install playwright==1.59.0 >"$CIKTI/pw.log" 2>&1
not olcum_araci $?

wine "$EXE" --remote-debugging-port="$CDP_PORT" >"$CIKTI/uygulama.log" 2>&1 &
UYG_PID=$!
YUKI_CDP="http://127.0.0.1:$CDP_PORT" timeout "$SURE" "$GECICI/olcum-venv/bin/python" -I \
  "$KOK/scripts/appimage_kap_olcum.py" "$CIKTI" 2>&1 | tee -a "$LOG" | grep -E "^ADIM"
not olcum_rc "${PIPESTATUS[0]}"
# Motor süreci: wine altında Windows yolu (…\pybundle-win\python.exe) argümanlarda görünür.
not motor_python "$(ps -eo args | grep -m1 -iE '[p]ybundle-win.python\.exe' | cut -c1-200)"
# Wine altındaki Windows süreçleri "C:\…\python.exe" diye görünür; ana makinenin kendi python
# süreçleri (.exe'siz) sayılmaz. pybundle-win dışında bir python.exe motor olmamalı.
not sistem_python_motor "$(ps -eo args | grep -iE '[p]ython[0-9.]*\.exe' | grep -ivc 'pybundle-win')"

echo
echo "── HÜKÜM ──"
kirmizi=0
satir() { grep -m1 "^SINAV $1 " "$LOG" | cut -d" " -f3-; }
adim() { grep -m1 "^ADIM $1 " "$LOG" | cut -d" " -f3-; }
kontrol() {  # ad, beklenen-açıklama, değer, beklenen-regex
  if [[ "$3" =~ $4 ]]; then printf '  🟢 %-14s %s\n' "$1" "$3"
  else printf '  🔴 %-14s %s (beklenen: %s)\n' "$1" "${3:-<yok>}" "$2"; kirmizi=1; fi
}
kontrol onek_python "0 (Python'suz makine)"  "$(satir onek_python)"  '^0$'
kontrol kurulum    "Yuki.exe Programs altında" "$(satir kurulum)"    '^ok .*Programs'
kontrol kisayol    "≥1 Yuki.lnk"             "$(satir kisayol)"      '^[1-9]'
kontrol olcum      "pip 0"                   "$(satir olcum_araci)"  '^0$'
kontrol pencere    "CDP sayfası açık"        "$(adim pencere)"       '^ok'
kontrol motor      "/health 200"             "$(adim motor)"         '^200'
kontrol arayuz     "arayüz motordan"         "$(adim arayuz)"        '^ok'
kontrol sihirbaz   "dil adımı görünür"       "$(adim sihirbaz)"      '^ok'
kontrol js_istisna "0"                       "$(adim js_istisna)"    '^0$'
kontrol kutu       "pybundle-win python.exe" "$(satir motor_python)" 'pybundle-win.python\.exe'
kontrol sistem_py  "0 (başka python motor değil)" "$(satir sistem_python_motor)" '^0$'
echo "  ekranlar: $(cd "$CIKTI" && ls ./*.png 2>/dev/null | tr '\n' ' ')"
exit "$kirmizi"

#!/usr/bin/env bash
# AppImage kap sınavı — yabancı biri hazır AppImage'ı boş bir Linux'ta çift tıklarsa ne olur?
#
#   bash scripts/appimage-kap-sinavi.sh [AppImage-yolu] [çıktı-dizini]
#
# `linux-paket-testi.sh` yalnız "runtime aşaması geçildi mi"ye bakar (ekran yok, --version).
# Bu sınav bir adım ileri gider: pencere gerçekten açılıyor mu, AppImage İÇİNDEKİ motor
# (resources/backend/pybundle) kalkıyor mu, arayüz motora bağlanıyor mu, ilk kurulum
# sihirbazı geliyor mu. Ekran görüntüsü 1280 ve 390 genişlikte alınır.
#
# Kap: Debian 13 (trixie) · libfuse2 YOK · fuse3 VAR · NORMAL kullanıcı · Xvfb ekranı.
# Kapta Python/venv/pip YOK — motor yalnız AppImage'ın kendi kutusuyla kalkabilir.
# Ölçüm aracı (Playwright) kabın İÇİNE değil, ayrı bir venv'e /olcum altına kurulur ve
# Electron'a CDP ile bağlanır; uygulamanın kullandığı Python'a dokunmaz.
#
# Çıkış 0 = bütün adımlar yeşil · 1 = en az biri kırmızı · 2 = araç/kullanım hatası
# Ortam: YUKI_KONTEYNER (podman|docker; varsayılan podman varsa podman) · YUKI_KAP_SURE (sn, 600)
set -uo pipefail

KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMG="${1:-$(ls -t "$KOK"/electron/dist/Yuki-*-lite.AppImage 2>/dev/null | head -1)}"
CIKTI="${2:-$(mktemp -d "${TMPDIR:-/tmp}/yuki-kap.XXXXXX")}"
SURE="${YUKI_KAP_SURE:-600}"

[[ -f "$IMG" ]] || { echo "🔴 AppImage bulunamadı: ${IMG:-<yok>}" >&2; exit 2; }
if [[ -n "${YUKI_KONTEYNER:-}" ]]; then KONT="$YUKI_KONTEYNER"
elif command -v podman >/dev/null; then KONT=podman
elif command -v docker >/dev/null; then KONT=docker
else echo "🔴 podman ya da docker gerekli" >&2; exit 2; fi
mkdir -p "$CIKTI"
IMG="$(cd "$(dirname "$IMG")" && pwd)/$(basename "$IMG")"
CIKTI="$(cd "$CIKTI" && pwd)"

echo "AppImage kap sınavı · $(basename "$IMG") ($(du -h "$IMG" | cut -f1)) · araç=$KONT · çıktı=$CIKTI"

timeout "$SURE" "$KONT" run --rm --shm-size=1g \
  --device /dev/fuse --cap-add SYS_ADMIN --security-opt apparmor=unconfined \
  -v "$IMG:/yuki.AppImage:ro" -v "$KOK/scripts/appimage_kap_olcum.py:/olcum.py:ro" \
  -v "$CIKTI:/cikti" docker.io/library/debian:trixie bash -c '
set -u
export DEBIAN_FRONTEND=noninteractive
apt-get -qq update >/dev/null 2>&1
# Yalnız masaüstü kütüphaneleri + ekran. python3 burada YALNIZ ölçüm venvi için (aşağıda
# /olcum altına kurulur, uygulama PATH ile değil kendi kutusuyla çalışır — kanıt: motor_python).
apt-get -qq install -y fuse3 xvfb xauth libgtk-3-0t64 libnss3 libasound2t64 libatk-bridge2.0-0t64 \
    libcups2t64 libdrm2 libgbm1 libxkbcommon0 libatspi2.0-0t64 libxss1 libsecret-1-0 \
    python3 python3-venv curl ca-certificates >/dev/null 2>&1
echo "SINAV libfuse2 $(dpkg -l 2>/dev/null | grep -c " libfuse2")"
python3 -m venv /olcum-venv >/dev/null 2>&1 && /olcum-venv/bin/pip -q install playwright==1.49.1 >/tmp/pw.log 2>&1
echo "SINAV olcum_araci $?"
useradd -m deneme
cp /yuki.AppImage /home/deneme/Yuki.AppImage && chmod +x /home/deneme/Yuki.AppImage && chown deneme /home/deneme/Yuki.AppImage
chown deneme /cikti
# Kullanıcının yaptığı tek şey: dosyayı çalıştırmak. Sistemde python3 var ama motor onu kullanmamalı.
# (Bu blok tek tırnak içinde: yorumlara bile kesme işareti yazma, tırnağı kapatır.)
su deneme -c "cd ~ && xvfb-run -a -s \"-screen 0 1400x900x24\" ./Yuki.AppImage --remote-debugging-port=9222 >/cikti/uygulama.log 2>&1 &"
su deneme -c "/olcum-venv/bin/python /olcum.py /cikti"
echo "SINAV olcum_rc $?"
echo "SINAV motor_python $(ps -eo args | grep -m1 -E "[p]ybundle/bin/python3" | cut -c1-160)"
echo "SINAV sistem_python_motor $(ps -eo args | grep -cE "^/usr/bin/python3(\.[0-9]+)? run[.]py")"
' 2>&1 | tee "$CIKTI/kap.log" | grep -E "^SINAV|^ADIM" || true
# Chromium kapta 64 MB /dev/shm ile sekme düşürebiliyor; --shm-size masaüstüne yakın koşul verir.

echo
echo "── HÜKÜM ──"
kirmizi=0
satir() { grep -m1 "^SINAV $1 " "$CIKTI/kap.log" | cut -d" " -f3-; }
adim() { grep -m1 "^ADIM $1 " "$CIKTI/kap.log" | cut -d" " -f3-; }
kontrol() {  # ad, koşul-açıklaması, değer, beklenen-regex
  if [[ "$3" =~ $4 ]]; then printf '  🟢 %-14s %s\n' "$1" "$3"
  else printf '  🔴 %-14s %s (beklenen: %s)\n' "$1" "${3:-<yok>}" "$2"; kirmizi=1; fi
}
kontrol libfuse2   "0 paket"            "$(satir libfuse2)"      '^0$'
kontrol olcum      "pip 0"              "$(satir olcum_araci)"   '^0$'
kontrol pencere    "CDP sayfası açık"    "$(adim pencere)"        '^ok'
kontrol motor      "/health 200"         "$(adim motor)"          '^200'
kontrol arayuz     "arayüz motordan"     "$(adim arayuz)"         '^ok'
kontrol sihirbaz   "dil adımı görünür"   "$(adim sihirbaz)"       '^ok'
kontrol js_istisna "0"                   "$(adim js_istisna)"     '^0$'
kontrol kutu       "pybundle python3"    "$(satir motor_python)"  'pybundle/bin/python3'
kontrol sistem_py  "0 (sistem python'u motor değil)" "$(satir sistem_python_motor)" '^0$'
echo "  ekranlar: $(ls "$CIKTI"/*.png 2>/dev/null | xargs -n1 basename 2>/dev/null | tr '\n' ' ')"
exit "$kirmizi"

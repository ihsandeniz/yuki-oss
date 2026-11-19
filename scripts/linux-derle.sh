#!/usr/bin/env bash
# Temiz klondan tek komutla Linux AppImage:
#
#   bash scripts/linux-derle.sh
#
# Adımlar: Python kutusu → (varsa) süreç bekçisi → npm ci → AppImage.
# Çıktı: electron/dist/Yuki-<sürüm>-lite.AppImage
# Gerekenler: bash, curl, python3, node 20+, npm. Windows kutusu GEREKMEZ.
set -euo pipefail

KOK="$(cd "$(dirname "$0")/.." && pwd)"
cd "$KOK"

bash scripts/pybundle-uret.sh

# Süreç bekçisi isteğe bağlı (YUKI_BEKCI=1 iken kullanılır). Kaynağı ayrı depoda;
# ikili yoksa boş klasörle devam edilir, motor doğrudan başlar.
if [[ ! -x electron/bekci-bin/linux/yuki-bekci ]]; then
  if [[ -n "${YUKI_BEKCI_KAYNAK:-}" ]]; then
    python3 scripts/bekci-getir.py linux --kaynak "$YUKI_BEKCI_KAYNAK"
  else
    echo "• süreç bekçisi yok — atlanıyor (isteğe bağlı; YUKI_BEKCI_KAYNAK=<yol> ile eklenir)"
    mkdir -p electron/bekci-bin/linux
  fi
fi

cd electron
npm ci --no-audit --no-fund

# 🔴 Temiz makinede electron-builder'ın AppImage araç önbelleği YOK; statik runtime
# betiği değiştireceği dosyayı bulamayıp durur (ölçüldü 2026-11-12, boş
# ELECTRON_BUILDER_CACHE ile: "appimage cache'i yok", çıkış 1). Bu betik "temiz klondan
# tek komut" sözü veriyor ve önbelleği dolu makinede bu kırılma görünmüyordu.
# Çözüm: önbellek yoksa bir ön derleme araçları indirir; çıktısı FUSE 2'ye bağlı
# runtime taşıdığı için silinir, asıl paket statik runtime kurulduktan SONRA üretilir.
# Düzen sürüme göre değişir (24: appimage/<sürüm>/ · 26: appimage-<sürüm>/appimage-<sürüm>-<ek>/).
ONBELLEK="${ELECTRON_BUILDER_CACHE:-$HOME/.cache/electron-builder}"
if ! compgen -G "$ONBELLEK/appimage/*/runtime-x64" >/dev/null \
   && ! compgen -G "$ONBELLEK/appimage-*/appimage-*/runtime-x64" >/dev/null; then
  echo "• electron-builder araç önbelleği yok ($ONBELLEK) — ön derlemeyle indiriliyor"
  npx electron-builder --linux AppImage --publish never --config electron-builder.yml
  rm -f dist/*.AppImage
fi
bash ../scripts/appimage-statik-runtime.sh
python3 ../scripts/update_payload.py shell-id
npx electron-builder --linux AppImage --publish never --config electron-builder.yml
ls -la dist/*.AppImage

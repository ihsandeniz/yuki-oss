#!/bin/sh
# Yuki başlatıcı — tar.gz dağıtımı için.
#
# 🔴 NEDEN VAR (ölçüldü 2026-08-09, Debian 13 kabı)
# tar.gz'yi açıp `yuki-oss`u doğrudan çalıştırmak ŞU HATAYLA ölüyor:
#
#   FATAL: The SUID sandbox helper binary was found, but is not configured
#   correctly. ... chrome-sandbox is owned by root and has mode 4755
#
# Chromium'un SUID sandbox'ı, yardımcı ikilinin root'a ait ve 4755 olmasını ister.
# Bir arşivden açılan dosyalar bu bayrakları taşıyamaz (tar korusa bile kullanıcı
# root değil). AppImage'da bu sorun görünmüyor çünkü electron-builder'ın ürettiği
# `AppRun` uygulamayı zaten `--no-sandbox` ile başlatıyor (AppImageTarget.js:
# `executableArgs?.join(" ") || "--no-sandbox"`). tar.gz'de o sarmalayıcı yok.
#
# Yani bu script AppImage'ın kendi davranışını tar.gz'ye taşıyor — yeni bir taviz
# değil, mevcut davranışın aynısı. Sandbox'ı gerçekten açmak isteyen kullanıcı:
#   sudo chown root:root chrome-sandbox && sudo chmod 4755 chrome-sandbox
# yapıp `yuki-oss`u doğrudan çalıştırabilir.
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/yuki-oss" --no-sandbox "$@"

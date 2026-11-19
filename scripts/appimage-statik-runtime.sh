#!/usr/bin/env bash
# appimage-statik-runtime.sh — AppImage'ın FUSE 2 bağımlılığını kaldırır.
#
# 🔴 NEDEN VAR
# electron-builder'ın kullandığı AppImage runtime'ı (`appimage-12.0.1/runtime-x64`)
# `dlopen("libfuse.so.2")` yapıyor. FUSE 2 Debian türevlerinde varsayılan kurulu
# değil ve **Kali'de depoda hiç yok** (ölçüldü 2026-08-09: kali-rolling'de yalnız
# fuse3/libfuse3-4 var; libfuse2 ve libfuse2t64 aday bile değil). Sonuç: kullanıcı
# çift tıklıyor, **hiçbir hata çıkmıyor**, program açılmıyor. geliştirici bizzat bu duvara
# çarptı; ödeme yapmış bir müşterinin çözme ihtimali daha da düşük.
#
# Bu script cache'teki runtime'ı, AppImage projesinin **statik** runtime'ıyla
# (type2-runtime, Alpine/musl, `static-pie linked`) değiştirir. Statik olduğu için
# hedef sistemde libfuse aranmaz.
#
# 🔴 NEDEN electron-builder'IN KENDİ SEÇENEĞİ DEĞİL
# electron-builder 26 (26.18.1'de ölçüldü, 2026-11-12) varsayılan olarak hâlâ FUSE 2'ye bağlı
# `appimage-12.0.1` runtime'ını kullanıyor. `toolsets: {appimage: "1.0.3"}` seçeneği
# 26.18'de VAR ama kendi şemasında "Betas" başlığı altında — dağıtılan paketi beta
# araçla üretmiyoruz. Seçenek kararlıya geçince bu betik emekliye ayrılabilir.
#
# Runtime repoda sabit (`scripts/vendor/`): "continuous" release'ten her derlemede
# indirmek, sürümü ağın o anki hâline bağlardı — aynı kaynaktan iki farklı paket
# çıkabilirdi. Sabit dosya + sha256 = tekrarlanabilir derleme.
#
# Kullanım (idempotent — zaten kuruluysa hiçbir şey yapmaz):
#     bash scripts/appimage-statik-runtime.sh
#     bash scripts/appimage-statik-runtime.sh --geri-al   # orijinali geri koyar
set -euo pipefail

KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$KOK/scripts/vendor/appimage-runtime-x86_64"
KOK_CACHE="${ELECTRON_BUILDER_CACHE:-$HOME/.cache/electron-builder}"
# Önbellek düzeni sürüme göre değişiyor (ölçüldü 2026-11-12):
#   electron-builder 24: <önbellek>/appimage/appimage-12.0.1/runtime-x64
#   electron-builder 26: <önbellek>/appimage-12.0.1/appimage-12.0.1-<rastgele>/runtime-x64
# 26'ya geçişte bu betik yalnız eski yolu aradığı için "cache yok" deyip derlemeyi
# durduruyordu. İki düzen de aranır; hangisi varsa o işlenir.
CACHE="$KOK_CACHE"
runtime_listesi() {
  compgen -G "$KOK_CACHE/appimage/*/runtime-x64" || true
  compgen -G "$KOK_CACHE/appimage-*/appimage-*/runtime-x64" || true
}
BEKLENEN_SHA="1cc49bcf1e2ccd593c379adb17c9f85a36d619088296504de95b1d06215aebbf"

yaz() { printf '%s\n' "$*"; }
hata() { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

[ -f "$VENDOR" ] || hata "statik runtime yok: $VENDOR"

# Tekrarlanabilirlik kapısı: dosya sessizce değişmişse derlemeyi durdur.
GERCEK_SHA="$(sha256sum "$VENDOR" | cut -d' ' -f1)"
[ "$GERCEK_SHA" = "$BEKLENEN_SHA" ] || \
  hata "runtime sha256 tutmuyor (beklenen ${BEKLENEN_SHA:0:12}… , bulunan ${GERCEK_SHA:0:12}…)"

# Statik olduğunu her seferinde DOĞRULA — yanlış dosya konursa AppImage sessizce
# eski davranışa döner ve bunu ancak müşteri fark eder.
file "$VENDOR" | grep -q "static-pie linked" || hata "vendor runtime STATİK DEĞİL"
if strings "$VENDOR" | grep -q "libfuse.so.2"; then hata "vendor runtime hâlâ libfuse.so.2 istiyor"; fi

[ -n "$(runtime_listesi)" ] || hata "electron-builder appimage cache'i yok: $CACHE
  Önce bir kez derle (npm run build) ki electron-builder araçları indirsin, sonra bunu çalıştır."

bulunan=0
while IFS= read -r hedef; do
  [ -e "$hedef" ] || continue
  bulunan=$((bulunan + 1))
  yedek="$hedef.orijinal"

  if [ "${1:-}" = "--geri-al" ]; then
    if [ -f "$yedek" ]; then
      mv -f "$yedek" "$hedef"; yaz "  ↩ geri alındı: $hedef"
    else
      yaz "  · yedek yok, dokunulmadı: $hedef"
    fi
    continue
  fi

  if cmp -s "$VENDOR" "$hedef"; then
    yaz "  · zaten statik: $hedef"
    continue
  fi
  # Orijinali BİR KEZ yedekle (ikinci çalıştırmada statik olanı yedeklemeyelim).
  [ -f "$yedek" ] || cp "$hedef" "$yedek"
  cp "$VENDOR" "$hedef"; chmod +x "$hedef"
  yaz "  ✓ statik runtime kuruldu: $hedef"
done < <(runtime_listesi)

[ "$bulunan" -gt 0 ] || hata "cache'te runtime-x64 bulunamadı ($CACHE)"
yaz "  → $bulunan runtime işlendi"

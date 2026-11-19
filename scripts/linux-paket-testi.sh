#!/usr/bin/env bash
# appimage-fuse-testi.sh — AppImage libfuse2 OLMAYAN bir sistemde açılıyor mu?
#
# 🔴 NEDEN VAR
# geliştirici Kali'de AppImage'ı açamadı; kök neden runtime'ın `dlopen("libfuse.so.2")`
# yapması ve FUSE 2'nin Kali deposunda HİÇ olmaması. Düzeltme (statik runtime)
# yalnız libfuse2'siz bir sistemde ölçülerek doğrulanabilir — Arch'ta test etmek
# hiçbir şey kanıtlamaz, çünkü burada libfuse2 kurulu.
#
# Kap Debian 13 (trixie): Kali'nin beslendiği taban, libfuse2 YOK.
# `--device /dev/fuse` + `SYS_ADMIN`: statik runtime kütüphaneyi gömüyor ama
# KERNEL arayüzünü hâlâ kullanıyor; bu ikisi olmadan test yanlış negatif verir.
#
# Ayrım:
#   ESKİ runtime → "dlopen(): error loading libfuse.so.2"  (runtime aşamasında ölür)
#   YENİ runtime → mount başarılı, Electron açılır ve DISPLAY bulamadığı için
#                  farklı bir hata verir. Bu BAŞARIDIR: runtime aşaması geçilmiştir.
#
# Kullanım:  bash scripts/appimage-fuse-testi.sh [AppImage-yolu]
set -uo pipefail

KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMG="${1:-$(ls -t "$KOK"/electron/dist/Yuki-*-lite.AppImage 2>/dev/null | head -1)}"

[ -f "$IMG" ] || { echo "✗ AppImage bulunamadı: ${IMG:-<yok>}"; exit 2; }
echo "test edilen: $(basename "$IMG")  ($(du -h "$IMG" | cut -f1))"

echo
echo "── ÖN KOŞUL: paketin içindeki runtime statik mi ──"
if head -c 200000 "$IMG" | strings | grep -q "libfuse.so.2"; then
  echo "  ✗ paketteki runtime hâlâ libfuse.so.2 arıyor — statik runtime UYGULANMAMIŞ"
  echo "    (önce: bash scripts/appimage-statik-runtime.sh, sonra yeniden derle)"
  exit 1
fi
echo "  ✓ pakette libfuse.so.2 referansı yok"

echo
echo "── CANLI: Debian 13 kabında (libfuse2 YOK) çalıştır ──"
# 🔴 Kap KALİ'yi taklit etmeli, "herhangi bir Debian"ı değil:
#   · fuse3 KURULU (Kali'de var; `fusermount` bağını da o sağlıyor)
#   · libfuse2 YOK (Kali deposunda hiç yok — sorunun kaynağı bu)
#   · NORMAL KULLANICI (root değil; root'ta Electron zaten --no-sandbox istiyor ve
#     bu, asıl ölçmek istediğimiz runtime sorununu maskeliyor)
# İlk sürümde root + fuse3'süz ölçülüyordu: test GEÇİYORDU ama geçtiği senaryo
# kullanıcının yaşadığı senaryo değildi.
cikti=$(timeout 300 docker run --rm \
  --device /dev/fuse --cap-add SYS_ADMIN --security-opt apparmor:unconfined \
  -v "$IMG:/yuki.AppImage:ro" debian:trixie bash -c '
    export DEBIAN_FRONTEND=noninteractive
    apt-get -qq update >/dev/null 2>&1
    apt-get -qq install -y fuse3 libgtk-3-0t64 libnss3 libasound2t64 libatk-bridge2.0-0t64 \
        libcups2t64 libdrm2 libgbm1 libxkbcommon0 libatspi2.0-0t64 >/dev/null 2>&1
    echo "libfuse2 paketi : $(dpkg -l 2>/dev/null | grep -c libfuse2)  (0 olmalı)"
    echo "fusermount      : $(command -v fusermount || echo YOK)"
    useradd -m deneme 2>/dev/null
    cp /yuki.AppImage /tmp/y.AppImage && chmod +x /tmp/y.AppImage && chown deneme /tmp/y.AppImage
    su deneme -c "/tmp/y.AppImage --version" 2>&1 | head -20
  ' 2>&1)

echo "$cikti" | sed 's/^/  /'

echo
echo "── HÜKÜM: AppImage ──"
appimage_ok=1
if grep -q "libfuse.so.2" <<<"$cikti"; then
  echo "  ✗ DÜŞTÜ — hâlâ libfuse.so.2 isteniyor"; appimage_ok=0
elif grep -qiE "cannot mount|failed to mount|squashfs.*error" <<<"$cikti"; then
  echo "  ✗ DÜŞTÜ — mount edilemedi"; appimage_ok=0
elif grep -qi "No suitable fusermount" <<<"$cikti"; then
  # Runtime kendini extract-and-run'a kurtarır ama bu YAVAŞ yol; Kali'de fuse3
  # kurulu olduğu için buraya düşmemeli. Düşüyorsa kap yanlış kurulmuştur.
  echo "  ✗ DÜŞTÜ — fusermount bulunamadı (kap fuse3'süz mü kuruldu?)"; appimage_ok=0
else
  echo "  ✓ GEÇTİ — libfuse2 olmayan sistemde runtime aşaması aşıldı"
  echo "    (DISPLAY/GPU kaynaklı mesajlar normaldir: kapta ekran yok)"
fi

# ── tar.gz ────────────────────────────────────────────────────────────────────
# Yedek yol da ölçülmeli: AppImage çalışsa bile tar.gz bozuksa "yedeğimiz var"
# demek yanlış olur. 2026-08-09'da bu test gerçek bir kusur buldu — tar.gz'yi açıp
# `yuki-oss`u doğrudan çalıştırmak Chromium SUID sandbox hatasıyla ölüyordu;
# `yuki.sh` başlatıcısı o yüzden eklendi.
TGZ="${IMG%-lite.AppImage}-lite.tar.gz"
echo
echo "── tar.gz (yedek yol) ──"
if [ ! -f "$TGZ" ]; then
  echo "  · $TGZ yok — atlandı"
else
  echo "  arşiv: $(basename "$TGZ")  ($(du -h "$TGZ" | cut -f1))"
  if ! tar tzf "$TGZ" >/dev/null 2>&1; then
    echo "  ✗ ARŞİV BOZUK (kesik indirme / yarım yazma)"; exit 1
  fi
  echo "  ✓ arşiv sağlam"
  tcikti=$(timeout 500 docker run --rm -v "$TGZ:/y.tar.gz:ro" debian:trixie bash -c '
    export DEBIAN_FRONTEND=noninteractive; apt-get -qq update >/dev/null 2>&1
    apt-get -qq install -y libgtk-3-0t64 libnss3 libasound2t64 libatk-bridge2.0-0t64 \
        libcups2t64 libdrm2 libgbm1 libxkbcommon0 libatspi2.0-0t64 >/dev/null 2>&1
    useradd -m deneme 2>/dev/null
    mkdir -p /home/deneme/app && tar xzf /y.tar.gz -C /home/deneme/app --strip-components=1
    chown -R deneme /home/deneme/app
    # Kullanıcının gerçekte çalıştıracağı yol: başlatıcı (doğrudan yuki-oss DEĞİL)
    su deneme -c "/home/deneme/app/yuki.sh --version" 2>&1 | head -8
  ' 2>&1)
  echo "$tcikti" | sed 's/^/    /'
  if grep -qi "SUID sandbox helper" <<<"$tcikti"; then
    echo "  ✗ DÜŞTÜ — sandbox hatası (yuki.sh başlatıcısı eksik ya da çalışmıyor)"; exit 1
  elif grep -qi "No such file or directory.*yuki.sh" <<<"$tcikti"; then
    echo "  ✗ DÜŞTÜ — yuki.sh pakete girmemiş (extraFiles?)"; exit 1
  else
    echo "  ✓ GEÇTİ — tar.gz açıldı ve başlatıcı çalıştı (FUSE hiç gerekmedi)"
    # 2026-08-09: bu yolda `Segmentation fault` görüldü, AppImage yolunda görülmedi.
    # DISPLAY'siz kapta Electron çıkarken segfault vermesi bilinen bir durum, ama
    # ASİMETRİ (bir pakette var, ötekinde yok) kendiliğinden açıklanmış sayılmaz.
    # Düşürmüyoruz — kapta ekran yok, hüküm vermek için yetersiz kanıt; ama sessizce
    # de geçmiyoruz ki gerçek masaüstünde bakılacaklar listesine girsin.
    if grep -qi "Segmentation fault" <<<"$tcikti"; then
      echo "  ⚠ NOT: çıkışta segfault (AppImage yolunda YOK). Ekransız kaba özgü olabilir;"
      echo "    gerçek masaüstünde bir kez göz kontrolü yapılmalı."
    fi
  fi
fi

[ "$appimage_ok" = "1" ] || exit 1

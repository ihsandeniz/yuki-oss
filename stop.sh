#!/usr/bin/env bash
# Yuki (ÜRÜN) — durdurma
#
# 🔴 BU SCRIPT 2026-09-10'DA BAŞTAN YAZILDI. Eski hâli kişisel Alice'ten
# fotokopiydi ve **kişisel Yuki'yi öldürüyordu**. Dört ayrı yerden:
#   ① `PID_FILE=/tmp/alice-backend.pid`   → kişiselle AYNI dosya
#   ② `lsof -ti tcp:8000`                 → kişiselin portu (ürünün portu 8001)
#   ③ `cloudflared tunnel run yuki`       → kişiselin GENEL tüneli
#   ④ `pgrep -f "alice-ai|AliceAi/electron"` → desende kişiselin dizin yolu
#      geçiyor; ayrıca `alice-ai` iki kurulumun PAYLAŞTIĞI Electron `name`'i
#      (app.asar'da `productName` yok — bkz. CLAUDE.md § geliştirme profili),
#      yani ürünü kapatmak kişiselin penceresini de kapatıyordu.
#
# 🔑 YENİ KURAL: bu script YALNIZ `start.sh`'in kendi başlattığını durdurur.
# Kimlik kaynağı ürüne özel PID dosyalarıdır; "şu porta bakıp öldür" gibi
# geniş bir tarama yapılmaz. Bir süreci biz başlatmadıysak ona dokunmayız.
#
# Kullanım: ./stop.sh

set -euo pipefail

# 🔴 Ürünün portu. 8000 KİŞİSELİNDİR — buraya yazma.
PORT="${YUKI_PORT:-8001}"
PID_FILE="/tmp/yuki-urun-backend.pid"
ELECTRON_PID_FILE="/tmp/yuki-urun-electron.pid"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
info() { echo -e "${CYAN}→${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }

# Electron ana süreci argv'sinde ayırt edici bir string taşımayabiliyor; tüm
# süreç ağacını PID üzerinden kapatıyoruz (pattern araması ana süreci kaçırıp
# alt-süreçleri yetim bırakıyordu).
kill_tree() {
  local pid="$1" child
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    kill_tree "$child"
  done
  kill -9 "$pid" 2>/dev/null || true
}

echo ""

# ── 1. Backend ───────────────────────────────────────────────
if [[ -f "$PID_FILE" ]]; then
  PID=$(cat "$PID_FILE")
  if kill -0 "$PID" 2>/dev/null; then
    info "Ürün backend'i durduruluyor (PID $PID)..."
    kill "$PID" 2>/dev/null || true
    sleep 1
    kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null || true
    ok "Backend durduruldu."
  else
    warn "Backend (PID $PID) zaten çalışmıyor."
  fi
  rm -f "$PID_FILE"
else
  # ⚠️ PID dosyası yoksa PORT ÜZERİNDEN ÖLDÜRMÜYORUZ — eski scriptin kişiseli
  # vurduğu yer tam olarak burasıydı. Yalnız BİLGİ veriyoruz; kararı insan
  # verir. Bizim başlatmadığımız bir süreci öldürmek bizim işimiz değil.
  if lsof -ti "tcp:$PORT" &>/dev/null; then
    warn "PID dosyası yok ama port $PORT dolu. Bu süreci BİZ başlatmadık —"
    warn "dokunulmuyor. Gerekirse elle: lsof -ti tcp:$PORT"
  else
    warn "Çalışan ürün backend'i bulunamadı."
  fi
fi

# ── 2. Electron ──────────────────────────────────────────────
if [[ -f "$ELECTRON_PID_FILE" ]]; then
  NPM_PID=$(cat "$ELECTRON_PID_FILE")
  if kill -0 "$NPM_PID" 2>/dev/null; then
    info "Electron durduruluyor (süreç ağacı, PID $NPM_PID)..."
    kill_tree "$NPM_PID"
    ok "Electron durduruldu."
  else
    warn "Electron (PID $NPM_PID) zaten çalışmıyor."
  fi
  rm -f "$ELECTRON_PID_FILE"
else
  warn "Çalışan ürün Electron'u bulunamadı."
fi

# ── Dokunulmayanlar ──────────────────────────────────────────
# · Cloudflare tüneli — kişiselin, ürünün değil.
# · PostgreSQL — ürün Postgres'siz çalışır (`todo_store.json`); kök
#   docker-compose.yml pg'yi kişiselin portunda (5433) ayağa kaldırıyor,
#   `docker compose down` çağırmak komşu kuruluma uzanmak olurdu.

echo ""
ok "Yuki (ÜRÜN) durduruldu."
echo ""

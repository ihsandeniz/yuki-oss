#!/usr/bin/env bash
# Yuki — Backend hot-restart (kod değişikliği sonrası)
# SADECE backend'i yeniden başlatır — Electron'a DOKUNMAZ.
# Kullanım: ./restart-backend.sh            (port: $YUKI_PORT, varsayılan 8001)
#           YUKI_PORT=8123 ./restart-backend.sh
#
# Kimlik kaynağı yalnız bu projenin PID dosyasıdır (start.sh/stop.sh ile aynı:
# /tmp/yuki-urun-backend.pid). "Şu portu dinleyeni öldür" YAPILMAZ: aynı makinede
# başka bir uygulama (ör. kişisel kopya, 8000) o portta olabilir. Port bizim
# PID'imiz dışında biri tarafından tutuluyorsa script durur ve kimseyi öldürmez.

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
PORT="${YUKI_PORT:-8001}"
LOG_BACKEND="/tmp/yuki-urun-backend.log"
PID_FILE="/tmp/yuki-urun-backend.pid"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
info() { echo -e "${CYAN}→${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }

[[ "$PORT" == "8000" ]] && fail "PORT 8000 kişisel kopyanındır — YUKI_PORT'u değiştir."
[[ -x "$BACKEND_DIR/venv/bin/python" ]] || fail "Venv bulunamadı: $BACKEND_DIR/venv"

# ── 1. Eski backend'i durdur (yalnız kendi PID dosyamızdaki süreç) ──
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  OLD_PID=$(cat "$PID_FILE")
  info "Backend durduruluyor (PID $OLD_PID)..."
  kill "$OLD_PID" 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    kill -0 "$OLD_PID" 2>/dev/null || break
    sleep 1
  done
  kill -0 "$OLD_PID" 2>/dev/null && kill -9 "$OLD_PID" 2>/dev/null
  ok "Backend durduruldu."
else
  warn "Çalışan backend yok (PID dosyası yok ya da bayat) — temiz başlatılıyor."
fi
rm -f "$PID_FILE"

# Port hâlâ doluysa bizim olmayan bir süreç dinliyor — dokunma, net hata ver.
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t &>/dev/null; then
  fail "Port $PORT dolu — başka bir süreç dinliyor: $(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t | head -1 | xargs -r ps -o cmd= -p 2>/dev/null). Önce onu kapat ya da YUKI_PORT ver."
fi

# ── 2. Başlat (start.sh ile aynı) ───────────────────────────
info "Backend başlatılıyor (port $PORT)..."
cd "$BACKEND_DIR" || fail "Backend klasörüne geçilemedi: $BACKEND_DIR"
# `load_dotenv` mevcut ortam değişkenini EZMEZ → buradaki PORT kazanır.
export PORT
nohup venv/bin/python run.py >"$LOG_BACKEND" 2>&1 &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$PID_FILE"

# ── 3. Health check ──────────────────────────────────────────
info "Backend hazır olana kadar bekleniyor..."
for _ in $(seq 1 20); do
  if curl -sf "http://127.0.0.1:$PORT/health" &>/dev/null; then
    ok "Backend hazır (PID $BACKEND_PID) — http://127.0.0.1:$PORT"
    exit 0
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo ""
    warn "Backend çöktü. Son log satırları:"
    tail -20 "$LOG_BACKEND"
    fail "Restart başarısız. Tam log: $LOG_BACKEND"
  fi
  sleep 1
done
warn "Backend 20s içinde /health yanıtı vermedi. Son log satırları:"
tail -10 "$LOG_BACKEND"
exit 1

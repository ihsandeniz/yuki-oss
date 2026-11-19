#!/usr/bin/env bash
# Yuki (ÜRÜN) — geliştirme başlatıcısı
#
# Kullanım:
#   ./start.sh              # backend + Electron
#   ./start.sh --no-ui      # yalnız backend
#   ./start.sh --web        # backend + tarayıcı
#   YUKI_PORT=8123 ./start.sh
#
# Postgres buradan başlatılmaz: PLAN ekranı Postgres'siz çalışır (`todo_store.json`).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
ELECTRON_DIR="$ROOT_DIR/electron"

# Varsayılan port 8001; 8000 ayrılmış.
PORT="${YUKI_PORT:-8001}"

LOG_BACKEND="/tmp/yuki-urun-backend.log"
LOG_ELECTRON="/tmp/yuki-urun-electron.log"
PID_FILE="/tmp/yuki-urun-backend.pid"
ELECTRON_PID_FILE="/tmp/yuki-urun-electron.pid"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
info() { echo -e "${CYAN}→${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }

OPEN_ELECTRON=true
OPEN_BROWSER=false
for arg in "$@"; do
  case $arg in
    --web)   OPEN_ELECTRON=false; OPEN_BROWSER=true ;;
    --no-ui) OPEN_ELECTRON=false; OPEN_BROWSER=false ;;
    --help|-h)
      echo "Kullanım: $0 [--web] [--no-ui]"
      echo "  Port: \$YUKI_PORT (varsayılan 8001). 8000 is reserved."
      exit 0 ;;
    *) warn "Bilinmeyen argüman: $arg"; exit 1 ;;
  esac
done

if [[ "$PORT" == "8000" ]]; then
  fail "Port 8000 is reserved — set YUKI_PORT to another port."
fi

echo ""
echo -e "${CYAN}╔══════════════════════════════╗${NC}"
echo -e "${CYAN}║        Yuki — ÜRÜN           ║${NC}"
echo -e "${CYAN}╚══════════════════════════════╝${NC}"
echo ""

# ── Önceki koşu ──────────────────────────────────────────────
if [[ -f "$PID_FILE" ]]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    warn "Ürün backend'i zaten çalışıyor (PID $OLD_PID). Önce ./stop.sh."
    exit 1
  fi
  rm -f "$PID_FILE"
fi

# Port başkasındaysa durulur.
if lsof -ti "tcp:$PORT" &>/dev/null; then
  fail "Port $PORT dolu — başka bir süreç dinliyor. Önce onu kapat."
fi

# ── Backend ──────────────────────────────────────────────────
info "Backend başlatılıyor (port $PORT)..."
[[ -x "$BACKEND_DIR/venv/bin/python" ]] || fail "Venv bulunamadı: $BACKEND_DIR/venv"

cd "$BACKEND_DIR"
# `load_dotenv` mevcut ortam değişkenini EZMEZ → buradaki PORT kazanır.
export PORT
# README'deki uvicorn komutuyla aynı varsayılan: hafıza arka ucu ortamda ya da bir .env'de
# seçilmemişse gömülü sqlite. Yoksa config pgvector'a düşer, DATABASE_URL boş → hafıza KAPALI
# açılıyordu (temiz klonda /health "memory": false). .env'deki seçim
# ezilmesin diye yalnız hiçbir yerde yazmıyorsa verilir. Bekçi: test_baslat_durdur_izolasyonu
if [[ -z "${MEMORY_BACKEND:-}" ]]; then
  # config.py ile aynı .env: önce veri dizinindeki, yoksa kökteki (ikisini birden okumaz).
  _env="${YUKI_DATA_DIR:-$ROOT_DIR}/.env"; [[ -f "$_env" ]] || _env="$ROOT_DIR/.env"
  # python-dotenv `export MEMORY_BACKEND=…` ve `MEMORY_BACKEND = …` biçimlerini de okur.
  grep -qsE '^[[:space:]]*(export[[:space:]]+)?MEMORY_BACKEND[[:space:]]*=' "$_env" || export MEMORY_BACKEND=sqlite
fi
nohup venv/bin/python run.py >"$LOG_BACKEND" 2>&1 &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$PID_FILE"

info "Backend hazır olana kadar bekleniyor..."
for i in $(seq 1 30); do
  curl -sf "http://127.0.0.1:$PORT/health" &>/dev/null && { ok "Backend hazır (PID $BACKEND_PID)."; break; }
  kill -0 "$BACKEND_PID" 2>/dev/null || fail "Backend çöktü. Log: $LOG_BACKEND"
  [[ $i -eq 30 ]] && warn "Backend 30s içinde yanıt vermedi — devam ediliyor."
  sleep 1
done

# ── Electron ─────────────────────────────────────────────────
if $OPEN_ELECTRON; then
  info "Electron başlatılıyor..."
  cd "$ELECTRON_DIR"
  nohup npm start >"$LOG_ELECTRON" 2>&1 &
  echo "$!" > "$ELECTRON_PID_FILE"
  ok "Electron başlatıldı (log: $LOG_ELECTRON)."
fi

if $OPEN_BROWSER; then
  info "Tarayıcı açılıyor..."
  xdg-open "http://127.0.0.1:$PORT/ui" &>/dev/null &
fi

echo ""
ok "Yuki (ÜRÜN) çalışıyor."
echo -e "   Arayüz   : ${CYAN}http://127.0.0.1:$PORT/ui${NC}"
echo -e "   Loglar   : ${CYAN}$LOG_BACKEND${NC}"
echo -e "            : ${CYAN}$LOG_ELECTRON${NC}"
echo -e "   Durdur   : ${CYAN}./stop.sh${NC}"
echo ""

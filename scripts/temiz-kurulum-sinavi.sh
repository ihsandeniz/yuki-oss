#!/usr/bin/env bash
# Temiz kurulum sınavı — yabancı biri README'deki "Run from source" adımlarıyla Yuki'yi
# boş bir Linux konteynerinde kaynaktan kurabiliyor mu, Yuki bulut sesle (Edge) cevap
# veriyor mu, depoda dağıtma hakkımız olmayan dosya kalmış mı?
#
# Koşturma (deponun kökünden):   bash scripts/temiz-kurulum-sinavi.sh
# Çıkış 0 = bütün adımlar yeşil · 1 = en az bir adım kırmızı · 2 = araç eksik / kullanım hatası
#
# Adımlar:
#   1. kaynak   — `git archive <ref>` ile depo dışarı alınır (klasör kopyası DEĞİL: izlenmeyen
#                 yerel/kişisel dosya sınava giremez)
#   2. kurulum  — boş `python:<sürüm>-slim` konteynerinde README adımları aynen:
#                 `python3 -m venv venv` → `venv/bin/pip install -r requirements.txt`
#   3. health   — backend başlar (MEMORY_BACKEND=sqlite), `GET /health` → 200
#   4. ses      — `POST /api/tts/test` → boş olmayan ses, sağlayıcı edge (Google'a düşmedi)
#   5. lisans   — varlık-lisans kapısı (şerit A'nın kapısı) → 0 ihlal
#   6. temizlik — `scripts/test_temizlik.py` (dışarı alınan kaynak üstünde) → kaldı 0
#   7. sohbet   — ölçülmez, yalnız "ölçülmedi" basar; başarısız saymaz
#
# Ortam değişkenleri (hepsi isteğe bağlı):
#   YUKI_KONTEYNER        podman | docker | <yol>  (varsayılan: podman varsa podman, yoksa docker)
#   YUKI_SINAV_PY         konteyner Python sürümü (varsayılan 3.12 — README'nin alt sınırı)
#   YUKI_SINAV_REF        sınanacak git ref'i (varsayılan HEAD)
#   YUKI_SINAV_CPU / YUKI_SINAV_RAM   konteyner tavanı (varsayılan 4 çekirdek / 8g)
#   YUKI_LISANS_KAPI      lisans kapısının adı (varsayılan test_varlik_lisans)
#
# Konteyner `--rm` ile koşar; birim (volume) açılmaz. Sınav imajı bu koşuda çekildiyse
# sonunda silinir (önceden makinede varsa dokunulmaz).

set -uo pipefail

KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY_SURUM="${YUKI_SINAV_PY:-3.12}"
REF="${YUKI_SINAV_REF:-HEAD}"
IMAJ="docker.io/library/python:${PY_SURUM}-slim"
CPU="${YUKI_SINAV_CPU:-4}"
RAM="${YUKI_SINAV_RAM:-8g}"
# Sözleşme (şerit A, 2026-10-30): varlık-lisans kapısı `scripts/test_temizlik.py` içinde
# `test_varlik_lisans` adıyla durur; tek başına `--kapi <ad>` ile koşar, çıkış 0/1.
KAPI_ADI="${YUKI_LISANS_KAPI:-test_varlik_lisans}"

declare -A SONUC DETAY
SIRA=(kaynak kurulum health ses lisans temizlik sohbet)
for a in "${SIRA[@]}"; do SONUC[$a]="—"; DETAY[$a]="koşulmadı"; done
yaz() { SONUC[$1]="$2"; DETAY[$1]="$3"; printf '  %-9s %s  %s\n' "$1" "$2" "$3"; }

# ── Araçlar ─────────────────────────────────────────────────────────────
if [[ -n "${YUKI_KONTEYNER:-}" ]]; then
    KONT="$YUKI_KONTEYNER"
elif command -v podman >/dev/null; then
    KONT=podman
elif command -v docker >/dev/null; then
    KONT=docker
else
    echo "🔴 podman ya da docker gerekli (YUKI_KONTEYNER ile yolu verilebilir)" >&2
    exit 2
fi
command -v "$KONT" >/dev/null || { echo "🔴 konteyner aracı bulunamadı: $KONT" >&2; exit 2; }
command -v git >/dev/null || { echo "🔴 git gerekli" >&2; exit 2; }
command -v python3 >/dev/null || { echo "🔴 python3 gerekli (kapılar için)" >&2; exit 2; }

GECICI="$(mktemp -d "${TMPDIR:-/tmp}/yuki-sinav.XXXXXX")"
IMAJ_ONCEDEN_VAR=1
temizle() {
    rm -rf "$GECICI"
    if [[ "$IMAJ_ONCEDEN_VAR" == 0 ]]; then
        "$KONT" image rm "$IMAJ" >/dev/null 2>&1 || true
    fi
}
trap temizle EXIT

echo "Yuki temiz kurulum sınavı · ref=$REF · python=$PY_SURUM · araç=$KONT"

# ── 1 · kaynak ──────────────────────────────────────────────────────────
KAYNAK="$GECICI/kaynak"
mkdir -p "$KAYNAK"
if git -C "$KOK" archive --format=tar "$REF" | tar -x -C "$KAYNAK" 2>"$GECICI/archive.err" \
   && [[ -f "$KAYNAK/backend/requirements.txt" ]]; then
    yaz kaynak "🟢" "git archive $(git -C "$KOK" rev-parse --short "$REF") → $(find "$KAYNAK" -type f | wc -l) dosya"
else
    yaz kaynak "🔴" "git archive başarısız: $(head -c 200 "$GECICI/archive.err")"
fi

# ── 2-4 · konteynerde README adımları ───────────────────────────────────
# İç betik yalnız ham gerçek basar ("SINAV <ad> <değer>"); hüküm dışarıda verilir.
IC_BETIK='
set -u
cp -a /kaynak /yuki && cd /yuki/backend || { echo "SINAV kurulum_rc 99"; exit 0; }
python3 -m venv venv >/tmp/venv.log 2>&1 && venv/bin/pip install -r requirements.txt >/tmp/pip.log 2>&1
echo "SINAV kurulum_rc $?"
tail -n 15 /tmp/pip.log | sed "s/^/SINAV_PIP /"
[ -x venv/bin/python ] || exit 0
mkdir -p /tmp/veri
MEMORY_BACKEND=sqlite ALICE_DATA_DIR=/tmp/veri \
  venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 >/tmp/uvicorn.log 2>&1 &
venv/bin/python - <<"PY"
import base64, json, time, urllib.request
kod = 0
for _ in range(90):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=3) as r:
            kod = r.status
            break
    except Exception as e:
        kod = getattr(e, "code", 0) or 0
        if kod:
            break
        time.sleep(1)
print("SINAV health", kod, flush=True)
if kod != 200:
    raise SystemExit
istek = urllib.request.Request("http://127.0.0.1:8001/api/tts/test", data=b"{}",
                               headers={"Content-Type": "application/json"}, method="POST")
try:
    with urllib.request.urlopen(istek, timeout=60) as r:
        govde = json.loads(r.read())
    print("SINAV tts_http", r.status, flush=True)
    print("SINAV tts_bayt", len(base64.b64decode(govde.get("audio_base64") or "")), flush=True)
except Exception as e:
    print("SINAV tts_http", getattr(e, "code", 0) or 0, flush=True)
    print("SINAV tts_bayt 0", flush=True)
PY
sleep 1
# Edge düşerse services/tts.py "Edge TTS hatası (...), Google TTS'"'"'e dönülüyor." yazar.
echo "SINAV edge_hatasi $(grep -c "Edge TTS hatası" /tmp/uvicorn.log)"
echo "SINAV google_istek $(grep -c "translate.google" /tmp/uvicorn.log)"
tail -n 20 /tmp/uvicorn.log | sed "s/^/SINAV_LOG /"
'

if [[ "${SONUC[kaynak]}" == "🟢" ]]; then
    if ! "$KONT" image inspect "$IMAJ" >/dev/null 2>&1; then
        IMAJ_ONCEDEN_VAR=0
    fi
    echo "  … konteyner koşuyor (pip install birkaç dakika sürebilir)"
    "$KONT" run --rm --pull=missing --cpus "$CPU" --memory "$RAM" \
        -v "$KAYNAK:/kaynak:ro,Z" \
        "$IMAJ" bash -c "$IC_BETIK" >"$GECICI/konteyner.log" 2>&1
    KONT_RC=$?
    deger() { awk -v k="$1" '$1=="SINAV" && $2==k {print $3}' "$GECICI/konteyner.log" | tail -n1; }
    KUR_RC="$(deger kurulum_rc)"; HEALTH="$(deger health)"
    TTS_HTTP="$(deger tts_http)"; TTS_BAYT="$(deger tts_bayt)"
    EDGE_HATA="$(deger edge_hatasi)"; GOOGLE="$(deger google_istek)"

    if [[ "$KUR_RC" == 0 ]]; then
        yaz kurulum "🟢" "venv + pip install -r requirements.txt (python $PY_SURUM)"
    else
        yaz kurulum "🔴" "pip/venv çıkışı ${KUR_RC:-yok} (konteyner rc=$KONT_RC)"
        grep '^SINAV_PIP ' "$GECICI/konteyner.log" | tail -n 5 | sed 's/^SINAV_PIP /      /'
        [[ -n "$KUR_RC" ]] || tail -n 5 "$GECICI/konteyner.log" | sed 's/^/      /'
    fi
    if [[ "$HEALTH" == 200 ]]; then
        yaz health "🟢" "GET /health → 200"
    elif [[ "$KUR_RC" == 0 ]]; then
        yaz health "🔴" "GET /health → ${HEALTH:-yanıt yok}"
        grep '^SINAV_LOG ' "$GECICI/konteyner.log" | tail -n 8 | sed 's/^SINAV_LOG /      /'
    fi
    if [[ "$TTS_HTTP" == 200 && "${TTS_BAYT:-0}" -gt 1000 && "$EDGE_HATA" == 0 && "$GOOGLE" == 0 ]]; then
        yaz ses "🟢" "POST /api/tts/test → $TTS_BAYT bayt, sağlayıcı edge"
    elif [[ "$HEALTH" == 200 ]]; then
        SAG="edge"; [[ "${EDGE_HATA:-0}" != 0 || "${GOOGLE:-0}" != 0 ]] && SAG="google (Edge düştü)"
        yaz ses "🔴" "POST /api/tts/test → http ${TTS_HTTP:-?}, ${TTS_BAYT:-0} bayt, sağlayıcı $SAG"
        grep '^SINAV_LOG ' "$GECICI/konteyner.log" | grep -i 'tts\|edge' | tail -n 3 | sed 's/^SINAV_LOG /      /'
    fi
fi

# ── 5 · varlık-lisans kapısı ────────────────────────────────────────────
if [[ "${SONUC[kaynak]}" == "🟢" ]]; then
    # Kapı dosyada yoksa `--kapi`yı tanımayan eski betik bambaşka bir şey koşar —
    # sonucu ne olursa olsun güvenilmez; o yüzden önce kapının varlığı aranır.
    if ! grep -q "^def ${KAPI_ADI}(" "$KAYNAK/scripts/test_temizlik.py" 2>/dev/null; then
        yaz lisans "🔴" "kapı yok: scripts/test_temizlik.py içinde ${KAPI_ADI} tanımlı değil (şerit A birleşmedi mi?)"
    elif (cd "$KAYNAK" && python3 scripts/test_temizlik.py --kapi "$KAPI_ADI") >"$GECICI/lisans.log" 2>&1; then
        yaz lisans "🟢" "test_temizlik.py --kapi $KAPI_ADI → 0 ihlal"
    else
        yaz lisans "🔴" "test_temizlik.py --kapi $KAPI_ADI → ihlal ($(grep -v '^[[:space:]]*$' "$GECICI/lisans.log" | tail -n1 | cut -c1-120))"
    fi

# ── 6 · temizlik kapısı ─────────────────────────────────────────────────
    if python3 "$KAYNAK/scripts/test_temizlik.py" "$KAYNAK" >"$GECICI/temizlik.log" 2>&1; then
        yaz temizlik "🟢" "test_temizlik.py → $(grep -o 'geçti [0-9]* · kaldı [0-9]*' "$GECICI/temizlik.log" | tail -n1)"
    else
        yaz temizlik "🔴" "test_temizlik.py → $(grep -o 'geçti [0-9]* · kaldı [0-9]*' "$GECICI/temizlik.log" | tail -n1)"
        grep '🔴' "$GECICI/temizlik.log" | head -n 5 | sed 's/^/      /'
    fi
fi

# ── 7 · sohbet (isteğe bağlı, ölçülmez) ─────────────────────────────────
yaz sohbet "⚪" "ölçülmedi — LLM anahtarı sınava verilmiyor (başarısız sayılmaz)"

# ── Hüküm ───────────────────────────────────────────────────────────────
KIRMIZI=()
for a in kaynak kurulum health ses lisans temizlik; do
    [[ "${SONUC[$a]}" == "🟢" ]] || KIRMIZI+=("$a")
done
if (( ${#KIRMIZI[@]} == 0 )); then
    echo "🟢 SINAV GEÇTİ — 6/6 adım yeşil"
    exit 0
fi
echo "🔴 SINAV KALDI — kırmızı/koşulmayan adım: ${KIRMIZI[*]}"
exit 1

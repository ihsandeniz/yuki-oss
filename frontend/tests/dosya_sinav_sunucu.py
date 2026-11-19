"""Dosya gönder + güvenli dosya tarayıcı testleri için sınav sunucusu — ikinci port, geçici veri.

Gerçek uçlar (dosya_api · guvenli_dosya_api · media) + gerçek ön yüz (/ui). Kabuk yerine
`/sinav/kabuk.html`: içinde gerçek `tab-switcher.js` ve `#dosya-iframe` var; sohbet soketi,
`showToast`, `switchTab` sahte — gönderilen mesajları `window._sinav` toplar. Gerçek sohbet,
gerçek LLM, kişisel Yuki (8000) ya da yuki-oss (8001) servisine dokunmaz.

    python frontend/tests/dosya_sinav_sunucu.py 18831
    YUKI_URL=http://127.0.0.1:18831 python -m pytest frontend/tests/test_dosya_gonder_guvenli.py -q

Kök: `<geçici>/Belgelerim` (not.txt, resim.png, alt/), galeri `<geçici>/Resimlerim` (3 PNG, 2 alt klasör), veri: `<geçici>/veri`. Anahtar: `sinav-anahtari`.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

GECICI = Path(tempfile.mkdtemp(prefix="yuki-dosya-sinav-"))
os.environ["YUKI_DATA_DIR"] = str(GECICI / "veri")
os.environ["AUTH_TOKEN"] = "sinav-anahtari"
KOK = GECICI / "Belgelerim"
os.environ["YUKI_DOSYA_KOKLER"] = str(KOK)
GKOK = GECICI / "Resimlerim"
os.environ["YUKI_GALERI_KOKLER"] = str(GKOK)

_DEPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_DEPO / "backend"))

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from app.api import dosya_api, galeri_api, guvenli_dosya_api, media  # noqa: E402
from app.limiter import limiter  # noqa: E402

# 1×1 PNG
_PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                     "1f15c4890000000d4944415478da63f8cf00000301010018dd8db00000000049454e44ae426082")

KABUK = """<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>html,body{margin:0;height:100%;background:#0a090e}#dosya-iframe{width:100%;height:100%;border:0;display:block}</style>
<script>
window._sinav = { gonderilen: [], toast: [], sekme: [] };
var socket = { readyState: 1, send: function (m) { window._sinav.gonderilen.push(JSON.parse(m)); } };
function authFetch(u, o) { return fetch(u, o); }
function showToast(m, t) { window._sinav.toast.push([t, m]); }
function addMessage() {}
function updateState() {}
function switchTab(s) { window._sinav.sekme.push(s); }
</script></head><body>
<input type="file" id="mediaFileInput" hidden>
<iframe id="dosya-iframe" src="/ui/dosya.html"></iframe>
<script src="/ui/js/tab-switcher.js"></script>
</body></html>"""


def _resim(renk: tuple[int, int, int]) -> bytes:
    """400×300 düz renk + köşegen şerit — galeri küçük resmi gerçekçi görünsün."""
    import io

    from PIL import Image, ImageDraw
    im = Image.new("RGB", (400, 300), renk)
    ImageDraw.Draw(im).polygon([(0, 300), (160, 0), (240, 0), (80, 300)], fill=tuple(min(255, c + 50) for c in renk))
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def tohumla() -> None:
    (KOK / "alt").mkdir(parents=True, exist_ok=True)
    (KOK / "not.txt").write_text("merhaba dunya — sınav metni", "utf-8")
    (KOK / "rapor.md").write_text("# Haftalık rapor\n\nİkinci belge.", "utf-8")
    (KOK / "resim.png").write_bytes(_PNG)
    (KOK / "alt" / "eski.txt").write_text("alt klasör", "utf-8")
    for yol, renk in (("deniz.png", (40, 110, 190)), ("tatil/kum.png", (215, 180, 110)), ("aile/bayram.png", (170, 60, 90))):
        (GKOK / yol).parent.mkdir(parents=True, exist_ok=True)
        (GKOK / yol).write_bytes(_resim(renk))


def uygulama() -> FastAPI:
    tohumla()
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(dosya_api.router)
    app.include_router(guvenli_dosya_api.router)
    app.include_router(media.router)
    app.include_router(galeri_api.router)

    @app.get("/sinav/var")
    def var(yol: str):
        """Galeri kökü altında bu göreli yol var mı (test dosya sistemini doğrular)."""
        return {"var": (GKOK / yol).resolve().is_relative_to(GKOK.resolve()) and (GKOK / yol).exists()}

    @app.get("/health")
    def saglik():
        return {"ok": True}

    @app.get("/sinav/kabuk.html", response_class=HTMLResponse)
    def kabuk():
        return KABUK

    @app.post("/sinav/sifirla")
    def sifirla():
        """Her test temiz başlar: kök yeniden tohumlanır, güvenli dosya kapanır."""
        import shutil
        shutil.rmtree(KOK, ignore_errors=True)
        shutil.rmtree(GKOK, ignore_errors=True)
        shutil.rmtree(GECICI / "veri", ignore_errors=True)
        tohumla()
        media.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        dosya_api._LISTE_ONBELLEK.clear()
        galeri_api._TUM_ONBELLEK = (0.0, (), [])
        galeri_api._KAYIT.clear()
        guvenli_dosya_api.gd._BEKLEYEN.clear()
        return {"ok": True}

    app.mount("/ui", StaticFiles(directory=_DEPO / "frontend"), name="ui")
    return app


if __name__ == "__main__":
    import atexit
    import shutil
    atexit.register(shutil.rmtree, GECICI, True)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18831
    print(f"sınav sunucusu :{port} · geçici {GECICI}", flush=True)
    uvicorn.run(uygulama(), host="127.0.0.1", port=port, log_level="warning")

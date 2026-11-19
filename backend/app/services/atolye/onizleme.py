"""Site önizleme sunucusu — Yuki Atölye v2, Faz 1.

Atölye kökünü `http://127.0.0.1:<port>/<tür>/<ad>/<yol>` olarak SALT-OKUNUR sunar.
Varsayılan port 8011 (`YUKI_ATOLYE_ONIZLEME_PORT`). Doğrulayıcı aynı işleyiciyi geçici
bir portta açar → model ne ölçülüyorsa kullanıcı onu görür.

Güvenlik (Yuki'nin ürettiği sayfa GÜVENİLMEZ içeriktir):
  · Yalnız 127.0.0.1'e bağlanır; `Host` başlığı 127.0.0.1/localhost:<port> değilse 403
    (DNS rebinding: yabancı ad bu sunucuya çözülse bile sayfa açılmaz).
  · Her yanıtta `Content-Security-Policy: sandbox allow-scripts …` — belge OPAK köken
    olur: localStorage/çerez yok (uygulamanın oturum
    anahtarı uygulama kökeninde, oraya ulaşılamaz), `connect-src 'none'` → fetch/XHR/WebSocket yok, dış kaynak yok.
  · Yol çözümü çalışma alanı kilidinden (`alan.guvenli_yol`) geçer: `..`, mutlak yol,
    sembolik bağ ve `.gorev/` (görev kaydı) reddedilir; son bileşen `O_NOFOLLOW`.
  · Yalnız GET/HEAD; uzantı izin listesi dışı dosya 404.
"""

from __future__ import annotations

import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from app.services.atolye import alan

VARSAYILAN_PORT = 8011
HOST = "127.0.0.1"

# 'self' sandbox'lı belgede de sunucu URL'sinin kökenine eşleşir (Chromium'da ölçüldü,
# tests/test_atolye_site.py). allow-same-origin YOK → opak köken; allow-popups/forms YOK.
# 🔴 `Cross-Origin-Resource-Policy: same-origin` EKLEME: opak kökenli belgenin kendi
# css/svg/js istekleri "cross-site" sayılır ve hepsi ERR_BLOCKED_BY_RESPONSE olur (ölçüldü).
CSP = ("sandbox allow-scripts; default-src 'none'; img-src 'self' data:; "
       "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
       "font-src 'self' data:; media-src 'self'; connect-src 'none'; form-action 'none'; "
       "base-uri 'none'; frame-src 'none'; object-src 'none'; worker-src 'none'; "
       "manifest-src 'none'")

TURLER_MIME = {
    ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
    ".ico": "image/x-icon", ".json": "application/json", ".txt": "text/plain; charset=utf-8",
    ".woff2": "font/woff2",
}
_PARCA = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


def isleyici_sinifi(kok: Path, port_al):
    """`kok` atölye köküne bağlı işleyici. `port_al()` dinlenen portu döner (Host kapısı)."""

    class _Isleyici(BaseHTTPRequestHandler):
        server_version = "YukiAtolyeOnizleme"
        sys_version = ""

        def log_message(self, *a):        # stderr'e erişim günlüğü basma
            pass

        def _gonder(self, kod: int, govde: bytes, tip: str = "text/plain; charset=utf-8",
                    bas: bool = True) -> None:
            self.send_response(kod)
            self.send_header("Content-Type", tip)
            self.send_header("Content-Length", str(len(govde)))
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if bas:
                self.wfile.write(govde)

        def _host_uygun(self) -> bool:
            port = port_al()
            return (self.headers.get("Host") or "") in (f"{HOST}:{port}", f"localhost:{port}")

        def _coz(self) -> Path | None:
            yol = unquote(urlsplit(self.path).path)
            parcalar = [p for p in yol.split("/") if p != ""]
            if len(parcalar) < 2 or not _PARCA.match(parcalar[0]) or not _PARCA.match(parcalar[1]):
                return None
            alan_kok = kok / parcalar[0] / parcalar[1]
            if alan_kok.is_symlink() or not alan_kok.is_dir():
                return None
            rel = "/".join(parcalar[2:])
            if not rel or yol.endswith("/"):
                rel = (rel + "/index.html").lstrip("/")
            try:
                hedef = alan.guvenli_yol(alan_kok, rel)
            except alan.AlanHatasi:
                return None
            return hedef

        def _isle(self, bas: bool) -> None:
            if not self._host_uygun():
                return self._gonder(403, b"Host kabul edilmedi", bas=bas)
            hedef = self._coz()
            if hedef is None:
                return self._gonder(404, b"yok", bas=bas)
            tip = TURLER_MIME.get(hedef.suffix.lower())
            if tip is None:
                return self._gonder(404, b"yok", bas=bas)
            try:
                fd = os.open(hedef, os.O_RDONLY | os.O_NOFOLLOW)
            except OSError:
                return self._gonder(404, b"yok", bas=bas)
            with os.fdopen(fd, "rb") as f:
                veri = f.read(alan.MAKS_BOYUT + 1)
            if len(veri) > alan.MAKS_BOYUT:
                return self._gonder(413, b"dosya cok buyuk", bas=bas)
            self._gonder(200, veri, tip, bas=bas)

        def do_GET(self):
            self._isle(True)

        def do_HEAD(self):
            self._isle(False)

        def _yasak(self):
            self._gonder(405, b"yalniz GET/HEAD")

        do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _yasak

    return _Isleyici


class OnizlemeSunucusu:
    """Arka plan iş parçacığında koşan önizleme. `port=0` → işletim sistemi boş port seçer."""

    def __init__(self, kok: Path, port: int = VARSAYILAN_PORT) -> None:
        self.kok = Path(kok)
        self._srv = ThreadingHTTPServer((HOST, port), isleyici_sinifi(self.kok, lambda: self.port))
        self._srv.daemon_threads = True
        self.port = self._srv.server_address[1]
        self._is = threading.Thread(target=self._srv.serve_forever, name="atolye-onizleme",
                                    daemon=True)

    def baslat(self) -> "OnizlemeSunucusu":
        self._is.start()
        return self

    def kapat(self) -> None:
        self._srv.shutdown()
        self._srv.server_close()

    def url(self, tur: str, ad: str) -> str:
        return f"http://{HOST}:{self.port}/{tur}/{ad}/"

    def __enter__(self):
        return self.baslat()

    def __exit__(self, *a):
        self.kapat()


_paylasilan: OnizlemeSunucusu | None = None
_kilit = threading.Lock()


def paylasilan(kok: Path) -> OnizlemeSunucusu:
    """Süreç başına tek önizleme (ilk istekte açılır). Port `YUKI_ATOLYE_ONIZLEME_PORT`."""
    global _paylasilan
    with _kilit:
        if _paylasilan is None:
            port = int(os.environ.get("YUKI_ATOLYE_ONIZLEME_PORT") or VARSAYILAN_PORT)
            _paylasilan = OnizlemeSunucusu(kok, port).baslat()
        return _paylasilan

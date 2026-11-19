"""Tarayıcıyla "Continue with ChatGPT" girişi — 127.0.0.1 geri dönüş dinleyicisi.

Uygulamadan: Ayarlar'daki "Continue with ChatGPT" düğmesi (`/api/chatgpt/giris`).
Komut satırından (backend dizininden):
    python -m app.services.chatgpt_plan.giris            # giriş / yeniden giriş
    python -m app.services.chatgpt_plan.giris --durum    # sır basmadan özet
    python -m app.services.chatgpt_plan.giris --dene     # model listesi + tek kısa istek
    python -m app.services.chatgpt_plan.giris --cikis    # refresh token iptal + yerel sil

Belge kuralları: dinleyici tarayıcıdan ÖNCE açılır · `localhost` değil `127.0.0.1` ·
yol `/auth/callback` · aynı deneme içinde redirect_uri birebir aynı.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from app.services.chatgpt_plan import kimlik

_TAMAM_SAYFA = (
    "<!doctype html><meta charset=utf-8><title>Yuki</title>"
    "<body style='font-family:sans-serif;padding:2em'>"
    "<h2>Yuki: ChatGPT bağlantısı alındı.</h2><p>Bu sekmeyi kapatabilirsin.</p>"
).encode("utf-8")


class _Dinleyici:
    """Tek bir `/auth/callback` isteğini bekleyen yerel sunucu."""

    def __init__(self, port: int) -> None:
        self.sonuc: dict[str, str] | None = None
        self._olay = threading.Event()
        dis = self

        class _H(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                u = urlparse(self.path)
                if u.path != kimlik.GERI_DONUS_YOLU:
                    self.send_response(404)
                    self.end_headers()
                    return
                dis.sonuc = {k: v[0] for k, v in parse_qs(u.query).items()}
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(_TAMAM_SAYFA)
                dis._olay.set()

            def log_message(self, *_a: Any) -> None:  # sorgu (code) log'a düşmesin
                return

        try:
            self.sunucu = HTTPServer(("127.0.0.1", port), _H)
        except OSError:
            # Belge: sonraki girişler başka port kullanabilir (yalnız port değişir).
            self.sunucu = HTTPServer(("127.0.0.1", 0), _H)
        self.port = self.sunucu.server_address[1]
        self._is = threading.Thread(target=self.sunucu.serve_forever, daemon=True)
        self._is.start()

    @property
    def redirect_uri(self) -> str:
        return f"http://127.0.0.1:{self.port}{kimlik.GERI_DONUS_YOLU}"

    def bekle(self, zaman_asimi: float) -> dict[str, str] | None:
        self._olay.wait(zaman_asimi)
        return self.sonuc

    def kapat(self) -> None:
        self.sunucu.shutdown()
        self.sunucu.server_close()


def giris(
    ac: Callable[[str], Any] = webbrowser.open,
    port: int = kimlik.VARSAYILAN_PORT,
    zaman_asimi: float = 300.0,
    anahtar_bulucu: kimlik.JwksAnahtarBulucu | None = None,
    yeni_hesap: bool = False,
) -> kimlik.Kayit:
    mevcut = None if yeni_hesap else kimlik.oku()
    dinleyici = _Dinleyici(port)          # 🔴 tarayıcıdan ÖNCE
    try:
        deneme = kimlik.deneme_baslat(dinleyici.redirect_uri, mevcut)
        url = kimlik.yetki_url(deneme, mevcut)
        if not ac(url):
            # id_token_hint taşıyabilir — log'a değil, yalnız kullanıcının terminaline.
            print("Tarayıcı açılamadı. Bu adresi elle aç:\n" + url, file=sys.stderr)
        sorgu = dinleyici.bekle(zaman_asimi)
        if sorgu is None:
            raise kimlik.GeriDonusHatasi(f"{int(zaman_asimi)} sn içinde tarayıcı dönüşü gelmedi")
        return kimlik.kod_degistir(deneme, sorgu, mevcut, anahtar_bulucu)
    finally:
        dinleyici.kapat()


def _port_bos(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _dene() -> int:
    """Model listesi + tek kısa istek. Gerçek kotadan bir istek yer."""
    import asyncio

    from app.services.chatgpt_plan.istemci import ChatGPTAsyncClient

    async def _calis() -> int:
        i = ChatGPTAsyncClient()
        modeller = await i.modeller(zorla=True)
        print("Modeller:", ", ".join(modeller) if modeller else "(liste alınamadı)")
        if not modeller:
            return 1
        cevap = await i.chat.completions.create(
            model=modeller[0],
            messages=[{"role": "user", "content": "Reply with exactly: Token sharing works."}],
        )
        print("Cevap:", cevap.choices[0].message.content)
        return 0

    return asyncio.run(_calis())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Yuki — ChatGPT ile resmî giriş")
    ap.add_argument("--durum", action="store_true")
    ap.add_argument("--dene", action="store_true")
    ap.add_argument("--cikis", action="store_true")
    ap.add_argument("--port", type=int, default=kimlik.VARSAYILAN_PORT)
    a = ap.parse_args(argv)

    if a.durum:
        print(json.dumps(kimlik.durum(), ensure_ascii=False, indent=2))
        return 0
    if a.cikis:
        print(json.dumps(kimlik.cikis(), ensure_ascii=False))
        return 0
    if a.dene:
        return _dene()

    if not _port_bos(a.port):
        print(f"Not: {a.port} dolu, boş bir port seçilecek.", file=sys.stderr)
    kayit = giris(port=a.port)
    print("Giriş tamam. Plan kullanımı:", "AÇIK" if kayit.plan_acik else
          "KAPALI (izin verilmedi — Yuki bu yolla konuşamaz)")
    return 0 if kayit.plan_acik else 2


if __name__ == "__main__":
    raise SystemExit(main())

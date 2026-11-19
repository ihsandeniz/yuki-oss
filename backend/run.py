#!/usr/bin/env python3
"""Yuki backend launcher."""

import os

import uvicorn

from app import ebeveyn_bekcisi
from app.config import HOST, PORT

def sunucu_ayarlari() -> dict:
    """uvicorn ayarları — test bunları gerçek sunucuyla ölçer (tests/test_vekil_basligi.py).

    🔴 `proxy_headers=False` ŞART: uvicorn varsayılanı loopback'ten gelen istekte istemci adresini
    `X-Forwarded-For`'dan yeniden yazar. Bu bilgisayardaki herhangi bir program ya da DNS rebinding'le
    gelen bir site başlığı ekleyip "uzak" görünür, yerel kapının Host + oturum çerezi kuralını ve parola
    deneme sayacını atlatırdı (denetim 2026-11-16, SEC-F001/F002). Yuki vekil arkasında koşmaz; tünel
    (`tailscale serve`, cloudflared) loopback'ten bağlanır ve yerel kurallardan geçer → app/yerel_kapi.py."""
    return dict(host=HOST, port=PORT, ws_ping_interval=None, ws_ping_timeout=None, proxy_headers=False)


if __name__ == "__main__":
    # Paketlenmiş üründe (AppImage) reload KAPALI olmalı: read-only mount'ta
    # dosya izleme + reloader-child süreci sorun çıkarır. Geliştirmede varsayılan açık.
    reload = os.getenv("YUKI_RELOAD", "true").lower() in ("1", "true", "yes")
    # Yuki penceresi zarifsiz ölürse (SIGKILL, oturum kapanışı) motor öksüz kalmasın
    ebeveyn_bekcisi.baslat()
    ayarlar = sunucu_ayarlari()
    if reload:
        uvicorn.run("app.main:app", reload=True, **ayarlar)
    else:
        # Server nesnesi elimizde dursun: motor kendi isteğiyle zarifçe kapanabilsin.
        # Windows'ta SIGTERM yok — `POST /api/motor/kapan` bunun karşılığı → app/motor_kapanis.py
        from app import motor_kapanis
        sunucu = uvicorn.Server(uvicorn.Config("app.main:app", **ayarlar))
        motor_kapanis.kur(sunucu)
        sunucu.run()

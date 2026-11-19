"""Yerel motor kapısı — Host + Origin + oturum anahtarı (v0.8.1 güvenlik yaması, 2026-10-06).

## Neden var
Motor yalnız `127.0.0.1`'de dinlediği için "dışarıdan erişilemez" sayılıyordu. Ama kullanıcının **tarayıcısı**
da aynı makinede: açtığı herhangi bir site `http://127.0.0.1:8791/...`'e istek atabilir, link verebilir ya
da DNS rebinding ile kendi adını 127.0.0.1'e çözdürüp aynı kökenden konuşabilir. Varsayılan kullanıcı
kurulumunda `AUTH_TOKEN` boş ve uygulama kilidi isteğe bağlı → `auth_middleware` hiç devreye girmiyordu
(denetim 2026-10-06: C1, H1, H3, H7).

## Üç kural, tek yer
1. **Host** — istek bu bilgisayardan geliyorsa `Host` başlığı `127.0.0.1` / `localhost` / `::1` (ya da
   açıkça izin verilen tünel adı) olmalı. DNS rebinding'i keser: saldırganın sayfası `evil.example`
   adıyla gelir. Ağdan gelen istek bu kurala girmez — onu `ag_ayari` + uygulama kilidi korur.
2. **Origin** — `Origin` başlığı varsa ya izinli listede (`ALLOWED_ORIGINS`) ya da isteğin kendi adresi
   (aynı köken, ör. ağa açık kurulumda telefondan gelen arayüz) olmalı. `null` reddedilir.
3. **Oturum anahtarı** — Electron her açılışta rastgele bir anahtar üretir, motora `YUKI_OTURUM_ANAHTARI`
   ile verir ve KENDİ oturumuna HttpOnly + SameSite=Strict çerez olarak koyar. Bu makineden gelen her
   istek bu çerezi taşımalı. Çerez seçildi çünkü `<img>`, `<video>`, `<iframe>` ve WebSocket onu kendiliğinden
   gönderir — başlık gönderemeyen yolların kırılması (UI-F003 sınıfı) burada olmaz. Kullanıcının normal
   tarayıcısında bu çerez YOKTUR: o tarayıcıdan gelen link/fetch/rebinding 401 alır.
   Anahtar verilmemişse (geliştirici `start.sh` ile elle çalıştırıyorsa) bu kural kapalıdır; 1 ve 2 açıktır.

## 🔴 Saf ASGI — `@app.middleware("http")` DEĞİL
Starlette'in http middleware'i WebSocket'e HİÇ uğramaz. Eski kapılar WS'leri tek tek handler'da korumaya
çalışıyordu ve `/ws/screen` Origin denetimini atlamıştı (H3). Bu katman `http` ve `websocket` kapsamlarının
ikisine de bakar; yeni eklenen bir WS ucu da kendiliğinden korunur.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit

from app.services.ag_ayari import loopback_istemci, vekil_basligi_var

log = logging.getLogger(__name__)

CEREZ_ADI = "yuki_oturum"
YEREL_HOSTLAR = frozenset({"127.0.0.1", "localhost", "::1"})


def oturum_anahtari() -> str:
    """Electron'un verdiği anahtar. Okuma her çağrıda ortamdan — testler değiştirebilsin."""
    return os.getenv("YUKI_OTURUM_ANAHTARI", "").strip()


def _host_adi(deger: str) -> str:
    """`127.0.0.1:8791` → `127.0.0.1` · `[::1]:8791` → `::1` · küçük harf."""
    deger = (deger or "").strip().lower()
    if deger.startswith("["):
        return deger[1:deger.find("]")] if "]" in deger else ""
    return deger.rsplit(":", 1)[0] if deger.count(":") == 1 else deger


def ek_hostlar() -> frozenset[str]:
    """Tünel/dış erişim adı: `ALLOWED_ORIGINS_EXTRA`'daki kökenlerin host'u + `ALLOWED_HOSTS_EXTRA`."""
    hostlar: set[str] = set()
    for o in os.getenv("ALLOWED_ORIGINS_EXTRA", "").split(","):
        h = urlsplit(o.strip()).hostname if o.strip() else None
        if h:
            hostlar.add(h.lower())
    for h in os.getenv("ALLOWED_HOSTS_EXTRA", "").split(","):
        if h.strip():
            hostlar.add(_host_adi(h))
    return frozenset(hostlar)


def koken_izinli(koken: str, host_basligi: str, sema: str, izinli) -> bool:
    """Origin kuralı — kapı ve WS uçları AYNI kuralı kullanır (eskiden uçta ayrı, `startsWith`'li bir kopya vardı).
    İzinli listede ya da isteğin kendi adresi (aynı köken). `null` her zaman red."""
    k = (koken or "").strip().rstrip("/").lower()
    if not k or k == "null":
        return False
    izinli = {o.rstrip("/").lower() for o in izinli}
    ayni = bool(host_basligi) and k == f"{sema}://{host_basligi.strip().lower()}"
    return k in izinli or ayni


class YerelKapi:
    """Saf ASGI middleware. `acik_yollar`/`acik_onekler`: kimliksiz erişilmesi ZORUNLU olanlar
    (statik dosyalar, /health, kilit ekranı, OAuth geri dönüşü — sistem tarayıcısından gelir)."""

    def __init__(self, app, acik_yollar=(), acik_onekler=(), izinli_kokenler=(), token_kabul=None):
        self.app = app
        self.acik_yollar = frozenset(acik_yollar)
        self.acik_onekler = tuple(acik_onekler)
        self.izinli_kokenler = frozenset(o.rstrip("/").lower() for o in izinli_kokenler)
        # (token) -> bool : AUTH_TOKEN ya da uygulama kilidi oturumu geçerli mi
        self.token_kabul = token_kabul or (lambda _t: False)

    async def __call__(self, scope, receive, send):
        tur = scope.get("type")
        if tur not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        basliklar = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        istemci = (scope.get("client") or (None, None))[0]
        # Vekil başlığı taşıyan istek de YEREL kurallardan geçer: uvicorn `proxy_headers` açıksa (ör. README'deki
        # `python -m uvicorn` yolu) loopback istemcinin adresini bu başlıktan yeniden yazmıştır, asıl adres
        # kayboldu. Başlığı ekleyen bu bilgisayardaki bir program ya da rebinding'li bir site "uzak" görünüp
        # Host + çerez kuralını atlatırdı (denetim 2026-11-16, SEC-F001). Ağdan gelen gerçek istemci (telefon)
        # bu başlığı göndermez; gönderirse sıkı kural uygulanır (güvenli yön).
        yerel = loopback_istemci(istemci) or vekil_basligi_var(basliklar)
        host_basligi = basliklar.get("host", "")
        host = _host_adi(host_basligi)

        # ── 1) Host ──────────────────────────────────────────────────────
        if yerel and host not in YEREL_HOSTLAR and host not in ek_hostlar():
            return await self._reddet(scope, receive, send, 403, "host")

        # ── 2) Origin ────────────────────────────────────────────────────
        koken = basliklar.get("origin")
        if koken is not None:
            sema = "https" if scope.get("scheme") in ("https", "wss") else "http"
            if not koken_izinli(koken, host_basligi, sema, self.izinli_kokenler):
                return await self._reddet(scope, receive, send, 403, "origin")

        # ── 3) Oturum anahtarı ───────────────────────────────────────────
        anahtar = oturum_anahtari()
        if anahtar and yerel and not self._acik_mi(scope):
            if not (self._cerez_gecerli(basliklar, anahtar) or self._token_gecerli(scope, basliklar)):
                return await self._reddet(scope, receive, send, 401, "oturum")

        return await self.app(scope, receive, send)

    # ── yardımcılar ──────────────────────────────────────────────────────
    def _acik_mi(self, scope) -> bool:
        yol = scope.get("path", "")
        if yol in self.acik_yollar or yol.startswith(self.acik_onekler):
            return True
        # CORS ön uçuşu çerez taşımaz; gövde dönmez, yetkiyi asıl istek ister.
        return scope.get("type") == "http" and scope.get("method") == "OPTIONS"

    @staticmethod
    def _cerez_gecerli(basliklar: dict, anahtar: str) -> bool:
        ham = basliklar.get("cookie", "")
        if not ham:
            return False
        try:
            c = SimpleCookie()
            c.load(ham)
        except Exception:
            return False
        m = c.get(CEREZ_ADI)
        return bool(m and m.value) and secrets.compare_digest(m.value, anahtar)

    def _token_gecerli(self, scope, basliklar: dict) -> bool:
        """Tünel/uzak arayüz: AUTH_TOKEN ya da kilit oturumu (Bearer veya ?token=)."""
        adaylar = []
        auth = basliklar.get("authorization", "")
        if auth.startswith("Bearer "):
            adaylar.append(auth[7:])
        qs = parse_qs((scope.get("query_string") or b"").decode("latin-1"))
        adaylar += qs.get("token", [])[:1]
        for t in adaylar:
            try:
                if t and self.token_kabul(t):
                    return True
            except Exception:
                log.debug("token denetimi hata verdi", exc_info=True)
        return False

    @staticmethod
    async def _reddet(scope, receive, send, kod: int, sebep: str):
        log.warning("yerel kapı reddetti: %s %s (%s)", scope.get("type"), scope.get("path"), sebep)
        if scope["type"] == "websocket":
            # Kabul etmeden kapatmak → sunucu el sıkışmayı 403 ile reddeder.
            await send({"type": "websocket.close", "code": 1008})
            return
        govde = json.dumps({"detail": "Unauthorized" if kod == 401 else "Forbidden"}).encode()
        await send({"type": "http.response.start", "status": kod,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(govde)).encode())]})
        await send({"type": "http.response.body", "body": govde})

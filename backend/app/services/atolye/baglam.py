"""İstek bağlamı — Atölye için "bu istek bu bilgisayardan mı?" işareti.

Atölye'nin iki kuralı bu işarete bağlıdır: dışarıdan (telefon, ağdaki başka cihaz,
vekil/tünel) açılan görev yalnız TASLAK olur (onay bekler), önizleme adresi ve DEVAM
yalnız bu bilgisayardan verilir.

Dış sayılır: istemci loopback değilse, vekil/tünel başlığı varsa ya da `Host` yerel
değilse. İşaretlenmemiş bağlam varsayılan DIŞ'tır (fail-closed): işaretlemeyi unutan
bir giriş en kötü ihtimalle yetki kaybeder, kazanmaz. Başında HTTP isteği olmayan iç
girişler (testler, zamanlayıcı) `yerel_baglam()` ile açıkça yerel olur.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar

log = logging.getLogger(__name__)

_dis: ContextVar[bool] = ContextVar("yuki_atolye_dis", default=True)

# Tünelin/vekilin eklediği, doğrudan loopback isteğinde bulunmayan başlıklar.
_VEKIL_BASLIKLARI = ("x-forwarded-for", "cf-connecting-ip", "cf-ray", "x-real-ip",
                     "forwarded", "x-forwarded-host")
_YEREL_HOSTLAR = {"localhost", "127.0.0.1", "::1", "[::1]", ""}


def _hesapla(request) -> bool:
    from app.services.ag_ayari import loopback_istemci
    basliklar = getattr(request, "headers", {})
    for b in _VEKIL_BASLIKLARI:
        if basliklar.get(b):
            return True
    istemci = getattr(getattr(request, "client", None), "host", None)
    if not loopback_istemci(istemci):
        return True
    host = (basliklar.get("host", "") or "").rsplit(":", 1)[0].strip().lower()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return host not in _YEREL_HOSTLAR


def isaretle(request) -> bool:
    """Giriş ucunda çağrılır; dış mı? (True = dış). Hata → dış."""
    try:
        dis = _hesapla(request)
    except Exception:
        log.exception("atölye bağlamı belirlenemedi — dış varsayıldı")
        dis = True
    _dis.set(dis)
    return dis


def dis_mi() -> bool:
    return _dis.get()


def dis_yaz(dis: bool) -> None:
    """Görevin asyncio görevi kendi bağlamını görevin KAYNAĞINA göre işaretler."""
    _dis.set(bool(dis))


@contextmanager
def yerel_baglam():
    """İstek-dışı iç giriş (test, zamanlayıcı) için açık 'yerel' bağlam."""
    tok = _dis.set(False)
    try:
        yield
    finally:
        _dis.reset(tok)

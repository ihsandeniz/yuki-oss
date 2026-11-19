"""Kamera görüşü — "Yuki bak": kameradan tek kare al, YEREL görsel modele sor.

Akış: `bak(soru)` → açık `/ws/gorus` bağlantısından sıradaki kareyi ister (`kare_iste`) →
kare bellekte base64'e çevrilir → bu bilgisayarda çalışan OpenAI uyumlu bir görsel modele
(Ollama, LM Studio, llama.cpp sunucusu…) gider → kısa betimleme döner.

Gizlilik sınırı (karar: görüntü yalnız yerelde, buluta gitmez):
  · Kare TUTULMAZ. `/ws/gorus` her kareyi `kare_geldi` ile buraya uzatır; bekleyen bir
    bakış isteği yoksa hiçbir şey saklanmaz. Dosya, günlük, önbellek yok.
  · Model adresi YALNIZ bu bilgisayar olabilir (`127.0.0.1`, `::1`, `localhost`).
    Başka bir adres yazılmışsa bakış reddedilir; bulut sağlayıcıya ya da genel sohbet
    modeline düşülmez. Yerel model yoksa cevap açık bir hata cümlesidir.
  · Yönlendirme izlenmez (yerel sunucu dışarıya yönlendirse bile kare gitmez).

Ayarlar (ortamdan, istek anında okunur):
  GORUS_MODEL_URL  OpenAI uyumlu taban adres  (varsayılan http://127.0.0.1:11434/v1 — Ollama)
  GORUS_MODEL      görsel model adı            (varsayılan qwen2.5vl:3b)
"""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import logging
import os
import time
from typing import Awaitable, Callable
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

VARSAYILAN_URL = "http://127.0.0.1:11434/v1"
VARSAYILAN_MODEL = "qwen2.5vl:3b"
MAX_BAYT = 400_000          # 640×480 JPEG ≈ 30-80 KB; fazlası yanlış istemci
KARE_BEKLE_SN = 4.0         # istemci saniyede ≤1 kare yollar
BAK_ARALIK_SN = 5.0         # iki bakış arası en az (aracı döngüye sokan modele karşı)
MAX_TOKEN = 160
ISTEK_SN = 90.0

SISTEM = (
    "Bir kameradan gelen TEK kareyi betimliyorsun. Kullanıcının dilinde, en çok 2 kısa cümle yaz. "
    "Yalnız gerçekten gördüğünü söyle; emin değilsen 'net göremiyorum' de. "
    "Bir şeyin olmadığını iddia etme. Kişinin kim olduğunu tahmin etme."
)
VARSAYILAN_SORU = "Bu karede ne görüyorsun?"


class GorusYok(RuntimeError):
    """Bakış yapılamadı; mesaj kullanıcıya olduğu gibi söylenebilir."""


# ── kare doğrulama ──────────────────────────────────────────────────────────
def kare_gecerli(veri: bytes) -> bool:
    """Yalnız boyutu makul JPEG kabul edilir (başlık FFD8, kuyruk FFD9)."""
    return (isinstance(veri, (bytes, bytearray)) and 4 <= len(veri) <= MAX_BAYT
            and veri[:2] == b"\xff\xd8" and veri[-2:] == b"\xff\xd9")


# ── model adresi: yalnız bu bilgisayar ──────────────────────────────────────
def model_url() -> str:
    return (os.getenv("GORUS_MODEL_URL", "").strip() or VARSAYILAN_URL).rstrip("/")


def model_adi() -> str:
    return os.getenv("GORUS_MODEL", "").strip() or VARSAYILAN_MODEL


def yerel_adres_mi(url: str) -> bool:
    try:
        p = urlsplit(url)
    except ValueError:
        return False
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        return False
    host = p.hostname.lower()
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback


def _adres_denetle() -> str:
    url = model_url()
    if not yerel_adres_mi(url):
        raise GorusYok("görsel model adresi bu bilgisayar değil (GORUS_MODEL_URL); "
                       "kamera görüntüsü dışarı gönderilmez")
    return url


# ── kare köprüsü (/ws/gorus → bakış) ────────────────────────────────────────
_istemci = 0
_bekleyenler: list[asyncio.Future] = []


def istemci_sayisi() -> int:
    return _istemci


def istemci_baglandi() -> None:
    global _istemci
    _istemci += 1


def istemci_ayrildi() -> None:
    global _istemci
    _istemci = max(0, _istemci - 1)
    if _istemci == 0:
        for f in _bekleyenler:
            if not f.done():
                f.set_exception(GorusYok("kamera bağlantısı kapandı"))
        _bekleyenler.clear()


def kare_geldi(veri: bytes) -> None:
    """`/ws/gorus` her geçerli karede çağırır. Bekleyen istek yoksa HİÇBİR ŞEY saklanmaz."""
    if not _bekleyenler:
        return
    for f in _bekleyenler:
        if not f.done():
            f.set_result(bytes(veri))
    _bekleyenler.clear()


async def kare_iste(sure: float = KARE_BEKLE_SN) -> bytes:
    if _istemci <= 0:
        raise GorusYok("kamera açık değil (önce kamera görüşünü başlatın)")
    f = asyncio.get_running_loop().create_future()
    _bekleyenler.append(f)
    try:
        return await asyncio.wait_for(f, sure)
    except asyncio.TimeoutError:
        raise GorusYok("kameradan kare gelmedi (kamera başka bir uygulamada olabilir)") from None
    finally:
        if f in _bekleyenler:
            _bekleyenler.remove(f)


# ── yerel model ─────────────────────────────────────────────────────────────
IstekFn = Callable[[str, str, dict | None, float], Awaitable[tuple[int, dict]]]


async def _http(metot: str, url: str, govde: dict | None, sure: float) -> tuple[int, dict]:
    import httpx
    async with httpx.AsyncClient(timeout=sure, follow_redirects=False, trust_env=False) as c:
        r = await c.request(metot, url, json=govde)
        try:
            veri = r.json()
        except ValueError:
            veri = {}
        return r.status_code, veri if isinstance(veri, dict) else {}


_istek: IstekFn = _http   # testler sahte yürütücü koyar


def _model_yok_metni(url: str) -> str:
    return (f"yerel görsel model bulunamadı ({url}). Kamera görüşü bu bilgisayarda çalışan bir "
            f"görsel model ister: örneğin Ollama kurup `ollama pull {VARSAYILAN_MODEL}` çalıştırın "
            "ya da GORUS_MODEL_URL / GORUS_MODEL ayarını kendi yerel sunucunuza göre verin")


async def model_durumu(sure: float = 2.0) -> dict:
    """{"hazir": bool, "url", "model", "neden"}. Ağ isteği yalnız yerel adrese gider."""
    url, ad = model_url(), model_adi()
    if not yerel_adres_mi(url):
        return {"hazir": False, "url": url, "model": ad,
                "neden": "model adresi bu bilgisayar değil; görüntü dışarı gönderilmez"}
    try:
        kod, veri = await _istek("GET", url + "/models", None, sure)
    except Exception:
        return {"hazir": False, "url": url, "model": ad, "neden": _model_yok_metni(url)}
    if kod != 200:
        return {"hazir": False, "url": url, "model": ad, "neden": _model_yok_metni(url)}
    adlar = {str(m.get("id", "")) for m in (veri.get("data") or []) if isinstance(m, dict)}
    if ad not in adlar:
        return {"hazir": False, "url": url, "model": ad,
                "neden": f"yerel sunucu açık ama '{ad}' modeli yüklü değil (GORUS_MODEL)"}
    return {"hazir": True, "url": url, "model": ad, "neden": ""}


async def _sor(jpeg: bytes, soru: str) -> str:
    url = _adres_denetle()
    b64 = base64.b64encode(jpeg).decode()
    govde = {
        "model": model_adi(), "max_tokens": MAX_TOKEN, "temperature": 0.2, "stream": False,
        "messages": [
            {"role": "system", "content": SISTEM},
            {"role": "user", "content": [
                {"type": "text", "text": soru},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
            ]},
        ],
    }
    del b64
    try:
        kod, veri = await _istek("POST", url + "/chat/completions", govde, ISTEK_SN)
    except Exception as e:
        raise GorusYok(_model_yok_metni(url) + f" [{type(e).__name__}]") from None
    finally:
        govde.clear()
    if kod == 404:
        raise GorusYok(f"yerel sunucu '{model_adi()}' modelini tanımıyor (GORUS_MODEL)")
    if kod != 200:
        raise GorusYok(f"yerel görsel model hata verdi (HTTP {kod})")
    metin = (((veri.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
    metin = metin.strip() if isinstance(metin, str) else ""
    if not metin:
        raise GorusYok("yerel görsel model boş cevap verdi")
    return metin[:600]


# ── bakış girişi ────────────────────────────────────────────────────────────
_kilit = asyncio.Lock()
_son_bakis = 0.0


def _sifirla() -> None:
    """Yalnız testler için."""
    global _istemci, _son_bakis, _kilit
    _istemci = 0
    _son_bakis = 0.0
    _bekleyenler.clear()
    _kilit = asyncio.Lock()


async def bak(soru: str = "") -> dict:
    """{"ok": bool, "metin": str}. Kare yalnız bu çağrı süresince bellekte durur."""
    global _son_bakis
    if _kilit.locked():
        return {"ok": False, "metin": "Zaten bakıyorum, bir saniye."}
    if time.monotonic() - _son_bakis < BAK_ARALIK_SN:
        return {"ok": False, "metin": "Az önce baktım; birkaç saniye sonra yeniden bakabilirim."}
    soru = (soru or "").strip()[:300] or VARSAYILAN_SORU
    async with _kilit:
        _son_bakis = time.monotonic()
        try:
            _adres_denetle()              # kareyi istemeden ÖNCE: adres yerel değilse kare hiç alınmaz
            jpeg = await kare_iste()
        except GorusYok as e:
            return {"ok": False, "metin": f"Şu an göremiyorum: {e}."}
        try:
            metin = await _sor(jpeg, soru)
        except GorusYok as e:
            return {"ok": False, "metin": f"Şu an göremiyorum: {e}."}
        finally:
            del jpeg
        logger.info("gorus: bakış tamam")
        return {"ok": True, "metin": metin}

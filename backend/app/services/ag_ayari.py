"""Yuki'yi yerel ağa açma — kullanıcının ayarı (HQ › CİHAZLAR, 2026-10-01).

Önceden tek yol ortam değişkeniydi (`HOST=0.0.0.0`); paketli üründe kullanıcının onu yazacağı bir yer yoktu.
Şimdi `config.user.json`'daki `AG_ACIK` ayarı: `config.py` açılışta okur, HOST'u 0.0.0.0 yapar, `run.py` uvicorn'u
o HOST'la başlatır → **ayar yeniden başlatınca geçerli olur** (soket süreç açılırken bağlanır).

## 🔴 Güvenlik kapısı — dört yerde, tek kural: kilitsiz ağ AÇILMAZ

Uygulama kilidi (parola) kurulu değilse aynı Wi-Fi'deki herkes Yuki'nin her ucuna girer. Bu yüzden:
1. **Açma ucu** (`PUT /api/devices/ag`) kilit yoksa 409 döner — arayüz düğmeyi pasif tutsa da sunucu da uygular.
2. **Açılış kapısı** (`config.py`): ayar açık ama kilit artık yok → HOST 127.0.0.1 kalır, ayar kapatılır, günlüğe yazılır.
3. **Çalışırken kilit kalkarsa**: süreç hâlâ ağda dinler (soket yeniden bağlanamaz) → ağdan gelen HER istek 403
   (`uzak_izin`), yerel istek etkilenmez. Yeniden başlatınca (2) devreye girer.
4. **WebSocket'ler** (`ws_izinli`): http middleware'i WebSocket'e HİÇ uğramaz (Starlette). `/ws/realtime`, `/ws/screen`
   ve `/ws/native` yalnız `AUTH_TOKEN`'a bakıyordu; üründe o boş → kilit kuruluyken bile ağdan token'sız bağlanılırdı
   (`/ws/screen` = ekran akışı). Ağdan gelen soket artık kilit oturum token'ı ister; yerel soket eskisi gibi.

Kapatmak her zaman serbesttir.
"""
from __future__ import annotations

import ipaddress
import logging
import secrets
import socket

from app import config as cfg
from app import config_manager

log = logging.getLogger(__name__)

LOOPBACK_HOSTLAR = ("127.0.0.1", "localhost", "::1", "")


def host_acik(host: str | None = None) -> bool:
    """Süreç loopback dışında dinleyecek şekilde mi başladı (HOST ayarı)?"""
    return (cfg.HOST if host is None else host) not in LOOPBACK_HOSTLAR


def kilit_kurulu() -> bool:
    """Uygulama kilidi var mı — **fail-closed**: okunamazsa YOK sayılır (ağ açılmaz)."""
    try:
        from app.services import app_lock
        return bool(app_lock.kurulu())
    except Exception:
        return False


def loopback_istemci(host: str | None) -> bool:
    """İstek bu bilgisayardan mı? (IPv4-eşlenmiş IPv6 dahil). Bilinmeyen/boş = uzak (fail-closed)."""
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback


# Vekil başlıkları. uvicorn `proxy_headers` açıkken (README'deki `python -m uvicorn` yolu run.py'den geçmez)
# loopback'ten gelen istekte istemci adresini `X-Forwarded-For`'dan yeniden yazar; asıl adres kaybolur.
VEKIL_BASLIKLARI = ("x-forwarded-for", "forwarded")


def vekil_basligi_var(basliklar) -> bool:
    """İstek bir vekil başlığı taşıyor mu? `basliklar`: küçük harfli dict ya da Starlette `Headers`."""
    return any((basliklar.get(b) or "").strip() for b in VEKIL_BASLIKLARI)


def deneme_anahtari(conn) -> str:
    """Parola/yüz deneme sayacının ve hız sınırının anahtarı (denetim 2026-11-16, SEC-F002).

    Vekil başlığı taşıyan HER istek tek kovaya ("vekil") düşer: başlığı her istekte değiştirmek sayacı
    sıfırlamaz, ve tünelden gelen yanlış denemeler bu bilgisayardaki sahibi (başlıksız 127.0.0.1)
    dışarıda bırakmaz. Başlığın DEĞERİ okunmaz — istemci onu uydurabilir."""
    if vekil_basligi_var(conn.headers):
        return "vekil"
    return (conn.client.host if conn.client else "-") or "-"


def uzak_izin(istemci: str | None, kilit: bool) -> bool:
    """Ağdan gelen istek geçebilir mi — YALNIZ `AG_ACIK` ile açılmış süreç için bir kural.

    Ayarla açıldı (`cfg.AG_ACIK_SUREC`) ama kilit artık yok → uzak istek reddedilir. Geliştiricinin elle koyduğu
    `HOST=0.0.0.0` (ayar değil) bu kuralın dışındadır: eski davranış korunur."""
    if not cfg.AG_ACIK_SUREC or kilit:
        return True
    return loopback_istemci(istemci)


def ws_izinli(ws) -> bool:
    """WebSocket kapısı (AUTH_TOKEN kontrolünden SONRA çağrılır). True = devam.

    HTTP ile AYNI kural (`main.auth_middleware`): kilit kuruluysa her istek — yerel ya da ağdan — kilit
    oturum token'ı ister. Eskiden yerel soket token'sız geçiyordu; kilit kuruluyken HTTP `/api/ping` 401
    alırken `/ws/realtime` ve `/ws/screen` (ekran akışı) aynı makinedeki herhangi bir programa açıktı
    (denetim 2026-11-16, API-F001).
    · kilit kurulu → kilit oturum token'ı (`?token=`) ya da AUTH_TOKEN şart (yerel + ağdan)
    · kilit yok + yerel soket → geçer (kilitsiz kurulumda HTTP de sormaz; çerezi YerelKapi denetler)
    · kilit yok + ağdan + süreç ayarla açılmış → RED
    · kilit yok + ağdan + ayar değil (geliştirici HOST'u) → eski davranış"""
    istemci = getattr(getattr(ws, "client", None), "host", None)
    kilit = kilit_kurulu()
    if not kilit:
        return loopback_istemci(istemci) or not cfg.AG_ACIK_SUREC
    token = ws.query_params.get("token", "")
    auth = getattr(cfg, "AUTH_TOKEN", "")
    if auth and token and secrets.compare_digest(token, auth):
        return True
    try:
        from app.services import app_lock
        return bool(token) and app_lock.oturum_gecerli(token)
    except Exception:
        return False


def dinleniyor(ip: str, port: int) -> bool:
    """Bu süreç `ip:port`tan GERÇEKTEN cevap veriyor mu — ayar değil, soket ölçülür.

    Kendi yerel ağ adresine bağlanmak yalnız 0.0.0.0'a (ya da o adrese) bağlı bir soketle başarılır; 127.0.0.1'e
    bağlı süreç reddeder. Güvenlik duvarını/VPN'i ÖLÇMEZ (dışarıdan gelen bağlantı ayrı) — panel bunu söyler."""
    if not host_acik() or loopback_istemci(ip):
        return False
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.4)
    try:
        return s.connect_ex((ip, int(port))) == 0
    except Exception:
        return False
    finally:
        s.close()


def ayar_acik() -> bool:
    return bool(getattr(cfg, "AG_ACIK", False))


def yaz(acik: bool) -> tuple[bool, str]:
    """Ayarı yaz (config.user.json) + bellekteki değeri güncelle. HOST'a DOKUNMAZ: süreç soketi açılışta
    bağlanmıştır, 'ağda' durumu ancak yeniden başlayınca değişir (ve `/ag` bunu soketten ölçer)."""
    ok, msg = config_manager.set_value("AG_ACIK", bool(acik))
    if ok:
        onceki = ayar_acik()
        cfg.AG_ACIK = bool(acik)
        if acik:
            cfg.AG_KILIT_DUSTU = False   # kullanıcı yeniden açtı → eski "kilit düştü" uyarısı biter
        try:
            from app.api import settings_api
            settings_api.bekleyen_isaretle("AG_ACIK", onceki, bool(acik))
        except Exception:  # pragma: no cover — bekleyen listesi yardımcı bilgi
            log.debug("bekleyen listesi güncellenemedi", exc_info=True)
    return ok, msg


def durum_ozeti(yerel_ip: str, port: int) -> dict:
    """Panelin ağ bölümü için tek paket. `durum` = kapali · acik-bekliyor · acik-dinliyor ·
    acik-ulasilamiyor · kapanis-bekliyor."""
    host_ac = host_acik()
    # Geliştirici `HOST=0.0.0.0`ı ortamdan verdiyse ayar kapalı olsa da süreç ağdadır; o durumda ayar
    # "açık" görünür (aksi hâlde yeşil ışıkla kapalı anahtar yan yana durur). Paketli kullanıcıda bu yol yok.
    ortamdan = host_ac and not getattr(cfg, "AG_ACIK_SUREC", False)
    ayar = ayar_acik() or ortamdan
    dinliyor = dinleniyor(yerel_ip, port) if host_ac else False
    if ayar and not host_ac:
        durum = "acik-bekliyor"            # ayar açık, süreç hâlâ 127.0.0.1'de → yeniden başlatma bekliyor
    elif ayar and dinliyor:
        durum = "acik-dinliyor"
    elif ayar:
        durum = "acik-ulasilamiyor"        # HOST açık ama kendi ağ adresimizden cevap yok (ağ yok?)
    elif host_ac:
        durum = "kapanis-bekliyor"         # ayar kapalı, süreç hâlâ ağda dinliyor
    else:
        durum = "kapali"
    return {
        "ag_ayari": ayar,
        "ag_durum": durum,
        "ortamdan": ortamdan,
        "dinleniyor": dinliyor,
        "kilit_kurulu": kilit_kurulu(),
        "yeniden_baslat_gerek": durum in ("acik-bekliyor", "kapanis-bekliyor"),
        "kilit_dustu": bool(getattr(cfg, "AG_KILIT_DUSTU", False)),
    }

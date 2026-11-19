"""Sunucu tarafı istek kapısı (SSRF) — URL özel/yerel bir adrese mi gidiyor.

İki tüketici: harita vekilleri (`api/map.py`, v0.8.1 C/H4) ve `browse_web` aracı
(`services/tools/network.py`, P1 E/H5). İkisi de yönlendirmeyi KENDİSİ izler ve
HER adımda bu kapıya sorar — `follow_redirects=True` tek başına ilk adresi korur.
"""
from __future__ import annotations

# Köken: harita vekilleri (2026-09-18, ürüne taşınırken eklendi); 10-06'da buraya taşındı.
#
# 🔴 Kişiselde tek kontrol `url.startswith("http")` idi. Kişisel makinede düşük
# riskli, SATILAN ÜRÜNDE değil: tarayıcıdan gelen herhangi bir adresi SUNUCU
# çeker → kullanıcının yerel ağındaki cihazlar (modem arayüzü, NAS, yazıcı),
# kendi backend'i (127.0.0.1:8001) ve bulut metadata adresleri (169.254.169.254)
# ürünün kendi ağ konumundan erişilebilir hâle gelirdi.
#
# Kapı fail-closed: çözümlenemeyen ad da REDDEDİLİR (DNS hatası "belki
# dışarıdadır" diye geçilmez).

_OZEL_AGLAR = None


def ozel_adres_mi(url: str) -> bool:
    """URL özel/yerel bir adrese mi gidiyor — DNS çözümlemesi dahil."""
    global _OZEL_AGLAR
    import ipaddress
    import socket
    from urllib.parse import urlparse

    if _OZEL_AGLAR is None:
        _OZEL_AGLAR = [
            ipaddress.ip_network(a) for a in (
                "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
                "169.254.0.0/16", "0.0.0.0/8", "100.64.0.0/10",
                "::1/128", "fc00::/7", "fe80::/10",
            )
        ]

    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return True
        host = p.hostname
        if not host:
            return True
        # Ad çözümle — "localhost" gibi adlar da yakalansın
        bilgi = socket.getaddrinfo(host, None)
        for kayit in bilgi:
            ip = ipaddress.ip_address(kayit[4][0].split("%")[0])
            # `::ffff:127.0.0.1` IPv4 ağlarında aranırken eşleşmez → önce IPv4'e indir (v0.8.1).
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                ip = ip.ipv4_mapped
            if any(ip in ag for ag in _OZEL_AGLAR) or not ip.is_global:
                return True
        return False
    except Exception:
        return True          # çözümlenemedi → REDDET (fail-closed)


def genel_ip(url: str) -> str | None:
    """Kapıdan geçen URL'nin BAĞLANILACAK adresi; geçmezse None (şema + DNS, fail-closed).

    Çözülen HER adres genel internette olmalı; dönen değer ilkidir. DNS-rebinding: çağıran bu
    IP'ye bağlanmalı — adı ikinci kez çözerse, iki çözüm arasında iç adrese dönen bir DNS kapıyı
    atlatır. (`ozel_adres_mi`'nin aynı kuralı; fark: geçerse adresi de verir.)"""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    if ozel_adres_mi(url):
        return None
    try:
        host = urlparse(url).hostname
        for kayit in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(kayit[4][0].split("%")[0])
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                ip = ip.ipv4_mapped
            return str(ip)
    except Exception:
        return None
    return None

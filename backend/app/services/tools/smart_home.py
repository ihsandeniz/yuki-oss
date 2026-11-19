"""Faz δ — Akıllı Ev Entegrasyonu (python-kasa / TP-Link).

Araçlar:
    smart_home_control(device_name, action, ...)  → cihaz kontrolü
    smart_home_discover()                         → ağdaki cihazları listele
"""

import asyncio
import ipaddress
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Keşfedilen cihazlar cache (IP → {"alias": ..., "type": ...})
_device_cache: dict[str, dict[str, Any]] = {}
_cache_ts: float = 0.0
_CACHE_TTL = 120  # saniye


async def _load_kasa():
    """python-kasa import (runtime — kurulamazsa graceful hata)."""
    try:
        import kasa
        return kasa
    except ImportError:
        raise RuntimeError("python-kasa kurulu değil. 'pip install python-kasa' çalıştır.")  # i18n-istisna: LLM'e giden araç sonucu


async def discover_devices(force: bool = False) -> dict[str, dict[str, Any]]:
    """Ağdaki TP-Link Kasa cihazlarını keşfeder (cache'li, TTL=120s).

    KASA_DEVICES dolu ise sadece o IP'leri sorgular.
    Boşsa ağ broadcast ile otomatik keşif yapar.
    """
    import time
    global _device_cache, _cache_ts

    if not force and _device_cache and (time.monotonic() - _cache_ts) < _CACHE_TTL:
        return _device_cache

    kasa = await _load_kasa()

    from app.config import KASA_DEVICES

    found: dict[str, dict[str, Any]] = {}

    if KASA_DEVICES:
        for ip in KASA_DEVICES:
            try:
                dev = await kasa.Discover.discover_single(ip)
                await dev.update()
                found[ip] = {
                    "alias": dev.alias,
                    "type": dev.device_type.value if hasattr(dev.device_type, "value") else str(dev.device_type),
                    "is_on": dev.is_on,
                    "model": dev.model,
                }
            except Exception as e:
                logger.warning("Kasa cihazı bulunamadı %s: %s", ip, e)
    else:
        try:
            devices = await kasa.Discover.discover(timeout=5)
            for ip, dev in devices.items():
                await dev.update()
                found[ip] = {
                    "alias": dev.alias,
                    "type": dev.device_type.value if hasattr(dev.device_type, "value") else str(dev.device_type),
                    "is_on": dev.is_on,
                    "model": dev.model,
                }
        except Exception as e:
            logger.error("Kasa keşif hatası: %s", e)

    _device_cache = found
    _cache_ts = time.monotonic()
    return found


def _is_private_ip(ip_str: str) -> bool:
    """Check if IP is in private/LAN ranges (10/8, 172.16/12, 192.168/16, 127/8)."""
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local
    except ValueError:
        return False


def _find_device_ip(device_name: str, devices: dict[str, dict]) -> str | None:
    """İsimden IP'ye eşleme — tam veya kısmi ad eşleşmesi (büyük/küçük harf yok)."""
    name_lower = (device_name or "").strip().lower()
    if not name_lower:
        return None  # `"" in alias` hep doğru: boş ad ilk cihazı seçerdi
    for ip, info in devices.items():
        alias = (info.get("alias") or "").strip().lower()
        if not alias:
            continue  # adsız cihaz: `alias in name_lower` her ada eşleşirdi
        if name_lower == alias or name_lower in alias or alias in name_lower:
            return ip
    return None


async def smart_home_control(
    device_name: str,
    action: str,
    brightness: int | None = None,
    color_temp: int | None = None,
    hue: int | None = None,
    saturation: int | None = None,
) -> str:
    """TP-Link Kasa akıllı cihazı kontrol eder.

    Args:
        device_name: Cihaz adı (alias) veya IP adresi.
        action: "on" | "off" | "toggle" | "status" | "discover"
        brightness: 0-100 (akıllı ampul için).
        color_temp: Renk sıcaklığı Kelvin (2500-6500, ampul için).
        hue: Ton 0-360 (RGB ampul için).
        saturation: Doygunluk 0-100 (RGB ampul için).
    """
    from app.config import SMART_HOME_ENABLED
    if not SMART_HOME_ENABLED:
        return "Akıllı ev devre dışı. SMART_HOME_ENABLED=true yap ve sunucuyu yeniden başlat."  # i18n-istisna: LLM'e giden araç sonucu

    kasa = await _load_kasa()

    if action == "discover":
        devices = await discover_devices(force=True)
        if not devices:
            return "Ağda Kasa cihazı bulunamadı."  # i18n-istisna: LLM'e giden araç sonucu
        lines = ["Bulunan akıllı ev cihazları:"]  # i18n-istisna: LLM'e giden araç sonucu
        for ip, info in devices.items():
            state = "açık" if info.get("is_on") else "kapalı"  # i18n-istisna: LLM'e giden araç sonucu
            lines.append(f"  • {info['alias']} ({ip}) — {info['type']}, {state}")
        return "\n".join(lines)

    # Cihazı bul
    devices = await discover_devices()
    ip = _find_device_ip(device_name, devices)

    if ip is None:
        # IP adresi doğrudan verilmiş olabilir
        import re
        if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", device_name):
            ip = device_name
        else:
            names = [info["alias"] for info in devices.values()]
            hint = ", ".join(names) if names else "hiçbiri"  # i18n-istisna: LLM'e giden araç sonucu
            return f"'{device_name}' adında cihaz bulunamadı. Mevcut cihazlar: {hint}. 'keşfet' komutuyla yeniden tara."  # i18n-istisna: LLM'e giden araç sonucu

    # SSRF prevention: only allow private/LAN IP addresses
    if not _is_private_ip(ip):
        return f"Güvenlik hatası: {ip} genel IP. Sadece LAN cihazları kontrol edilebilir."  # i18n-istisna: LLM'e giden araç sonucu

    try:
        dev = await kasa.Discover.discover_single(ip)
        await dev.update()
    except Exception as e:
        return f"Cihaza bağlanılamadı ({ip}): {e}"  # i18n-istisna: LLM'e giden araç sonucu

    alias = dev.alias

    if action == "status":
        state = "açık" if dev.is_on else "kapalı"  # i18n-istisna: LLM'e giden araç sonucu
        info = f"{alias} şu anda {state}."  # i18n-istisna: LLM'e giden araç sonucu
        # Ampul ek bilgisi
        if hasattr(dev, "brightness"):
            info += f" Parlaklık: %{dev.brightness}."  # i18n-istisna: LLM'e giden araç sonucu
        if hasattr(dev, "color_temp") and dev.color_temp:
            info += f" Renk sıcaklığı: {dev.color_temp}K."  # i18n-istisna: LLM'e giden araç sonucu
        return info

    try:
        if action == "on":
            await dev.turn_on()
        elif action == "off":
            await dev.turn_off()
        elif action == "toggle":
            if dev.is_on:
                await dev.turn_off()
            else:
                await dev.turn_on()
        else:
            return f"Bilinmeyen eylem: '{action}'. Geçerli: on, off, toggle, status, discover."  # i18n-istisna: LLM'e giden araç sonucu

        # Parlaklık / renk (ampul ise)
        if brightness is not None and hasattr(dev, "set_brightness"):
            await dev.set_brightness(max(0, min(100, brightness)))
        if color_temp is not None and hasattr(dev, "set_color_temp"):
            await dev.set_color_temp(color_temp)
        if hue is not None and saturation is not None and hasattr(dev, "set_hsv"):
            await dev.set_hsv(hue, saturation)

    except Exception as e:
        return f"{alias} kontrolünde hata: {e}"  # i18n-istisna: LLM'e giden araç sonucu

    action_tr = {"on": "açıldı", "off": "kapatıldı", "toggle": "değiştirildi"}.get(action, action)  # i18n-istisna: LLM'e giden araç sonucu
    extras = []
    if brightness is not None:
        extras.append(f"parlaklık %{brightness}")  # i18n-istisna: LLM'e giden araç sonucu
    if color_temp is not None:
        extras.append(f"renk sıcaklığı {color_temp}K")  # i18n-istisna: LLM'e giden araç sonucu
    suffix = f" ({', '.join(extras)})" if extras else ""
    return f"{alias} {action_tr}{suffix}. ✓"


async def smart_home_discover() -> str:
    """Ağdaki tüm Kasa cihazlarını keşfeder ve listeler."""
    return await smart_home_control("", "discover")

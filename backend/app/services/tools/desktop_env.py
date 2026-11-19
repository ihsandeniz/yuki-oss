"""desktop_env.py — Platform / masaüstü ortamı tespiti (system-aware Mod Yöneticisi).

Mod Yöneticisi mantığı platformdan bağımsızdır (mod = uygulama aç + çalışma alanına geç),
ama yöntem masaüstüne göre değişir. Açık kaynak sürümde modlar kabuk komutu ÇALIŞTIRMAZ:

  • Hyprland (Wayland)  → hyprctl + özel alanlar (togglespecialworkspace)   ← tam destek
  • Diğer Linux (GNOME/KDE/sway/…) → wmctrl                                  ← best-effort
  • Windows 10/11       → uygulama aç                                        ← best-effort
  • Bilinmeyen          → sadece uygulama aç (alan geçişi yok)

Bu modül kurulan sistemi ALGILAR ve `detect_env()` ile yetenek haritası döner; UI ve
`modes.py` bu haritaya göre kendini ayarlar. Hyprland dışı yollar bu makinede test EDİLEMEZ
(gerçek hedef sistemde doğrulanmalı) — o yüzden yalnızca güvenli/best-effort davranır.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from functools import lru_cache

def _is_hyprland() -> bool:
    """Hyprland aktif mi? İmza env'i veya hyprctl yanıtı."""
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return True
    if not shutil.which("hyprctl"):
        return False
    try:
        r = subprocess.run(["hyprctl", "version"], capture_output=True,
                           text=True, timeout=2)
        return r.returncode == 0
    except Exception:
        return False


def _detect_linux_desktop() -> str:
    """Linux masaüstü/pencere yöneticisini adlandır: hyprland|gnome|kde|sway|xfce|other."""
    if _is_hyprland():
        return "hyprland"
    xdg = (os.environ.get("XDG_CURRENT_DESKTOP", "") + " " +
           os.environ.get("DESKTOP_SESSION", "")).lower()
    for key in ("sway", "gnome", "kde", "plasma", "xfce", "cinnamon", "mate", "hyprland"):
        if key in xdg:
            return "kde" if key == "plasma" else key
    if os.environ.get("SWAYSOCK"):
        return "sway"
    return "other"


@lru_cache(maxsize=1)
def detect_env() -> dict:
    """Kurulu sistemi algıla → {os, session, desktop, features{}}.

    features: her yeteneğin bu sistemde desteklenip desteklenmediği (UI + modes.py buna bakar):
      apps            uygulama açma (her yerde True)
      workspaces      numaralı çalışma alanına geçiş
      workspace_move  yeni pencereyi sessizce alana taşıma (yalnız Hyprland)
      specials        özel/gizli alan (yalnız Hyprland)
    """
    sysname = platform.system().lower()  # 'linux' | 'windows' | 'darwin'
    if sysname == "windows":
        os_name, desktop, session = "windows", "windows", "windows"
    elif sysname == "darwin":
        os_name, desktop, session = "macos", "macos", "aqua"
    else:
        os_name = "linux"
        desktop = _detect_linux_desktop()
        session = os.environ.get("XDG_SESSION_TYPE") or (
            "wayland" if os.environ.get("WAYLAND_DISPLAY") else
            "x11" if os.environ.get("DISPLAY") else "tty")

    is_hypr = desktop == "hyprland"
    has_wmctrl = os_name == "linux" and shutil.which("wmctrl") is not None

    features = {
        "apps": True,
        # Numaralı alan geçişi: Hyprland veya (Linux + wmctrl) veya Windows (sanal masaüstü)
        "workspaces": is_hypr or has_wmctrl or os_name == "windows",
        # Yeni pencereyi sessizce taşıma: sadece Hyprland'de güvenilir
        "workspace_move": is_hypr,
        "specials": is_hypr,
    }

    return {
        "os": os_name,
        "session": session,
        "desktop": desktop,
        "features": features,
    }


def env_label() -> str:
    """UI başlığı için okunur sistem etiketi: 'Hyprland · linux' gibi."""
    e = detect_env()
    d = {
        "hyprland": "Hyprland", "gnome": "GNOME", "kde": "KDE",
        "sway": "Sway", "xfce": "XFCE", "windows": "Windows",
        "macos": "macOS", "other": "Linux",
    }.get(e["desktop"], e["desktop"])
    return f"{d} · {e['os']}"

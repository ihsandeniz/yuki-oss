"""D-Bus Watcher — Sistem olaylarını dinler ve Yuki'yi bilgilendirir.

Dinlenen sinyaller:
  - org.freedesktop.login1.Manager :: PrepareForSleep
      → uyku öncesi (True) / uyanma (False)
  - org.freedesktop.NetworkManager :: StateChanged
      → ağ bağlantısı kesildi / kuruldu

Özellik bayrağı: DBUS_ENABLED=true (.env)
"""

from __future__ import annotations

import asyncio
import logging
import sys as _sys
from app.mesajlar import M

logger = logging.getLogger(__name__)

_cm = None          # ConnectionManager
_task: asyncio.Task | None = None
_prev_nm_state: int = -1


def set_connection_manager(cm) -> None:
    global _cm
    _cm = cm


# ──────────────────────────────────────────────────────────────────────
# Proaktif mesaj gönderici
# ──────────────────────────────────────────────────────────────────────

async def _push(text: str) -> None:
    """Sistem olayını (uyku/ağ) ekrana + sese ilet, `yuki_dedi`'ye `sistem` olarak yaz.
    Telefona GİTMEZ — makinenin kendi uykusu/ağı telefonu ilgilendirmez (eski davranış korunur)."""
    if not _cm:
        return
    from app.services import scheduler as _sch
    if _sch._cm is None:
        _sch.set_connection_manager(_cm)
    await _sch._push_proactive(text, "sistem", telefona=False)


# ──────────────────────────────────────────────────────────────────────
# D-Bus izleme döngüsü
# ──────────────────────────────────────────────────────────────────────

async def _watch() -> None:
    try:
        from dbus_next.aio import MessageBus
        from dbus_next.message import Message
        from dbus_next import MessageType, BusType
    except ImportError:
        logger.warning("dbus-next yüklü değil — D-Bus izleme devre dışı")
        return

    try:
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    except Exception as e:
        logger.warning("D-Bus (SYSTEM) bağlantısı kurulamadı: %s", e)
        return

    async def _add_match(rule: str) -> None:
        try:
            await bus.call(Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="AddMatch",
                signature="s",
                body=[rule],
            ))
        except Exception as e:
            logger.warning("AddMatch başarısız (%r): %s", rule, e)

    await _add_match(
        "type='signal',"
        "sender='org.freedesktop.login1',"
        "interface='org.freedesktop.login1.Manager',"
        "member='PrepareForSleep'"
    )
    await _add_match(
        "type='signal',"
        "sender='org.freedesktop.NetworkManager',"
        "interface='org.freedesktop.NetworkManager',"
        "member='StateChanged'"
    )

    global _prev_nm_state
    state_holder = [_prev_nm_state]  # mutable closure

    def handle(msg) -> None:
        if msg.message_type != MessageType.SIGNAL:
            return

        iface = msg.interface or ""
        member = msg.member or ""

        if iface == "org.freedesktop.login1.Manager" and member == "PrepareForSleep":
            if len(msg.body) > 0:
                going_to_sleep: bool = msg.body[0]
                if not going_to_sleep:
                    asyncio.create_task(_push(M("bildirim.uyanis")))

        elif iface == "org.freedesktop.NetworkManager" and member == "StateChanged":
            if len(msg.body) > 0:
                nm_state: int = msg.body[0]
                prev = state_holder[0]
                if nm_state in (20, 30) and prev >= 60:
                    asyncio.create_task(_push(M("bildirim.internet-kesildi")))
                elif nm_state >= 70 and (prev < 60 or prev == -1):
                    asyncio.create_task(_push(M("bildirim.internet-geldi")))
                state_holder[0] = nm_state

    bus.add_message_handler(handle)
    logger.info("D-Bus izleme başladı (login1 PrepareForSleep + NetworkManager StateChanged)")

    try:
        await bus.wait_for_disconnect()
    except asyncio.CancelledError:
        bus.disconnect()
        raise


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def desteklenen_platform() -> bool:
    """D-Bus yalnız Linux/BSD'de vardır — Windows ve macOS'ta yoktur.

    🔴 2026-08-02 saha raporu (Windows 10, kullanıcı):
        WARNING dbus_watcher — D-Bus (SYSTEM) bağlantısı kurulamadı:
        module 'socket' has no attribute 'AF_UNIX'

    `AF_UNIX` Windows'ta yok; yani bu bağlantı **denenmemeliydi bile**. Her
    açılışta kullanıcının hata günlüğüne, düzeltemeyeceği ve düzeltmesi de
    gerekmeyen bir uyarı düşüyordu — gerçek sorunları gölgeleyen gürültü.
    """
    return _sys.platform.startswith(("linux", "freebsd", "openbsd", "netbsd"))


async def start(cm=None) -> None:
    """D-Bus izleme task'ını başlat (yalnız destekleyen platformlarda)."""
    global _task, _cm
    if not desteklenen_platform():
        logger.info(
            "D-Bus izleme atlandı — %s bu teknolojiyi kullanmaz (uyku/ağ olayları "
            "yalnız Linux'ta izlenir). Bu bir hata değildir.", _sys.platform
        )
        return
    if cm:
        _cm = cm
    _task = asyncio.create_task(_watch(), name="dbus-watcher")


async def stop() -> None:
    """D-Bus izleme task'ını durdur."""
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None

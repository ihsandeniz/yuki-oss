"""Device Manager — AliceAI'ya bağlı remote agent'ları yönet."""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from fastapi import WebSocket

from app.mesajlar import M

log = logging.getLogger(__name__)


@dataclass
class ConnectedDevice:
    device_id:    str
    hostname:     str
    os:           str
    os_version:   str
    arch:         str
    ip:           str
    ws:           WebSocket
    connected_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_seen:    str = field(default_factory=lambda: datetime.utcnow().isoformat())
    cpu_percent:  float = 0.0
    cpu_count:    int   = 0
    ram_total:    int   = 0
    ram_used:     int   = 0
    ram_percent:  float = 0.0
    disk_total:   int   = 0
    disk_used:    int   = 0
    disk_percent: float = 0.0
    uptime:       int   = 0
    _pending: dict = field(default_factory=dict)

    async def send_command(
        self, action: str, args: dict | None = None, timeout: float = 30.0
    ) -> dict:
        cmd_id = str(uuid.uuid4())
        loop   = asyncio.get_event_loop()
        fut    = loop.create_future()
        self._pending[cmd_id] = fut
        try:
            import json
            await self.ws.send_text(json.dumps({
                "type":   "command",
                "cmd_id": cmd_id,
                "action": action,
                "args":   args or {},
            }))
            return await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(cmd_id, None)
            return {"error": M("cihaz.zaman-asimi")}
        except Exception as e:
            self._pending.pop(cmd_id, None)
            return {"error": str(e)}

    def resolve(self, cmd_id: str, payload: dict) -> None:
        fut = self._pending.pop(cmd_id, None)
        if fut and not fut.done():
            fut.set_result(payload)


_devices: dict[str, ConnectedDevice] = {}


def get_all() -> list[ConnectedDevice]:
    return list(_devices.values())


def get(device_id: str) -> Optional[ConnectedDevice]:
    return _devices.get(device_id)


def register(device_id: str, info: dict, ws: WebSocket) -> ConnectedDevice:
    dev = ConnectedDevice(
        device_id=device_id,
        hostname=info.get("hostname", "unknown"),
        os=info.get("os", "unknown"),
        os_version=info.get("os_version", ""),
        arch=info.get("arch", ""),
        ip=info.get("ip", ""),
        ws=ws,
        cpu_percent=info.get("cpu_percent", 0.0),
        cpu_count=info.get("cpu_count", 0),
        ram_total=info.get("ram_total", 0),
        ram_used=info.get("ram_used", 0),
        ram_percent=info.get("ram_percent", 0.0),
        disk_total=info.get("disk_total", 0),
        disk_used=info.get("disk_used", 0),
        disk_percent=info.get("disk_percent", 0.0),
        uptime=info.get("uptime", 0),
    )
    _devices[device_id] = dev
    log.info("Cihaz bağlandı: %s (%s @ %s)", device_id[:8], dev.hostname, dev.ip)
    return dev


def unregister(device_id: str) -> None:
    d = _devices.pop(device_id, None)
    if d:
        log.info("Cihaz ayrıldı: %s (%s)", device_id[:8], d.hostname)


def update(device_id: str, info: dict) -> None:
    d = _devices.get(device_id)
    if not d:
        return
    d.last_seen    = datetime.utcnow().isoformat()
    d.cpu_percent  = info.get("cpu_percent",  d.cpu_percent)
    d.ram_percent  = info.get("ram_percent",  d.ram_percent)
    d.ram_used     = info.get("ram_used",     d.ram_used)
    d.disk_percent = info.get("disk_percent", d.disk_percent)
    d.uptime       = info.get("uptime",       d.uptime)

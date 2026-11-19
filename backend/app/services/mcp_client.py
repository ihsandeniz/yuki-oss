"""MCP client köprüsü (Faz 23) — dış MCP sunucularının araçlarını Yuki'ye açar.

Her sunucu KENDİ asyncio task'ında yaşar: stdio context manager tek task içinde
açılıp kapanır (anyio "cancel scope in a different task" hatasını önler). Araç
çağrıları future'larla o task'a marshal edilir.

Boot-güvenli: bir sunucu bağlanamazsa ATLANIR, backend yine açılır.
Config: backend/mcp_servers.json (varsayılan TÜM sunucular disabled).
Keşfedilen araçlar dispatcher.TOOLS'a `mcp__<sunucu>__<araç>` adıyla eklenir.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# backend/app/services/mcp_client.py → parents[2] = backend/
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "mcp_servers.json"


def _base_env(extra_keys: list[str]) -> dict:
    """Sunucu alt-sürecine geçilecek env: güvenli taban + istenen kimlik anahtarları."""
    try:
        from mcp.client.stdio import get_default_environment
        env = dict(get_default_environment())
    except Exception:  # noqa: BLE001
        env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "USER") if k in os.environ}
    for k in extra_keys:
        if k in os.environ:
            env[k] = os.environ[k]
    return env


def _schema_from_tool(server: str, t) -> dict:
    """Bir MCP Tool'unu AliceAi araç şemasına (`mcp__server__tool`) çevirir."""
    params = getattr(t, "inputSchema", None) or {"type": "object", "properties": {}}
    desc = (getattr(t, "description", None) or f"{server} MCP aracı")[:1024]
    return {
        "type": "function",
        "function": {
            "name": f"mcp__{server}__{t.name}",
            "description": desc,
            "parameters": params,
        },
    }


def _extract_text(res) -> str:
    """MCP call_tool sonucundan metni ayıklar (content[].text)."""
    parts = []
    for c in (getattr(res, "content", None) or []):
        txt = getattr(c, "text", None)
        if txt is not None:
            parts.append(txt)
    out = "\n".join(parts).strip()
    if getattr(res, "isError", False):
        return f"Hata (MCP): {out or 'bilinmeyen hata'}"
    return out or "(boş MCP yanıtı)"


class _ServerConn:
    """Tek bir MCP sunucusu — kendi task'ında yaşayan bağlantı aktörü."""

    def __init__(self, spec: dict):
        self.spec = spec
        self.name = spec["name"]
        self.tools: list[dict] = []
        self.error: str | None = None
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._calls: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=self.spec.get("timeout", 20))
        except asyncio.TimeoutError:
            self.error = self.error or "bağlantı zaman aşımı"

    async def _run(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        try:
            params = StdioServerParameters(
                command=self.spec["command"],
                args=self.spec.get("args", []),
                env=_base_env(self.spec.get("env_keys", [])),
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), timeout=15)
                    resp = await session.list_tools()
                    self.tools = [_schema_from_tool(self.name, t) for t in resp.tools]
                    self._ready.set()
                    # Çağrıları servis et — _stop gelene kadar
                    while not self._stop.is_set():
                        try:
                            tool, args, fut = await asyncio.wait_for(self._calls.get(), timeout=0.5)
                        except asyncio.TimeoutError:
                            continue
                        try:
                            r = await asyncio.wait_for(
                                session.call_tool(tool, args or {}),
                                timeout=self.spec.get("call_timeout", 60),
                            )
                            if not fut.done():
                                fut.set_result(_extract_text(r))
                        except Exception as e:  # noqa: BLE001
                            if not fut.done():
                                fut.set_result(f"Hata: MCP '{self.name}.{tool}' — {e}")
        except Exception as e:  # noqa: BLE001
            self.error = str(e)
        finally:
            self._ready.set()  # start()'ı asla asma

    async def call(self, tool: str, args: dict) -> str:
        if self.error:
            return f"Hata: MCP '{self.name}' bağlı değil ({self.error})"
        fut = asyncio.get_event_loop().create_future()
        await self._calls.put((tool, args, fut))
        try:
            return await asyncio.wait_for(fut, timeout=self.spec.get("call_timeout", 60) + 5)
        except asyncio.TimeoutError:
            return f"Hata: MCP '{self.name}.{tool}' çağrısı zaman aşımına uğradı"

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except Exception:  # noqa: BLE001
                self._task.cancel()


class MCPManager:
    def __init__(self):
        self.conns: dict[str, _ServerConn] = {}
        self.index: dict[str, str] = {}  # mcp__server__tool -> server

    async def startup(self, specs: list[dict]) -> None:
        for spec in specs:
            if not spec.get("enabled"):
                continue
            name, cmd = spec.get("name"), spec.get("command")
            if not name or not cmd:
                logger.warning("MCP spec geçersiz (name/command eksik), atlanıyor: %s", spec)
                continue
            conn = _ServerConn(spec)
            await conn.start()
            if conn.error:
                logger.warning("MCP '%s' atlandı: %s", name, conn.error)
                await conn.stop()
                continue
            self.conns[name] = conn
            from app.services.tools.dispatcher import register_mcp_tools
            register_mcp_tools(conn.tools)
            for sc in conn.tools:
                self.index[sc["function"]["name"]] = name
            logger.info("MCP '%s' bağlandı: %d araç", name, len(conn.tools))

    async def call(self, full_name: str, args: dict) -> str:
        server = self.index.get(full_name)
        if not server or server not in self.conns:
            return f"Hata: bilinmeyen/bağlı-olmayan MCP aracı '{full_name}'"
        tool = full_name.split("__", 2)[2] if full_name.count("__") >= 2 else full_name
        return await self.conns[server].call(tool, args)

    async def shutdown(self) -> None:
        for c in list(self.conns.values()):
            try:
                await c.stop()
            except Exception:  # noqa: BLE001
                pass
        self.conns.clear()
        self.index.clear()


_manager: MCPManager | None = None


def get_manager() -> MCPManager:
    global _manager
    if _manager is None:
        _manager = MCPManager()
    return _manager


def load_config() -> list[dict]:
    try:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        return data.get("servers", [])
    except FileNotFoundError:
        return []
    except Exception as e:  # noqa: BLE001
        logger.warning("mcp_servers.json okunamadı: %s", e)
        return []


async def startup_from_config() -> None:
    specs = load_config()
    if not any(s.get("enabled") for s in specs):
        logger.info("MCP: etkin sunucu yok (mcp_servers.json)")
        return
    await get_manager().startup(specs)


async def shutdown() -> None:
    if _manager is not None:
        await _manager.shutdown()


# ── n8n webhook köprüsü (MCP değil — basit webhook tetikleyici) ──────────────
async def trigger_n8n(workflow: str, payload: dict | None = None) -> str:
    """n8n webhook'unu tetikler. Base URL: .env → N8N_WEBHOOK_BASE."""
    base = os.getenv("N8N_WEBHOOK_BASE", "").rstrip("/")
    if not base:
        return "Hata: N8N_WEBHOOK_BASE .env'de tanımlı değil."
    ad = (workflow or "").lstrip("/")
    # Ad URL yoluna girer: `../`, `?` ya da `#` webhook kökünden başka uca götürür.
    if not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", ad):
        return f"Hata: Geçersiz workflow adı: {workflow!r}"
    url = f"{base}/{ad}"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, json=payload or {})
        if r.status_code < 300:
            return f"n8n '{workflow}' tetiklendi ✓ (HTTP {r.status_code}): {r.text[:300]}"
        return f"Hata: n8n '{workflow}' → HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:  # noqa: BLE001
        return f"Hata: n8n webhook başarısız — {e}"

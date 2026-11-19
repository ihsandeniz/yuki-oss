"""Sistem izleme zaman serisi deposu (aiosqlite, WAL).

- monitor_samples : 60s'lik metrik örnekleri (7 gün retention)
- process_daily   : gün + program adı bazında toplam CPU-saniye + zirve RAM (1 yıl)
"""
from __future__ import annotations

import datetime as _dt
import os
import logging
import time as _time
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

# backend/app/services/monitoring/history.py → parents[3] = backend/
# 🐞 2026-07-31: `backend/data/monitor.db` sabitti → satılan pakette salt okunur
# (routines.py / config_manager ile aynı hata sınıfı). YUKI_DATA_DIR varsa oraya.
_DB_PATH = (
    Path(os.getenv("YUKI_DATA_DIR") or Path(__file__).resolve().parents[3])
    / "data" / "monitor.db"
)
_RETENTION_DAYS = 7
_RANGE_SECONDS = {"1h": 3600, "24h": 86400, "7d": 7 * 86400}


async def init_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS monitor_samples (
              ts INTEGER PRIMARY KEY,
              cpu REAL, mem REAL, gpu REAL, gpu_vram REAL,
              net_up REAL, net_down REAL, disk_read REAL, disk_write REAL,
              cpu_temp REAL, gpu_temp REAL, power REAL, health INTEGER
            )""")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS process_daily (
              day TEXT, name TEXT,
              cpu_sec REAL, mem_peak_mb REAL, net_mb REAL, samples INTEGER,
              PRIMARY KEY (day, name)
            )""")
        await db.commit()
    logger.info("monitor.db hazır: %s", _DB_PATH)


async def write_sample(snap: dict) -> None:
    ts = int(snap.get("ts", _time.time()) // 60 * 60)  # 60s bucket
    cpu = snap.get("cpu") or {}
    mem = snap.get("mem") or {}
    gnv = snap.get("gpu_nvidia") or {}
    net = snap.get("net") or {}
    disks = snap.get("disks") or []
    ifaces = net.get("ifaces") or []

    disk_read = sum((d.get("read_mbps") or 0) for d in disks)
    disk_write = sum((d.get("write_mbps") or 0) for d in disks)
    net_up = sum((i.get("up_mbps") or 0) for i in ifaces)
    net_down = sum((i.get("down_mbps") or 0) for i in ifaces)

    row = (
        ts, cpu.get("total"), mem.get("percent"),
        gnv.get("util"), gnv.get("vram_used_mb"),
        round(net_up, 3), round(net_down, 3),
        round(disk_read, 3), round(disk_write, 3),
        cpu.get("temp_c"), gnv.get("temp_c"),
        (snap.get("power") or {}).get("package_w"),
        snap.get("health_score"),
    )
    try:
        async with aiosqlite.connect(_DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO monitor_samples "
                "(ts,cpu,mem,gpu,gpu_vram,net_up,net_down,disk_read,disk_write,"
                "cpu_temp,gpu_temp,power,health) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                row)
            await db.execute("DELETE FROM monitor_samples WHERE ts < ?",
                             (ts - _RETENTION_DAYS * 86400,))
            await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("write_sample hatası: %s", e)


async def upsert_process_daily(procs: list[dict], interval_s: float,
                               day: str | None = None) -> None:
    if not procs:
        return
    day = day or _dt.date.today().isoformat()
    agg: dict[str, list[float]] = {}
    for p in procs:
        name = p.get("name") or "?"
        cpu_sec = (p.get("cpu") or 0) / 100.0 * interval_s
        mem_mb = p.get("mem_mb") or 0
        a = agg.setdefault(name, [0.0, 0.0])
        a[0] += cpu_sec
        a[1] = max(a[1], mem_mb)
    try:
        async with aiosqlite.connect(_DB_PATH) as db:
            for name, (cpu_sec, mem_peak) in agg.items():
                await db.execute("""
                    INSERT INTO process_daily (day,name,cpu_sec,mem_peak_mb,net_mb,samples)
                    VALUES (?,?,?,?,0,1)
                    ON CONFLICT(day,name) DO UPDATE SET
                      cpu_sec = cpu_sec + excluded.cpu_sec,
                      mem_peak_mb = MAX(mem_peak_mb, excluded.mem_peak_mb),
                      samples = samples + 1
                """, (day, name, cpu_sec, mem_peak))
            await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("upsert_process_daily hatası: %s", e)


async def query_range(rng: str = "1h") -> list[dict]:
    secs = _RANGE_SECONDS.get(rng, 3600)
    since = int(_time.time()) - secs
    try:
        async with aiosqlite.connect(_DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM monitor_samples WHERE ts >= ? ORDER BY ts ASC", (since,))
            return [dict(r) for r in await cur.fetchall()]
    except Exception as e:  # noqa: BLE001
        logger.warning("query_range hatası: %s", e)
        return []


async def report_today(day: str | None = None) -> dict:
    """Belirli bir günün raporu (top CPU/RAM + zirveler). day=None → bugün."""
    try:
        day_date = _dt.date.fromisoformat(day) if day else _dt.date.today()
    except ValueError:
        day_date = _dt.date.today()
    day = day_date.isoformat()
    day_start = int(_dt.datetime.combine(day_date, _dt.time.min).timestamp())
    day_end = day_start + 86400
    out: dict = {"day": day, "top_cpu": [], "top_mem": [], "peaks": {}, "samples": 0}
    try:
        async with aiosqlite.connect(_DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT name, ROUND(cpu_sec,1) cpu_sec, ROUND(mem_peak_mb,1) mem_peak_mb "
                "FROM process_daily WHERE day=? ORDER BY cpu_sec DESC LIMIT 5", (day,))
            out["top_cpu"] = [dict(r) for r in await cur.fetchall()]
            cur = await db.execute(
                "SELECT name, ROUND(cpu_sec,1) cpu_sec, ROUND(mem_peak_mb,1) mem_peak_mb "
                "FROM process_daily WHERE day=? ORDER BY mem_peak_mb DESC LIMIT 5", (day,))
            out["top_mem"] = [dict(r) for r in await cur.fetchall()]
            cur = await db.execute(
                "SELECT MAX(cpu) c, MAX(mem) m, MAX(gpu) g, MAX(net_down) nd, COUNT(*) n "
                "FROM monitor_samples WHERE ts >= ? AND ts < ?", (day_start, day_end))
            r = await cur.fetchone()
            if r:
                out["peaks"] = {"cpu": r["c"], "mem": r["m"],
                                "gpu": r["g"], "net_down": r["nd"]}
                out["samples"] = r["n"]
    except Exception as e:  # noqa: BLE001
        logger.warning("report_today hatası: %s", e)
    return out


async def report_available_days(limit: int = 30) -> list[str]:
    """Verisi olan günlerin listesi (en yeni önce) — geçmiş gün gezinmesi için."""
    try:
        async with aiosqlite.connect(_DB_PATH) as db:
            cur = await db.execute(
                "SELECT DISTINCT day FROM process_daily ORDER BY day DESC LIMIT ?", (limit,))
            return [r[0] for r in await cur.fetchall()]
    except Exception as e:  # noqa: BLE001
        logger.warning("report_available_days hatası: %s", e)
        return []

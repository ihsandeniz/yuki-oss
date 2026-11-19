"""Map veri kaynakları için ortak dayanıklılık katmanı.

Sorun: Map sekmesi araçları (deprem, yangın, uçuş...) dış API'lere tek atış
yapıyordu — cache yok, retry yok, son-iyi-veri yok. Yavaş/limitli upstream
(FIRMS ~6s CSV, OpenSky anonim 429, NASA DEMO_KEY 30/saat) → "bazen sonuç
veriyor bazen vermiyor".

Çözüm: her kaynak için TTL cache + tek retry + stale-on-error (upstream
düşerse son başarılı veri `stale: true` ile döner) + stampede kilidi +
sağlık kaydı (`/api/map/health`).

Kullanım:
    async def _fetch_x() -> dict:   # HATA durumunda exception FIRLATMALI
        ...
        return {"items": [...], "count": n}

    return await resilient("x", ttl=600, fetcher=_fetch_x)

Not: boş sonuç != hata. Fetcher gerçek 0 kayıtta normal dict dönmeli;
yalnız upstream ulaşılamaz/parse edilemez olduğunda raise etmeli — aksi
halde boş sonuç cache'lenir (eski military bug'ı).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

_cache: dict[str, dict[str, Any]] = {}    # key → {"data": dict, "ts": float}
_locks: dict[str, asyncio.Lock] = {}
_health: dict[str, dict[str, Any]] = {}   # key → son fetch durumu


def _hit(entry: dict, *, stale: bool = False, err: str | None = None) -> dict:
    out = {**entry["data"], "cached": True, "age_s": int(time.time() - entry["ts"])}
    if stale:
        out["stale"] = True
        if err:
            out["upstream_error"] = err[:200]
    return out


async def resilient(
    key: str,
    ttl: float,
    fetcher: Callable[[], Awaitable[dict]],
    retries: int = 1,
    retry_delay: float = 1.5,
) -> dict:
    now = time.time()
    entry = _cache.get(key)
    if entry and now - entry["ts"] < ttl:
        return _hit(entry)

    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        # Kilidi beklerken başka istek cache'i doldurmuş olabilir
        entry = _cache.get(key)
        if entry and time.time() - entry["ts"] < ttl:
            return _hit(entry)

        last_err: Exception | None = None
        for attempt in range(retries + 1):
            t0 = time.time()
            try:
                data = await fetcher()
                _cache[key] = {"data": data, "ts": time.time()}
                _health[key] = {
                    "ok": True, "error": None, "ts": time.time(),
                    "latency_ms": int((time.time() - t0) * 1000),
                    "fail_count": 0,
                }
                return {**data, "cached": False, "age_s": 0}
            except Exception as e:  # noqa: BLE001 — her upstream hatası aynı yolda
                last_err = e
                if attempt < retries:
                    await asyncio.sleep(retry_delay)

        prev = _health.get(key, {})
        _health[key] = {
            "ok": False, "error": str(last_err)[:200], "ts": time.time(),
            "latency_ms": None,
            "fail_count": prev.get("fail_count", 0) + 1,
        }
        if entry:  # TTL geçmiş ama elde son-iyi-veri var → boş ekran yerine stale
            return _hit(entry, stale=True, err=str(last_err))
        return {"error": str(last_err)[:200]}


def health_snapshot() -> dict:
    """Kaynak bazında son durum — /api/map/health için."""
    now = time.time()
    out: dict[str, dict] = {}
    for key, h in _health.items():
        entry = _cache.get(key)
        out[key] = {
            **h,
            "data_age_s": int(now - entry["ts"]) if entry else None,
            "has_data": entry is not None,
        }
    return out

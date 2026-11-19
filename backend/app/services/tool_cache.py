"""TTL Cache decorator — Faz A2: Sık çağrılan tool sonuçlarını cache'le."""

from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable


def ttl_cache(seconds: float):
    """Basit TTL cache decorator. Sonuçları `seconds` saniye boyunca cache'ler.

    - Key: fonksiyon argümanlarının tuple hali
    - Thread-safe değil ama asyncio single-thread loop'ta sorunsuz
    - Max 64 entry, en eski expire olunca temizlenir
    """
    def decorator(func: Callable) -> Callable:
        _cache: dict[tuple, tuple[float, Any]] = {}
        MAX_ENTRIES = 64

        @wraps(func)
        def wrapper(*args, **kwargs):
            key = args + tuple(sorted(kwargs.items()))
            now = time.monotonic()

            if key in _cache:
                ts, val = _cache[key]
                if now - ts < seconds:
                    return val

            result = func(*args, **kwargs)

            # Expire olan entry'leri temizle
            if len(_cache) >= MAX_ENTRIES:
                expired = [k for k, (ts, _) in _cache.items() if now - ts >= seconds]
                for k in expired:
                    del _cache[k]

            _cache[key] = (now, result)
            return result

        wrapper.cache_clear = lambda: _cache.clear()
        return wrapper

    return decorator

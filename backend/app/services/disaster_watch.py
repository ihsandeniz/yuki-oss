"""Proaktif afet izleyicisi (Map FAZ 4, 2026-07-06).

AFAD'ı periyodik yoklar; eşik üstü YENİ Türkiye depremi görünce:
  1. intel event log'una düşer (INTEL sekmesi feed'i),
  2. masaüstü bildirimi gönderir (notify-send),
  3. WS broadcast yayınlar ({"type": "disaster_alert", ...}) — frontend
     ileride dinleyebilir (şimdilik log+bildirim yeterli).

Env:
  DISASTER_WATCH_ENABLED  (default: true)  — kapatmak için false
  DISASTER_WATCH_MIN_MAG  (default: 4.5)   — bildirim eşiği
  DISASTER_WATCH_INTERVAL (default: 180)   — saniye

Not: AFAD apiv2 302 ile servisnet.afad.gov.tr'ye yönlenir — follow_redirects
şart (2026-07-06 keşfi, map earthquakes endpoint'iyle aynı kaynak).
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from collections import deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_seen: deque[str] = deque(maxlen=500)


def _enabled() -> bool:
    return os.getenv("DISASTER_WATCH_ENABLED", "true").lower() not in ("false", "0", "no")


def _min_mag() -> float:
    try:
        return float(os.getenv("DISASTER_WATCH_MIN_MAG", "4.5"))
    except ValueError:
        return 4.5


def _notify_desktop(title: str, body: str) -> None:
    try:
        subprocess.run(["notify-send", "-u", "critical", "-a", "Yuki", title, body],
                       timeout=5, check=False)
    except Exception:  # notify-send yoksa/başarısızsa izleyici ölmesin
        pass


async def check_once(min_mag: float | None = None, notify: bool = True) -> list[dict]:
    """Tek yoklama — eşik üstü YENİ olayları döner (test edilebilir çekirdek)."""
    import httpx

    threshold = _min_mag() if min_mag is None else min_mag
    end_d = datetime.utcnow()
    start_d = end_d - timedelta(hours=1)

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        r = await client.get(
            "https://deprem.afad.gov.tr/apiv2/event/filter",
            params={"start": start_d.strftime("%Y-%m-%d %H:%M:%S"),
                    "end":   end_d.strftime("%Y-%m-%d %H:%M:%S"),
                    "minmag": threshold, "limit": 50, "orderby": "timedesc"},
            headers={"User-Agent": "Mozilla/5.0 (compatible; AliceAI/1.0)",
                     "Accept": "application/json"},
        )
        r.raise_for_status()
        rows = r.json()

    fresh: list[dict] = []
    for e in rows if isinstance(rows, list) else []:
        try:
            eid = str(e.get("eventID") or f"{e.get('date')}|{e.get('location')}")
            mag = float(e.get("magnitude") or 0)
            if mag < threshold or eid in _seen:
                continue
            _seen.append(eid)
            ev = {"id": eid, "mag": mag, "place": e.get("location", "Türkiye"),  # i18n-istisna: veri — Kandilli kaynağının yer adı yedeği, özel ad
                  "depth": e.get("depth"), "date": e.get("date")}
            fresh.append(ev)

            from app.mesajlar import M
            msg = M("bildirim.deprem-metin", buyukluk=mag, yer=ev["place"], derinlik=ev["depth"])
            try:
                from app.api.intel import log_event
                log_event("AFET", msg)
            except Exception:
                pass
            if notify:
                _notify_desktop(M("bildirim.deprem-baslik"), msg)
                try:
                    from app.api.websocket import _manager as _ws_mgr
                    await _ws_mgr.broadcast({"type": "disaster_alert",
                                             "kind": "earthquake", **ev})
                except Exception:
                    pass
        except (KeyError, ValueError, TypeError):
            continue
    return fresh


async def watcher() -> None:
    """Süreğen izleme döngüsü — main.py lifespan'da create_task ile başlar."""
    if not _enabled():
        logger.info("disaster_watch devre dışı (DISASTER_WATCH_ENABLED=false)")
        return
    interval = int(os.getenv("DISASTER_WATCH_INTERVAL", "180"))
    logger.info("disaster_watch aktif — eşik M%.1f, %ss aralık", _min_mag(), interval)
    # İlk turda mevcut olayları 'görülmüş' say — açılışta eski deprem spam'i olmasın
    try:
        await check_once(notify=False)
    except Exception:
        pass
    while True:
        await asyncio.sleep(interval)
        try:
            fresh = await check_once()
            if fresh:
                logger.info("disaster_watch: %d yeni olay bildirildi", len(fresh))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("disaster_watch yoklama hatası: %s", str(e)[:120])

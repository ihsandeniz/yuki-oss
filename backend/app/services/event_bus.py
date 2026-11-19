"""Async pub-sub event bus — Yuki iç olaylarini dagitir."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

# 🔴 `language_changed` 2026-10-04'e kadar bu listede YOKTU → `/api/language` ve sesli
# "Japoncaya geç" olayı yayınlıyordu ama hiçbir WS istemcisine ulaşmıyordu (ölçüldü,
# 8035 canlı turu): ekran dil değişimini ancak yeniden yüklenince görüyordu.
_ALL_TOPICS = ("state", "emotion", "live2d", "behavior", "state_info", "image_msg", "face_recognized", "tool_approval", "companion_active", "companion_done", "companion_result", "team_start", "team_end", "language_changed", "gorev")


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)

    # ------------------------------------------------------------------ #
    # Subscribe / Unsubscribe
    # ------------------------------------------------------------------ #

    def subscribe(self, topic: str) -> asyncio.Queue:
        """Tek bir topic'e abone ol. Kuyruk döner."""
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=64)
        self._subs[topic].append(q)
        return q

    def unsubscribe(self, topic: str, q: asyncio.Queue) -> None:
        try:
            self._subs[topic].remove(q)
        except ValueError:
            pass

    def subscribe_all(self) -> asyncio.Queue:
        """Tüm topic'lere tek kuyrukla abone ol (WebSocket için)."""
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=128)
        for topic in _ALL_TOPICS:
            self._subs[topic].append(q)
        return q

    def unsubscribe_all(self, q: asyncio.Queue) -> None:
        for topic in _ALL_TOPICS:
            try:
                self._subs[topic].remove(q)
            except ValueError:
                pass

    # ------------------------------------------------------------------ #
    # Publish
    # ------------------------------------------------------------------ #

    def abone_var(self, topic: str) -> bool:
        """Bu olayı DİNLEYEN biri var mı?

        🔴 Neden gerekli: onay kapısı (`tool_approval`) dinleyen istemci yokken
        cevaplanamaz — 30 sn bekleyip "reddedildi" döner. Arka planda koşan bir
        rutin için bu, kapı değil sessiz bir kilittir. Çağıran taraf kapıyı
        uygulamadan önce cevaplanabilir olduğunu ölçebilsin.
        """
        return bool(self._subs.get(topic))

    async def publish(self, topic: str, data: dict[str, Any]) -> None:
        """Olayı tüm abonelere ilet. Yavaş abone → event drop."""
        event = {"type": topic, **data}
        for q in list(self._subs.get(topic, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # yavaş tüketici — düşür


# Singleton
bus = EventBus()

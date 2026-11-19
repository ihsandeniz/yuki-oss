"""Yuki Behavior Layer — durum bazlı idle mikro-animasyonlar."""

from __future__ import annotations

import asyncio
import random

from app.services.event_bus import bus
from app.services.state_machine import YukiState, get_state_machine

# ------------------------------------------------------------------ #
# Davranış havuzu
# Ağırlık = listede kaç kez geçtiği
# ------------------------------------------------------------------ #

_IDLE_POOL = [
    # Göz kırpma — en sık
    {"action": "eye_blink", "duration": 0.12},
    {"action": "eye_blink", "duration": 0.12},
    {"action": "eye_blink", "duration": 0.12},
    {"action": "eye_blink", "duration": 0.12},
    # Çift göz kırpma
    {"action": "eye_blink_double", "duration": 0.10},
    # Kafa eğme
    {"action": "head_tilt", "direction": "left",  "angle": 5.0},
    {"action": "head_tilt", "direction": "right", "angle": 3.0},
    # Bakış kaydırma
    {"action": "look_away", "direction": "up-right"},
    {"action": "look_away", "direction": "up-left"},
    {"action": "look_away", "direction": "side"},
    # Nefes
    {"action": "breath"},
    {"action": "breath"},
]

_LISTENING_POOL = [
    {"action": "head_nod", "intensity": 0.3},
    {"action": "eye_blink", "duration": 0.12},
    {"action": "look_at_user"},
]

_THINKING_POOL = [
    {"action": "look_away", "direction": "up"},
    {"action": "look_away", "direction": "up-right"},
    {"action": "eye_blink", "duration": 0.18},
    {"action": "head_tilt", "direction": "left", "angle": 4.0},
]


class BehaviorLayer:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def _loop(self) -> None:
        while self._running:
            sm = get_state_machine()
            state = sm.state

            if state == YukiState.IDLE:
                behavior = random.choice(_IDLE_POOL)
                wait = random.uniform(2.5, 6.0)
            elif state == YukiState.LISTENING:
                behavior = random.choice(_LISTENING_POOL)
                wait = random.uniform(3.0, 5.0)
            elif state == YukiState.THINKING:
                behavior = random.choice(_THINKING_POOL)
                wait = random.uniform(1.5, 3.0)
            else:
                # TALKING — lip-sync yönetir, behavior layer sadece bekler
                await asyncio.sleep(0.5)
                continue

            await bus.publish("behavior", behavior)
            await asyncio.sleep(wait)


# Singleton
_layer: BehaviorLayer | None = None


def get_behavior_layer() -> BehaviorLayer:
    global _layer
    if _layer is None:
        _layer = BehaviorLayer()
    return _layer

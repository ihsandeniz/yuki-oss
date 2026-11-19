"""Yuki State Machine — IDLE / LISTENING / THINKING / TALKING."""

from __future__ import annotations

import asyncio
from enum import Enum

from app.services.event_bus import bus


class YukiState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    TALKING = "talking"


# Geçerli geçişler
_TRANSITIONS: dict[YukiState, set[YukiState]] = {
    YukiState.IDLE:      {YukiState.LISTENING},
    YukiState.LISTENING: {YukiState.THINKING, YukiState.IDLE},
    YukiState.THINKING:  {YukiState.TALKING, YukiState.IDLE},
    YukiState.TALKING:   {YukiState.IDLE},
}


class StateMachine:
    def __init__(self) -> None:
        self._state = YukiState.IDLE
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @property
    def state(self) -> YukiState:
        return self._state

    async def transition(self, new_state: YukiState) -> bool:
        """Geçerli bir geçiş yap. Başarısızsa False döner."""
        async with self._lock:
            if new_state not in _TRANSITIONS.get(self._state, set()):
                return False
            return await self._apply(new_state)

    async def force(self, new_state: YukiState) -> None:
        """Zorunlu geçiş — kurtarma/reset için (doğrulama yok)."""
        async with self._lock:
            await self._apply(new_state)

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    async def _apply(self, new_state: YukiState) -> bool:
        old = self._state
        self._state = new_state
        await bus.publish("state", {"from": old.value, "to": new_state.value})
        return True


# Singleton
_sm: StateMachine | None = None


def get_state_machine() -> StateMachine:
    global _sm
    if _sm is None:
        _sm = StateMachine()
    return _sm

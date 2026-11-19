"""Screen Context — Ambient Watcher'ın yakaladığı ekran bilgisini global olarak saklar.

Faz K-3a: AmbientWatcher → update_screen_context() → LLMRunner bağlamına enjekte edilir.

Kullanım:
    from app.services.screen_context import get_screen_context, update_screen_context

    # Ambient watcher tarafından güncellenir:
    update_screen_context("code: main.py", "Kullanıcı Python dosyası düzenliyor.")

    # LLMRunner tarafından okunur:
    ctx = get_screen_context()
    if ctx.is_fresh():
        prompt += ctx.to_prompt_block()
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class ScreenContext:
    active_window: str = "bilinmiyor"
    description: str = ""
    updated_at: float = field(default_factory=float)

    def is_fresh(self, max_age: float = 120.0) -> bool:
        """Son güncellemeden bu yana max_age saniyeden az geçtiyse True."""
        if not self.description:
            return False
        return (time.time() - self.updated_at) < max_age

    def to_prompt_block(self) -> str:
        """LLM bağlamına eklenmek üzere kısa bir metin bloğu üretir."""
        if not self.description:
            return ""
        return (
            f"## Ekran Bağlamı\n"
            f"Aktif pencere: {self.active_window}\n"
            f"Ekranda: {self.description}"
        )


_ctx = ScreenContext()


def get_screen_context() -> ScreenContext:
    """Global ekran bağlamını döndürür."""
    return _ctx


def update_screen_context(active_window: str, description: str) -> None:
    """Ambient Watcher tarafından çağrılır; bağlamı günceller."""
    global _ctx
    _ctx.active_window = active_window
    _ctx.description = description
    _ctx.updated_at = time.time()

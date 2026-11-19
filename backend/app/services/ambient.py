"""Ambient Intelligence — Yuki arka planda ekranı izler, proaktif öneri sunar.

Faz J (temel):
  AMBIENT_INTERVAL saniyede bir ekran görüntüsü alır, Vision LLM ile analiz eder.
  Kullanıcı yardıma ihtiyaç duyuyorsa Event Bus üzerinden state_info yayınlar.

Faz K (geliştirmeler):
  - Screen diff detection: ekran değişmemişse LLM çağrısı yapma
  - Active window tracking: hyprctl activewindow -j ile odaktaki uygulama
  - detail="low": %75 token tasarrufu
  - AMBIENT_MODE: passive | active | focused

  AMBIENT_ENABLED=false (varsayılan) → servis başlamaz.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import re
import subprocess
import tempfile
import time as _time

from app.config import AMBIENT_ENABLED, AMBIENT_INTERVAL, AMBIENT_MODE

logger = logging.getLogger(__name__)
from app.services.event_bus import bus
from app.mesajlar import M

# Diff detection eşiği — değişen piksel oranı bu değerin üstündeyse analiz yap
_DIFF_THRESHOLD = 0.03   # %3

# passive mod — sadece "yardım lazım mı?" sorusu
_PROMPT_PASSIVE = """\
Aktif uygulama: {active_window}

Bu ekran görüntüsünde kullanıcının acil yardıma ihtiyacı var mı? \
(örneğin: açık terminal hatası, build hatası, kritik uyarı)
Eğer evet ise tek cümle Türkçe öneri yaz. \
Eğer hayır ise sadece "null" yaz. Başka hiçbir şey yazma."""

# active mod — kısa açıklama + yardım kontrolü (JSON)
_PROMPT_ACTIVE = """\
Aktif uygulama: {active_window}

Ekranda ne olduğunu 1-2 cümle ile özetle (description).
Sonra kullanıcının acil yardıma ihtiyacı var mı? (needs_help)
Yanıtı JSON formatında ver:
{{"description": "...", "needs_help": true|false, "suggestion": "..." veya null}}
Başka hiçbir şey yazma."""


def _has_significant_change(b64_prev: str | None, b64_curr: str) -> bool:
    """İki frame arasında anlamlı piksel farkı var mı?"""
    if b64_prev is None:
        return True
    try:
        from PIL import Image, ImageChops
        img_prev = Image.open(io.BytesIO(base64.b64decode(b64_prev))).convert("L")
        img_curr = Image.open(io.BytesIO(base64.b64decode(b64_curr))).convert("L")
        if img_prev.size != img_curr.size:
            img_curr = img_curr.resize(img_prev.size, Image.Resampling.LANCZOS)
        diff = ImageChops.difference(img_prev, img_curr)
        pixels = list(diff.getdata())
        changed = sum(1 for p in pixels if p > 20)
        ratio = changed / len(pixels)
        logger.debug("Diff oranı: %.3f (eşik: %.3f)", ratio, _DIFF_THRESHOLD)
        return ratio > _DIFF_THRESHOLD
    except Exception as e:
        logger.debug("Diff hesaplama hatası: %s", e)
        return True  # hata durumunda analiz et


def _get_active_window() -> str:
    """Hyprland'da odaktaki pencereyi döndürür: 'class: title'"""
    try:
        result = subprocess.run(
            ["hyprctl", "activewindow", "-j"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            cls = data.get("class", "?")
            title = data.get("title", "?")[:60]
            return f"{cls}: {title}"
    except Exception:
        pass
    return "bilinmiyor"


def _get_grim_env() -> dict:
    """grim için gerekli Wayland env değişkenlerini döndürür."""
    from app.services.tools import _build_wayland_env
    return _build_wayland_env()


def _capture_active_window_screenshot() -> str | None:
    """focused mod: sadece aktif pencerenin ekran görüntüsünü alır.

    Döndürür: base64 JPEG string veya None (hata durumunda)
    """
    try:
        from PIL import Image

        result = subprocess.run(
            ["hyprctl", "activewindow", "-j"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        data = json.loads(result.stdout)
        at = data.get("at", [0, 0])
        size = data.get("size", [1920, 1080])
        if size[0] < 50 or size[1] < 50:
            return None
        region = f"{at[0]},{at[1]} {size[0]}x{size[1]}"

        tmp_fd, tmp_img = tempfile.mkstemp(suffix=".png")
        os.close(tmp_fd)
        try:
            subprocess.run(
                ["grim", "-g", region, tmp_img],
                check=True, timeout=6, env=_get_grim_env(), capture_output=True
            )
            img = Image.open(tmp_img)
            img.thumbnail((960, 540))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=80)
            return base64.b64encode(buffered.getvalue()).decode("utf-8")
        finally:
            if os.path.exists(tmp_img):
                os.unlink(tmp_img)
    except Exception as e:
        logger.debug("Aktif pencere yakalama hatası: %s", e)
        return None


async def _analyze_screen(screenshot_b64: str, active_window: str, mode: str) -> dict:
    """Ekran görüntüsünü Vision LLM ile analiz et.

    Döndürür: {"needs_help": bool, "suggestion": str | None, "description": str}
    """
    try:
        from openai import AsyncOpenAI
        from app.config import OPENROUTER_API_KEY, VISION_MODEL, LLM_MODEL, USE_LOCAL_LLM

        if USE_LOCAL_LLM:
            return {"needs_help": False, "suggestion": None, "description": ""}

        # Vision analizi için VISION_MODEL kullan (gpt-4o-mini vision desteklemiyor)
        model = VISION_MODEL if VISION_MODEL else LLM_MODEL
        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )

        if mode == "active":
            prompt = _PROMPT_ACTIVE.format(active_window=active_window)
        else:
            prompt = _PROMPT_PASSIVE.format(active_window=active_window)

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{screenshot_b64}",
                                "detail": "low",  # %75 token tasarrufu
                            },
                        },
                    ],
                }
            ],
            timeout=20.0,
        )
        text = (response.choices[0].message.content or "").strip()

        if mode == "active":
            # LLM sık sık ```json ... ``` çitiyle döner → çitleri soy, ilk {...} bloğunu al.
            # (Aksi halde parse düşer ve ham JSON metni suggestion olarak UI'a sızıyordu.)
            candidate = text
            fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.DOTALL)
            if fence:
                candidate = fence.group(1)
            else:
                brace = re.search(r"\{.*\}", candidate, re.DOTALL)
                if brace:
                    candidate = brace.group(0)
            try:
                parsed = json.loads(candidate)
                return {
                    "needs_help": bool(parsed.get("needs_help", False)),
                    "suggestion": parsed.get("suggestion"),
                    "description": parsed.get("description", ""),
                }
            except json.JSONDecodeError:
                # JSON kurtarılamadı — ham metni description olarak ver (öneri DEĞİL;
                # needs_help=True yanlış alarm + ham çıktı baloncuğu üretiyordu)
                return {"needs_help": False, "suggestion": None, "description": text}

        # passive mod
        if text.lower() == "null" or not text:
            return {"needs_help": False, "suggestion": None, "description": ""}
        return {"needs_help": True, "suggestion": text, "description": ""}

    except Exception as e:
        logger.warning("Analiz hatası: %s", e)
        return {"needs_help": False, "suggestion": None, "description": ""}


# Modül düzeyinde singleton — API endpoint'lerinden erişim için
_watcher: "AmbientWatcher | None" = None


class AmbientWatcher:
    """Periyodik ekran analizi → proaktif öneri.

    K-fazı geliştirmeleri:
    - Diff detection: değişmemiş ekranlar LLM'e gönderilmez
    - Active window tracking: hangi uygulama odakta
    - detail="low": token tasarrufu
    - set_mode(): runtime mod değişimi
    """

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._mode: str = AMBIENT_MODE  # passive | active | focused
        self._last_b64: str | None = None
        self._last_analysis: dict = {
            "active_window": None,
            "needs_help": None,
            "suggestion": None,
            "description": None,
            "captured_at": None,
            "skipped": None,  # "no_change" | "not_idle" | None
        }

    async def start(self) -> None:
        global _watcher
        _watcher = self
        self._task = asyncio.create_task(self._loop())
        logger.info("Başlatıldı (interval=%ds, mod=%s)", AMBIENT_INTERVAL, self._mode)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def set_mode(self, mode: str) -> None:
        """Runtime mod değişimi: passive | active | focused | off"""
        if mode == "off":
            await self.stop()
            logger.info("Ambient izleme durduruldu.")
            return
        self._mode = mode
        logger.info("Mod değiştirildi: %s", mode)

    async def scan_now(self) -> dict:
        """Anında tek bir ekran taraması yapar, last_analysis'i günceller."""
        from app.services.tools import take_screenshot
        try:
            if self._mode == "focused":
                b64 = await asyncio.to_thread(_capture_active_window_screenshot)
                if b64 is None:
                    result = await asyncio.to_thread(take_screenshot)
                    if not result.startswith("SCREENSHOT_DATA:"):
                        return {"error": M("gorme.ekran-alinamadi")}
                    b64 = result.split(":", 1)[1]
            else:
                result = await asyncio.to_thread(take_screenshot)
                if not result.startswith("SCREENSHOT_DATA:"):
                    return {"error": M("gorme.ekran-alinamadi")}
                b64 = result.split(":", 1)[1]

            active_window = await asyncio.to_thread(_get_active_window)
            # Manuel taramada her zaman "active" mod kullan — description gelsin
            scan_mode = "active" if self._mode == "passive" else self._mode
            analysis = await _analyze_screen(b64, active_window, scan_mode)
            self._last_b64 = b64
            self._last_analysis = {
                "active_window": active_window,
                "needs_help": analysis["needs_help"],
                "suggestion": analysis.get("suggestion"),
                "description": analysis.get("description", ""),
                "captured_at": _time.time(),
                "skipped": None,
            }
            return self._last_analysis
        except Exception as e:
            logger.error("scan_now hatası: %s", e)
            return {"error": str(e)}

    def status(self) -> dict:
        return {
            "enabled": AMBIENT_ENABLED,
            "mode": self._mode,
            "interval": AMBIENT_INTERVAL,
            "running": self._task is not None and not self._task.done(),
            "last_analysis": self._last_analysis,
        }

    async def _loop(self) -> None:
        from app.services.tools import take_screenshot
        from app.services.state_machine import get_state_machine, YukiState

        sm = get_state_machine()

        while True:
            await asyncio.sleep(AMBIENT_INTERVAL)

            # Yuki konuşuyorsa atla (dikkat dağıtma)
            if sm.state != YukiState.IDLE:
                self._last_analysis["skipped"] = "not_idle"
                continue

            try:
                # focused mod: sadece aktif pencereyi yakala
                if self._mode == "focused":
                    b64 = await asyncio.to_thread(_capture_active_window_screenshot)
                    if b64 is None:
                        # fallback: tam ekran
                        result = await asyncio.to_thread(take_screenshot)
                        if not result.startswith("SCREENSHOT_DATA:"):
                            continue
                        b64 = result.split(":", 1)[1]
                else:
                    result = await asyncio.to_thread(take_screenshot)
                    if not result.startswith("SCREENSHOT_DATA:"):
                        continue
                    b64 = result.split(":", 1)[1]

                # Diff detection: ekran değişmediyse LLM çağrısı yapma
                if not _has_significant_change(self._last_b64, b64):
                    logger.debug("Ekran değişmedi, LLM çağrısı atlandı.")
                    self._last_analysis["skipped"] = "no_change"
                    continue
                self._last_b64 = b64
                self._last_analysis["skipped"] = None

                # Aktif pencereyi al
                active_window = await asyncio.to_thread(_get_active_window)

                analysis = await _analyze_screen(b64, active_window, self._mode)

                self._last_analysis = {
                    "active_window": active_window,
                    "needs_help": analysis["needs_help"],
                    "suggestion": analysis.get("suggestion"),
                    "description": analysis.get("description", ""),
                    "captured_at": _time.time(),
                    "skipped": None,
                }

                # Screen context güncelle (active modda description varsa)
                if analysis.get("description"):
                    try:
                        from app.services.screen_context import update_screen_context
                        update_screen_context(active_window, analysis["description"])
                    except ImportError:
                        pass  # screen_context henüz yüklü değilse geç

                if analysis["needs_help"] and analysis["suggestion"]:
                    logger.info("Öneri [%s | %s]: %s",
                                self._mode, active_window, analysis["suggestion"])
                    await bus.publish("state_info", {
                        "text": f"[Ambient] {analysis['suggestion']}",
                        "ambient": True,
                    })

            except Exception as e:
                logger.error("Döngü hatası: %s", e)

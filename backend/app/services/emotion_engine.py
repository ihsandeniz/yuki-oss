"""Yuki Emotion Engine — LLM duygu etiketlerini Live2D parametrelerine çevirir."""

from __future__ import annotations

import asyncio

from app.services.event_bus import bus

# ------------------------------------------------------------------ #
# Live2D Cubism parametre haritası
# Değer aralığı: 0.0–1.0 (ParamBodyAngleY hariç: derece)
# ------------------------------------------------------------------ #

_PARAMS: dict[str, dict[str, float]] = {
    "neutral": {
        "ParamEyeLOpen":   1.0,
        "ParamEyeROpen":   1.0,
        "ParamEyeLSmile":  0.0,
        "ParamEyeRSmile":  0.0,
        "ParamBrowLY":     0.0,
        "ParamBrowRY":     0.0,
        "ParamBrowLAngle": 0.0,
        "ParamBrowRAngle": 0.0,
        "ParamMouthOpenY": 0.0,
        "ParamMouthForm":  0.0,   # -1.0=mutsuz, 0=nötr, 1.0=gülümseme
        "ParamCheek":      0.0,
        "ParamBodyAngleX": 0.0,
        "ParamBodyAngleY": 0.0,
    },
    "happy": {
        "ParamEyeLOpen":   0.8,
        "ParamEyeROpen":   0.8,
        "ParamEyeLSmile":  0.9,
        "ParamEyeRSmile":  0.9,
        "ParamBrowLY":     0.3,
        "ParamBrowRY":     0.3,
        "ParamBrowLAngle": 0.2,
        "ParamBrowRAngle": 0.2,
        "ParamMouthOpenY": 0.2,
        "ParamMouthForm":  0.9,
        "ParamCheek":      0.3,
        "ParamBodyAngleX": 0.0,
        "ParamBodyAngleY": 3.0,
    },
    "sad": {
        "ParamEyeLOpen":   0.6,
        "ParamEyeROpen":   0.6,
        "ParamEyeLSmile":  0.0,
        "ParamEyeRSmile":  0.0,
        "ParamBrowLY":    -0.3,
        "ParamBrowRY":    -0.3,
        "ParamBrowLAngle":-0.4,
        "ParamBrowRAngle":-0.4,
        "ParamMouthOpenY": 0.0,
        "ParamMouthForm": -0.7,
        "ParamCheek":      0.0,
        "ParamBodyAngleX": 0.0,
        "ParamBodyAngleY":-5.0,
    },
    "angry": {
        "ParamEyeLOpen":   1.2,
        "ParamEyeROpen":   1.2,
        "ParamEyeLSmile":  0.0,
        "ParamEyeRSmile":  0.0,
        "ParamBrowLY":     0.2,
        "ParamBrowRY":     0.2,
        "ParamBrowLAngle":-0.8,
        "ParamBrowRAngle":-0.8,
        "ParamMouthOpenY": 0.1,
        "ParamMouthForm": -0.5,
        "ParamCheek":      0.0,
        "ParamBodyAngleX": 2.0,
        "ParamBodyAngleY": 0.0,
    },
    "surprised": {
        "ParamEyeLOpen":   1.5,
        "ParamEyeROpen":   1.5,
        "ParamEyeLSmile":  0.0,
        "ParamEyeRSmile":  0.0,
        "ParamBrowLY":     0.7,
        "ParamBrowRY":     0.7,
        "ParamBrowLAngle": 0.0,
        "ParamBrowRAngle": 0.0,
        "ParamMouthOpenY": 0.6,
        "ParamMouthForm":  0.0,
        "ParamCheek":      0.0,
        "ParamBodyAngleX": 0.0,
        "ParamBodyAngleY":-2.0,
    },
    "shy": {
        "ParamEyeLOpen":   0.7,
        "ParamEyeROpen":   0.7,
        "ParamEyeLSmile":  0.5,
        "ParamEyeRSmile":  0.5,
        "ParamBrowLY":     0.0,
        "ParamBrowRY":     0.0,
        "ParamBrowLAngle": 0.2,
        "ParamBrowRAngle": 0.2,
        "ParamMouthOpenY": 0.0,
        "ParamMouthForm":  0.3,
        "ParamCheek":      0.8,
        "ParamBodyAngleX":-3.0,
        "ParamBodyAngleY":-3.0,
    },
    "tired": {
        "ParamEyeLOpen":   0.3,
        "ParamEyeROpen":   0.3,
        "ParamEyeLSmile":  0.0,
        "ParamEyeRSmile":  0.0,
        "ParamBrowLY":    -0.2,
        "ParamBrowRY":    -0.2,
        "ParamBrowLAngle":-0.1,
        "ParamBrowRAngle":-0.1,
        "ParamMouthOpenY": 0.1,
        "ParamMouthForm": -0.2,
        "ParamCheek":      0.0,
        "ParamBodyAngleX": 0.0,
        "ParamBodyAngleY":-8.0,
    },
}

_NEUTRAL = _PARAMS["neutral"]

SUPPORTED_EMOTIONS = set(_PARAMS.keys())


def _lerp(a: dict[str, float], b: dict[str, float], t: float) -> dict[str, float]:
    """İki parametre seti arasında doğrusal interpolasyon."""
    return {k: a[k] + (b[k] - a[k]) * t for k in a}


class EmotionEngine:
    def __init__(self) -> None:
        self._emotion = "neutral"
        self._intensity = 0.0
        self._decay_task: asyncio.Task | None = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @property
    def emotion(self) -> str:
        return self._emotion

    @property
    def intensity(self) -> float:
        return self._intensity

    async def update(self, emotion: str, intensity: float, voice_hint: str = "neutral") -> None:
        """LLM çıktısından gelen duyguyu uygula.

        voice_hint: analyze_voice_emotion() sonucu — neutral dışındaysa intensity %20 artar.
        Çelişki durumunda LLM duygusu önceliklidir.
        """
        emotion = emotion if emotion in SUPPORTED_EMOTIONS else "neutral"
        intensity = max(0.0, min(1.0, intensity))

        # Faz H: ses tonu güçlendirme
        if voice_hint != "neutral" and voice_hint in SUPPORTED_EMOTIONS:
            intensity = min(1.0, intensity * 1.2)

        self._emotion = emotion
        self._intensity = intensity

        await bus.publish("emotion", {"emotion": emotion, "intensity": intensity})
        await bus.publish("live2d", {"params": self._current_params()})

        # Önceki decay'i iptal et ve yeniden başlat
        if self._decay_task and not self._decay_task.done():
            self._decay_task.cancel()
        if emotion != "neutral":
            self._decay_task = asyncio.create_task(self._decay_loop())

    async def reset(self) -> None:
        """Anında nötre dön (konuşma bitişinde)."""
        if self._decay_task and not self._decay_task.done():
            self._decay_task.cancel()
        self._emotion = "neutral"
        self._intensity = 0.0
        await bus.publish("emotion", {"emotion": "neutral", "intensity": 0.0})
        await bus.publish("live2d", {"params": _NEUTRAL})

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _current_params(self) -> dict[str, float]:
        target = _PARAMS.get(self._emotion, _NEUTRAL)
        return _lerp(_NEUTRAL, target, self._intensity)

    async def _decay_loop(self) -> None:
        """Duygu intensitesini 5 sn sonra yavaşça nötre çek (~8 sn)."""
        await asyncio.sleep(5.0)
        while self._intensity > 0.05:
            self._intensity = max(0.0, self._intensity - 0.08)
            await bus.publish("live2d", {"params": self._current_params()})
            await asyncio.sleep(0.25)
        self._emotion = "neutral"
        self._intensity = 0.0
        await bus.publish("emotion", {"emotion": "neutral", "intensity": 0.0})
        await bus.publish("live2d", {"params": _NEUTRAL})


# Singleton
_engine: EmotionEngine | None = None


def get_emotion_engine() -> EmotionEngine:
    global _engine
    if _engine is None:
        _engine = EmotionEngine()
    return _engine

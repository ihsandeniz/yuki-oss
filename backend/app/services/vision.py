"""Faz 4 — Vision servisi: ekran görüntüsü al + Vision LLM ile analiz et."""

from __future__ import annotations

import logging

from app.config import VISION_MODEL
from app.services.llm import ChatResponse, _get_client, _parse_tags

log = logging.getLogger(__name__)


def _capture_screenshot() -> str:
    """Ekranı yakala, JPEG base64 döndür. Wayland/X11 destekli (tools.py üzerinden)."""
    from app.services.tools import take_screenshot as _take_screenshot_raw
    raw = _take_screenshot_raw()
    if raw.startswith("SCREENSHOT_DATA:"):
        return raw.split(":", 1)[1]
    raise RuntimeError(raw)


async def capture_and_analyze(prompt: str) -> ChatResponse:
    """Ekran görüntüsü al ve Vision LLM ile analiz et.

    Args:
        prompt: Kullanıcının sorusu, ör. "Ekranda ne var?"

    Returns:
        ChatResponse (temiz metin + duygu etiketi)
    """
    log.info("[vision] Ekran yakalanıyor…")
    img_b64 = _capture_screenshot()
    log.info("[vision] Ekran yakalandı, Vision LLM'e gönderiliyor…")

    client = _get_client()

    response = await client.chat.completions.create(
        model=VISION_MODEL,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_b64}",
                            "detail": "low",
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            f"{prompt}\n\n"
                            "Yanıtının SONUNA (ayrı satırlarda) duygu ve davranış etiketlerini ekle:\n"
                            '[EMOTION:{"emotion":"<happy|sad|angry|surprised|shy|tired|neutral>","intensity":<0.0-1.0>}]\n'
                            '[BEHAVIOR:{"action":"<idle|nod|wave>"}]'
                        ),
                    },
                ],
            }
        ],
    )

    raw_text = response.choices[0].message.content or ""
    clean_text, emotion, _ = _parse_tags(raw_text)
    log.info("[vision] Yanıt alındı, emotion=%s", emotion.emotion)

    return ChatResponse(text=clean_text, emotion=emotion)

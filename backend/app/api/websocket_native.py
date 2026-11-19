"""/ws/native — Gemini Native Audio WebSocket endpoint.

Faz α: Tek Gemini Live API oturumu üzerinden bidirectional ses akışı.

Protokol (Client → Server):
    - Binary frame: WAV ses verisi
    - Text frame:   {"type": "text", "message": "..."}

Protokol (Server → Client):
    - {"type": "audio_chunk", "data": "<base64 PCM>", "mime": "audio/pcm;rate=24000"}
    - {"type": "text", "chunk": "..."}
    - {"type": "done"}
    - {"type": "error", "message": "..."}
"""

import asyncio
import base64
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.mesajlar import M
from app.config import GEMINI_API_KEY, GEMINI_LIVE_MODEL, GEMINI_LIVE_VOICE, GEMINI_NATIVE_AUDIO
from app.services.native_audio import GeminiLiveSession
from app.config import build_system_prompt

logger = logging.getLogger(__name__)

router = APIRouter()

# State sabitleri
_IDLE = "IDLE"
_THINKING = "THINKING"
_TALKING = "TALKING"


async def _send_json(ws: WebSocket, data: dict) -> None:
    """JSON frame gönderir; disconnect durumunda sessizce geçer."""
    try:
        await ws.send_text(json.dumps(data, ensure_ascii=False))
    except Exception:
        pass


@router.websocket("/ws/native")
async def ws_native(websocket: WebSocket):
    """Gemini Native Audio WebSocket bağlantısı.

    GEMINI_NATIVE_AUDIO=false ise 503 döner.
    GEMINI_API_KEY eksikse 503 döner.
    """
    # WP3: WebSocket token doğrulaması — middleware'de ölü kod, el-içi kontrol gerekli
    from app.config import AUTH_TOKEN
    from app.services import api_guard
    import secrets
    _token = websocket.query_params.get("token", "")
    if AUTH_TOKEN and not api_guard.ws_gecer(websocket, _token, AUTH_TOKEN):
        await websocket.close(code=4401, reason="Unauthorized")
        return
    from app.services import ag_ayari
    if not ag_ayari.ws_izinli(websocket):
        await websocket.close(code=4401, reason="Unauthorized")
        return

    # Özellik kapalıysa önce ACCEPT sonra close — accept'siz close istemciye
    # HTTP 403 el sıkışması olarak yansır ve 4503 kodu hiç ulaşmaz (frontend
    # bunun yerine 1006 görüp sonsuz reconnect döngüsüne giriyordu).
    if not GEMINI_NATIVE_AUDIO:
        await websocket.accept()
        await websocket.close(code=4503, reason="GEMINI_NATIVE_AUDIO devre dışı")  # i18n-istisna: WS kapanış gerekçesi — istemci kodu (4503) okur, metni göstermez
        return

    if not GEMINI_API_KEY:
        await websocket.accept()
        await websocket.close(code=4503, reason="GEMINI_API_KEY eksik")
        return

    await websocket.accept()
    logger.info("Gemini Native Audio bağlantısı: %s", websocket.client)

    state = _IDLE
    system_prompt = build_system_prompt()

    try:
        async with GeminiLiveSession(
            api_key=GEMINI_API_KEY,
            model=GEMINI_LIVE_MODEL,
            voice=GEMINI_LIVE_VOICE,
            system_prompt=system_prompt,
        ) as session:

            async def _receive_loop():
                """Gemini'den gelen yanıtları WebSocket'e yönlendirir."""
                nonlocal state
                async for chunk in session.receive():
                    if chunk.audio:
                        state = _TALKING
                        encoded = base64.b64encode(chunk.audio).decode()
                        await _send_json(websocket, {
                            "type": "audio_chunk",
                            "data": encoded,
                            "mime": "audio/pcm;rate=24000",
                        })
                    if chunk.text:
                        await _send_json(websocket, {
                            "type": "text",
                            "chunk": chunk.text,
                        })
                    if chunk.turn_complete:
                        state = _IDLE
                        await _send_json(websocket, {"type": "done"})

            # İstemciden gelen frame'leri işle
            while True:
                try:
                    raw = await asyncio.wait_for(websocket.receive(), timeout=60.0)
                except asyncio.TimeoutError:
                    # Heartbeat (boşta bağlantıyı koru)
                    await _send_json(websocket, {"type": "ping"})
                    continue

                if "bytes" in raw and raw["bytes"]:
                    # Ses frame (WAV)
                    wav_bytes = raw["bytes"]
                    state = _THINKING
                    logger.debug("Ses alındı: %d bytes", len(wav_bytes))

                    await session.send_audio(wav_bytes)

                    # Yanıt akışını başlat
                    try:
                        await asyncio.wait_for(_receive_loop(), timeout=30.0)
                    except asyncio.TimeoutError:
                        logger.warning("Gemini yanıtı zaman aşımı")
                        await _send_json(websocket, {
                            "type": "error",
                            "message": M("ses.yanit-zaman-asimi"),
                        })
                        state = _IDLE

                elif "text" in raw and raw["text"]:
                    # Text frame
                    try:
                        payload = json.loads(raw["text"])
                    except json.JSONDecodeError:
                        await _send_json(websocket, {
                            "type": "error",
                            "message": M("ses.gecersiz-json"),
                        })
                        continue

                    if payload.get("type") == "text":
                        msg = payload.get("message", "").strip()
                        if not msg:
                            continue

                        state = _THINKING
                        await session.send_text(msg)

                        try:
                            await asyncio.wait_for(_receive_loop(), timeout=30.0)
                        except asyncio.TimeoutError:
                            logger.warning("Gemini yanıtı zaman aşımı (text)")
                            await _send_json(websocket, {
                                "type": "error",
                                "message": M("ses.yanit-zaman-asimi"),
                            })
                            state = _IDLE

    except WebSocketDisconnect:
        logger.info("Gemini Native Audio bağlantısı kesildi")
    except Exception as e:
        logger.error("Gemini Native Audio hatası: %s", e, exc_info=True)
        try:
            await _send_json(websocket, {
                "type": "error",
                "message": M("ses.sunucu-hatasi", sebep=e),
            })
            await websocket.close()
        except Exception:
            pass

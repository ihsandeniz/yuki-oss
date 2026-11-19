"""Voice endpoint — audio in, audio out (STT + LLM + TTS pipeline)."""

import base64

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.limiter import limiter
from app.mesajlar import M
from app.services.llm import LLMUserError, chat_sync
from app.services.stt import reset_stt, stt_status, transcribe
from app.services.tts import synthesize

router = APIRouter(prefix="/api", tags=["voice"])

MAX_AUDIO_SIZE = 25 * 1024 * 1024  # 25 MB
ALLOWED_TYPES = {"audio/wav", "audio/mp3", "audio/mpeg", "audio/ogg", "audio/webm", "audio/x-wav"}


class VoiceReply(BaseModel):
    transcription: str
    reply: str
    emotion: str
    intensity: float
    audio_base64: str


@router.post("/voice", response_model=VoiceReply)
@limiter.limit("10/minute")
async def voice(request: Request, file: UploadFile = File(...)):
    """Full voice pipeline: audio -> STT -> LLM -> TTS -> audio response."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail=M("stt.format"))

    audio_bytes = await file.read()

    if len(audio_bytes) > MAX_AUDIO_SIZE:
        raise HTTPException(status_code=413, detail=M("stt.dosya-buyuk"))

    # STT
    transcription = await transcribe(audio_bytes)

    # LLM
    try:
        response = await chat_sync(transcription)
    except LLMUserError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    # TTS
    audio_out = await synthesize(response.text)
    audio_b64 = base64.b64encode(audio_out).decode("ascii")

    return VoiceReply(
        transcription=transcription,
        reply=response.text,
        emotion=response.emotion.emotion,
        intensity=response.emotion.intensity,
        audio_base64=audio_b64,
    )


@router.get("/stt/status")
@limiter.limit("30/minute")
async def stt_status_endpoint(request: Request):

    """STT/mikrofon kullanılabilirliği + model varlığı (frontend indirme akışı için).

    {available: native runtime var mı, model_present: model diskte mi, loaded, model_id}
    """
    return stt_status()


@router.post("/stt/reload")
@limiter.limit("20/minute")
async def stt_reload_endpoint(request: Request):

    """STT modül durumunu sıfırla — indir-gerektiğinde model indirildikten sonra çağrılır;
    böylece yeni model backend'i tam yeniden başlatmadan devreye girer.
    """
    reset_stt()
    return {"ok": True, **stt_status()}

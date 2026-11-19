"""Chat endpoints — sync reply + SSE streaming."""

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.limiter import limiter
from app.mesajlar import M

# BYOK: kullanıcı key girmeden sohbet ederse generic "hata oluştu" yerine sihirbaza yönlendir.
#
# 🔴 2026-08-28 — bu kapı 15 sağlayıcının 2'sini biliyordu.
# Eski hâli yalnız OPENROUTER_API_KEY / ANTHROPIC_API_KEY / USE_LOCAL_LLM'e
# bakıyordu. Ama 2026-08-05'te çok sağlayıcılı BYOK geldi: seçim artık
# `LLM_PROVIDER` ile yapılıyor ve kayıtta 15 sağlayıcı var. Kapı güncellenmedi.
#
# Ölçüldü (geliştiricinin makinesi, LLM_PROVIDER=ollama): seçili sağlayıcı Ollama,
# `yerel_mi=True`, `anahtar_gerekir=False` — buna rağmen kapı "anahtar yok" deyip
# /api/chat'i 503'e düşürüyor ve kullanıcıya *"OpenRouter anahtarını gir"* diyordu.
# Etki yalnız Ollama değil: google/openai/groq/cerebras/deepseek/mistral/xai/
# together/fireworks/deepinfra/nebius/chutes — **13 sağlayıcı** bu kapının
# arkasında ölüydü. Yani satılan bir özellik (BYOK) hiç çalışmıyordu.
#
# 🪤 Sınıf: YANLIŞ TEŞHİS. Bu depoda üçüncü kez — ElevenLabs 401=kota,
# OpenRouter 429=günlük/dakikalık. Hepsinde mesaj kullanıcıyı OLMAYAN bir
# soruna yolluyor; burada yerel modeli seçmiş kullanıcı bulut anahtarı almaya
# gidiyordu.
#
# Doğru soru "herhangi bir anahtar var mı" DEĞİL:
#   **"SEÇİLİ sağlayıcının ihtiyacı karşılanıyor mu?"**


def _secili_saglayici() -> str:
    import app.config as _cfg
    return (getattr(_cfg, "LLM_PROVIDER", "") or "openrouter").strip()


def _llm_key_missing() -> bool:
    """Seçili sağlayıcı sohbet edebilir durumda değilse True."""
    import app.config as _cfg
    from app.services import llm_providers as _lp

    # Elle zorlanmış yerel mod — sağlayıcı ne olursa olsun anahtar istemez.
    if getattr(_cfg, "USE_LOCAL_LLM", False):
        return False

    kimlik = _secili_saglayici()

    # Bilinmeyen kimlik: kayıtta yoksa karar veremeyiz. Eski davranışa düş
    # (herhangi bir anahtar var mı) — kapıyı bilmediğimiz bir ada dayanarak
    # KAPATMAK, çalışan bir kurulumu susturmak olurdu.
    if _lp.kayit(kimlik) is None:
        return not (
            getattr(_cfg, "OPENROUTER_API_KEY", "")
            or getattr(_cfg, "ANTHROPIC_API_KEY", "")
        )

    if not _lp.anahtar_gerekir(kimlik):   # yerel (Ollama) → anahtar diye bir şey yok
        return False

    return not _lp.anahtar(kimlik)


def _no_key_msg() -> str:
    """Mesaj SEÇİLİ sağlayıcıya göre yazılır.

    Ollama seçiliyken `openrouter.ai/keys` demek anlamsızdı; Groq seçiliyken
    OpenRouter'a yollamak ise kullanıcıyı yanlış siteye gönderirdi.
    """
    from app.services import llm_providers as _lp

    sag = _lp.kayit(_secili_saglayici())
    if sag is None:
        return M("anahtar.saglayici-yok")
    if sag.yerel:
        # Bu dal normalde ULAŞILMAZ (yerelde kapı zaten açık). Yine de doğru
        # yazıldı: yerel sağlayıcıda sorun "anahtar" değil "motor çalışmıyor"
        # olur; oraya anahtar istemek yeni bir yanlış teşhis olurdu.
        return M("anahtar.yerel-yanit-yok", saglayici=sag.ad, url=sag.anahtar_url)
    url = f" ({sag.anahtar_url})" if sag.anahtar_url else ""
    return M("anahtar.saglayici-anahtari-yok", saglayici=sag.ad, url=url)
from app.services.llm import (
    ChatResponse,
    LLMUserError,
    chat_stream,
    chat_sync,
    clear_history,
)
from app.services.state_machine import YukiState, get_state_machine
from app.services.emotion_engine import get_emotion_engine

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatReply(BaseModel):
    reply: str
    emotion: str
    intensity: float
    state: str


@router.post("/chat", response_model=ChatReply)
@limiter.limit("20/minute")
async def chat(request: Request, req: ChatRequest):
    """Sync chat — mesaj gönder, tam yanıt + duygu etiketi al."""
    if _llm_key_missing():
        raise HTTPException(status_code=503, detail=_no_key_msg())
    sm = get_state_machine()
    ee = get_emotion_engine()

    if sm.state != YukiState.IDLE:
        await sm.force(YukiState.IDLE)
    await sm.transition(YukiState.LISTENING)
    await sm.transition(YukiState.THINKING)

    try:
        resp: ChatResponse = await chat_sync(req.message)
    except LLMUserError as e:
        # Geçersiz anahtar / kota / erişim — 500 yerine sebebi söyleyen 503.
        await sm.force(YukiState.IDLE)
        raise HTTPException(status_code=503, detail=str(e)) from e

    await ee.update(resp.emotion.emotion, resp.emotion.intensity)
    await sm.transition(YukiState.TALKING)
    await sm.force(YukiState.IDLE)

    return ChatReply(
        reply=resp.text,
        emotion=resp.emotion.emotion,
        intensity=resp.emotion.intensity,
        state=sm.state.value,
    )


@router.post("/chat/stream")
@limiter.limit("20/minute")
async def chat_stream_sse(request: Request, req: ChatRequest):
    """Streaming chat — SSE, token by token."""
    if _llm_key_missing():
        async def _no_key_gen():
            yield f"data: [ERROR] {_no_key_msg()}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(_no_key_gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    sm = get_state_machine()

    if sm.state != YukiState.IDLE:
        await sm.force(YukiState.IDLE)
    await sm.transition(YukiState.LISTENING)
    await sm.transition(YukiState.THINKING)

    async def event_generator():
        try:
            first_chunk = True
            async for chunk in chat_stream(req.message):
                if first_chunk:
                    await sm.transition(YukiState.TALKING)
                    first_chunk = False
                yield f"data: {chunk}\n\n"
            await sm.force(YukiState.IDLE)
            yield "data: [DONE]\n\n"
        except LLMUserError as e:
            await sm.force(YukiState.IDLE)
            log.error("chat_stream LLM hatası: %s", e)
            yield f"data: [ERROR] {e}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            await sm.force(YukiState.IDLE)
            log.error("chat_stream error: %s", repr(e))
            yield f"data: [ERROR] {M('hata.tekrar-dene')}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/chat/history")
@limiter.limit("100/minute")
async def chat_history(request: Request):
    """Aktif karakterin kalıcı sohbet geçmişi — UI açılışta geri yükler (lite memory)."""
    from app.services.llm import _get_history
    return {"messages": list(_get_history())}


@router.post("/chat/clear")
@limiter.limit("10/minute")
async def chat_clear(request: Request):
    """Konuşma geçmişini ve duygu durumunu sıfırla (pgvector dahil)."""
    await clear_history()
    await get_emotion_engine().reset()
    await get_state_machine().force(YukiState.IDLE)
    return {"status": "ok"}


@router.post("/chat/clear-messages")
@limiter.limit("10/minute")
async def chat_clear_messages(request: Request):
    """Sadece aktif konuşma bağlamını sıfırla — pgvector hafızasına dokunma."""
    await clear_history(clear_pgvector=False)
    await get_emotion_engine().reset()
    await get_state_machine().force(YukiState.IDLE)
    return {"status": "ok"}


@router.get("/state")
@limiter.limit("100/minute")
async def get_state(request: Request):
    """Mevcut durum ve duygu bilgisi."""
    sm = get_state_machine()
    ee = get_emotion_engine()
    return {
        "state": sm.state.value,
        "emotion": ee.emotion,
        "intensity": ee.intensity,
    }


@router.get("/tokens")
@limiter.limit("100/minute")
async def get_tokens(request: Request):
    """Oturum token kullanımı ve tahmini maliyet."""
    from app.services.llm import get_token_stats
    stats = get_token_stats()
    prompt = stats.get("prompt", 0)
    completion = stats.get("completion", 0)
    # GPT-4.1-mini fiyatı: $0.40/1M prompt, $1.60/1M completion
    cost = (prompt * 0.40 + completion * 1.60) / 1_000_000
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "estimated_cost_usd": round(cost, 5),
    }


# `/api/shell` SÖKÜLDÜ (v0.8.1, denetim H2): kapısız `bash -c` koşan bir HTTP ucuydu.
# Açık kaynak sürümde kabuk/komut çalıştırma aracı da yok. Geri ekleme →
# tests/test_shell_ucu_yok.py kırmızı olur.


@router.get("/metrics")
@limiter.limit("100/minute")
async def get_metrics(request: Request):
    """CPU, RAM, disk metrikleri."""
    import psutil, os
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cpu_pct": cpu,
        "ram_pct": mem.percent,
        "ram_used_gb": round(mem.used / 1024**3, 2),
        "ram_total_gb": round(mem.total / 1024**3, 2),
        "disk_pct": disk.percent,
        "disk_used_gb": round(disk.used / 1024**3, 1),
        "disk_total_gb": round(disk.total / 1024**3, 1),
    }

@router.get("/sys-metrics")
@limiter.limit("100/minute")
async def get_sys_metrics(request: Request):
    """Legacy alias — CPU, RAM, disk metrikleri (backward compatibility)."""
    return await get_metrics()

"""Text-to-Speech — Fish Speech S2 → ElevenLabs → Edge TTS → Google TTS (fallback zinciri).

Faz A3:  synthesize_stream() + TTSChunk + asyncio.Queue pipeline.
Faz G:   edge-tts native stream() (temp file yok).
Faz 11:  ElevenLabs zincirden kaldırıldı — tam lokal TTS.
         _synthesize_elevenlabs / _stream_elevenlabs korunuyor (manuel çağrı için).
Faz 14+: Fish Speech S2 lokal SOTA TTS (USE_FISH_TTS=true) — zincirin en üstü.
         Ayrı api_server'a msgpack HTTP isteği; TTFA ~100ms streaming.
Faz 15+: ElevenLabs USE_ELEVENLABS_TTS=true ile zincire eklendi (Fish → EL → Edge).
Latency: synthesize_streaming() — audio chunk'larını anında yield eder.

Fallback zinciri:
  1. Fish Speech S2 (USE_FISH_TTS=true ise — ayrı api_server, lokal SOTA)
  2. ElevenLabs (USE_ELEVENLABS_TTS=true ve ELEVENLABS_API_KEY varsa)
  3. Edge TTS → hata/boş ses verirse Google çeviri TTS (2026-10-10, Edge 403)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import edge_tts
import httpx

from app.config import (
    EDGE_VOICE_RATE,
    EDGE_VOICE_PITCH,
    get_lang_config,
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
    USE_ELEVENLABS_TTS,
    USE_FISH_TTS,
    FISH_TTS_URL,
    FISH_REFERENCE_AUDIO,
    FISH_REFERENCE_TEXT,
    FISH_TTS_FORMAT,
    FISH_TTS_TIMEOUT,
)

logger = logging.getLogger(__name__)

# Edge TTS sesi dile göre seçilir → config.LANGUAGES[<dil>]["edge_voice"]
# (tr → tr-TR-EmelNeural, ja → ja-JP-NanamiNeural)
#
# ⚠️ Bu cümle 2026-09-18'e kadar YANLIŞTI: ses gerçekten dile göre seçiliyordu ama
# altı satır aşağıda persona tablosundan gelen sabit `edge_voice` onu eziyordu.
# Yorum doğruyu, kod başka şeyi söylüyordu. Persona artık ses KİMLİĞİ taşımıyor,
# yalnız ÜSLUP (rate/pitch) katıyor → `personas.py` başındaki uyarıya bak.

# Paylaşılan httpx client (connection pooling)
_shared_client: Optional[httpx.AsyncClient] = None

# ── ElevenLabs hata teşhisi ──────────────────────────────────────────
# 🔴 2026-08-02: log her cevapta `401 Unauthorized` basıyordu, anahtar geçersiz
# sanıldı — DEĞİLDİ. Ölçüm: GET /v1/voices → 200 (21 ses erişilebilir), ama
# POST .../stream → 401 ve GÖVDEDE {"code":"quota_exceeded",
# "message":"You have 0 credits remaining"}. ElevenLabs kota aşımına 429 değil
# **401** döndürüyor. Çıplak `raise_for_status()` yalnız durum satırını yakalayıp
# gövdeyi atıyordu → 2 hafta yanlış teşhis.
#
# BYOK ürününde bu doğrudan yanlış destek yanıtı demek: kullanıcının kotası bitince
# "anahtarın geçersiz" demek onu anahtarını boşuna değiştirmeye yönlendirir.
_KALICI_KODLAR = frozenset({
    "quota_exceeded",
    "unauthorized",
    "invalid_api_key",
    "missing_api_key",
    "voice_not_found",
    "voice_limit_reached",
    "detected_unusual_activity",
})

# Kalıcı hatada katman O OTURUM için kapatılır. Yoksa HER cevap önce boşa bir ağ
# turu öder (her yanıta gecikme ekler). Yuki susmaz — Edge TTS devralır.
_elevenlabs_kapali_sebep: Optional[str] = None


class _ElevenLabsKaliciHata(RuntimeError):
    """Yeniden denemenin işe yaramayacağı ElevenLabs hatası (kota/anahtar/ses)."""


def _elevenlabs_hata_ayikla(resp: httpx.Response) -> tuple[str, str]:
    """Yanıt gövdesinden (kod, mesaj) çıkar. Gövde JSON değilse ham metne düş."""
    try:
        govde = resp.json()
    except Exception:
        return "", (resp.text or "")[:200]
    detay = govde.get("detail", govde) if isinstance(govde, dict) else {}
    if isinstance(detay, str):
        return "", detay[:200]
    if not isinstance(detay, dict):
        return "", str(detay)[:200]
    return str(detay.get("status") or detay.get("code") or ""), str(detay.get("message") or "")[:200]


async def _elevenlabs_durum_dogrula(resp: httpx.Response) -> None:
    """`raise_for_status()` yerine — hata gövdesini OKUYUP gerçek sebebi söyler.

    Stream modunda gövde tembeldir; okumak için önce `aread()` gerekir.
    """
    if resp.status_code < 400:
        return
    global _elevenlabs_kapali_sebep
    await resp.aread()
    kod, mesaj = _elevenlabs_hata_ayikla(resp)
    ozet = f"HTTP {resp.status_code}" + (f" [{kod}]" if kod else "") + (f" {mesaj}" if mesaj else "")
    if kod in _KALICI_KODLAR:
        _elevenlabs_kapali_sebep = ozet
        logger.error(
            "ElevenLabs kalıcı hata — katman bu oturum için kapatıldı, Edge TTS devralıyor: %s", ozet
        )
        raise _ElevenLabsKaliciHata(ozet)
    raise RuntimeError(ozet)


def _elevenlabs_kullanilabilir() -> bool:
    """Zincirde ElevenLabs denenmeli mi (kalıcı hata sonrası boşa ağ turu atma)."""
    return bool(USE_ELEVENLABS_TTS and ELEVENLABS_API_KEY and _elevenlabs_kapali_sebep is None)


def elevenlabs_durumu_sifirla() -> None:
    """Kullanıcı yeni anahtar/kota girdiğinde katmanı yeniden aç (ayar panelinden çağrılabilir)."""
    global _elevenlabs_kapali_sebep
    _elevenlabs_kapali_sebep = None


def _get_shared_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(timeout=15.0)
    return _shared_client


@dataclass
class TTSChunk:
    """Bir cümlenin TTS sonucu."""
    text: str
    audio: bytes


_SESLENDIRILEBILIR = re.compile(r"[^\W\d_]", re.UNICODE)   # en az bir harf


def seslendirilebilir_mi(text: str) -> bool:
    """Metinde seslendirilecek bir şey var mı (en az bir harf)?

    🔴 2026-08-02 saha raporu (Windows 10, kullanıcı):
        ERROR websocket — Beklenmedik hata: No audio was received.
                          Please verify that your parameters are correct.

    Bu mesaj **Edge TTS'e aittir** ve metin boş/yalnız noktalama olduğunda gelir.
    Aynı logda LLM hataları vardı: model cevap veremeyince elde boş metin kalıyor,
    boş metin TTS'e gönderiliyor ve kullanıcı asıl sorun yerine anlamsız bir TTS
    hatası görüyordu — **hatanın kendisi hatayı gizliyordu.**
    """
    return bool(text and _SESLENDIRILEBILIR.search(text))


async def synthesize(text: str) -> bytes:
    """Convert text to audio bytes.

    Fallback zinciri: Fish Speech S2 → ElevenLabs → Edge TTS → Google TTS.
    """
    if not seslendirilebilir_mi(text):
        # Sessizce boş dön: seslendirilecek bir şey yok, bu bir HATA DEĞİL.
        logger.debug("TTS atlandı — seslendirilebilir metin yok: %r", (text or "")[:40])
        return b""

    if USE_FISH_TTS:
        try:
            return await _synthesize_fish(text)
        except Exception as e:
            logger.warning("Fish Speech hatası: %s. Sonraki TTS katmanına dönülüyor.", e)

    if _elevenlabs_kullanilabilir():
        try:
            return await _synthesize_elevenlabs(text)
        except Exception as e:
            logger.warning("ElevenLabs hatası: %s. Sonraki TTS katmanına dönülüyor.", e)

    return await _synthesize_edge(text)


async def _synthesize_elevenlabs(text: str) -> bytes:
    """ElevenLabs /stream endpoint — ilk chunk geldiği anda veri akar, temp file yok."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY,
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.85,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }
    client = _get_shared_client()
    chunks: list[bytes] = []
    async with client.stream("POST", url, json=data, headers=headers) as resp:
        await _elevenlabs_durum_dogrula(resp)
        async for chunk in resp.aiter_bytes(chunk_size=1024):
            if chunk:
                chunks.append(chunk)
    return b"".join(chunks)


def _fish_payload(text: str, streaming: bool) -> dict:
    """Fish Speech api_server istek gövdesi (ServeTTSRequest şeması).

    Yuki sesi için FISH_REFERENCE_AUDIO varsa voice cloning referansı eklenir.
    """
    references = []
    if FISH_REFERENCE_AUDIO and Path(FISH_REFERENCE_AUDIO).exists():
        with open(FISH_REFERENCE_AUDIO, "rb") as f:
            references.append({"audio": f.read(), "text": FISH_REFERENCE_TEXT})
    return {
        "text": text,
        "references": references,
        "reference_id": None,
        "format": FISH_TTS_FORMAT,
        "streaming": streaming,
        "normalize": True,
    }


async def _synthesize_fish(text: str) -> bytes:
    """Fish Speech S2 — lokal SOTA TTS, ayrı API sunucusuna HTTP POST.

    Sunucu (kullanıcı ayrı başlatır): `python -m tools.api_server --listen 0.0.0.0:8080`.
    İstek gövdesi msgpack ile kodlanır (resmi `api_server` formatı). ormsgpack
    yoksa veya sunucu yanıt vermezse istisna fırlatır → zincir alt katmana düşer.
    """
    import ormsgpack  # fish-speech zaten kullanır; USE_FISH_TTS=true ise gerekli
    url = f"{FISH_TTS_URL.rstrip('/')}/v1/tts"
    body = ormsgpack.packb(_fish_payload(text, streaming=False))
    client = _get_shared_client()
    resp = await client.post(
        url, content=body,
        headers={"Content-Type": "application/msgpack"},
        timeout=FISH_TTS_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.content


# ── Karakter → ses prosody haritası (Faz 5) ──────────────────────────
# Her karakter aynı dilin taban sesini kullanır; pitch/rate ile ton farklılaşır.
def _parse_offset(val: str, unit: str) -> int:
    """'+5%' / '-10Hz' gibi edge-tts offset string'ini tam sayıya çevirir."""
    try:
        return int(str(val).replace(unit, "").replace("+", "").strip() or "0")
    except (ValueError, AttributeError):
        return 0


# Edge TTS ses adı biçimi: `tr-TR-EmelNeural`. Değer dış servise gidiyor ve
# kullanıcıdan geliyor → biçim doğrulanır, serbest metin kabul edilmez.
GECERLI_SES = re.compile(r"^[a-z]{2,3}-[A-Z]{2}-[A-Za-z]+Neural$")


def kullanici_sesi(persona_key: str) -> str:
    """Kullanıcının bu persona için AÇIKÇA seçtiği Edge sesi (yoksa '').

    🔴 2026-09-18 (FAZ 0, A6): ⚙ AYAR → TTS'teki ses seçici karakter başına bir ses
    çiziyor, seçimi `localStorage['yukiCharVoices']`'e yazıyor ve "✓ kaydedildi"
    toast'ı basıyordu — ama backend'e **hiç istek atmıyordu** ve okuyan hiçbir yer
    yoktu. Yani kullanıcı seçiyor, onay görüyor, hiçbir şey değişmiyordu.
    Artık seçim `config.user.json`'daki `PERSONA_VOICES` haritasından okunur.

    ⚠️ Bu, A7'de kaldırılan persona sabitinin geri gelmesi DEĞİLDİR: orada 5 personaya
    gömülü bir varsayılan dili HER KOŞULDA eziyordu; burada kullanıcının açık tercihi
    var ve seçici "Dil varsayılanı" seçeneğiyle geri alınabiliyor (boş değer).
    """
    try:
        from app import config_manager
        ham = (config_manager.get("PERSONA_VOICES", "") or "").strip()
        if not ham:
            return ""
        secim = (json.loads(ham) or {}).get(persona_key) or ""
        return secim if GECERLI_SES.match(secim) else ""
    except Exception:
        return ""


def _edge_voice_params() -> tuple[str, str, str]:
    """(voice, rate, pitch) — ses KİMLİĞİ dilden/kullanıcı tercihinden, ÜSLUP personadan.

    Öncelik: kullanıcının açık seçimi > aktif dilin varsayılan sesi.
    """
    cfg = get_lang_config()
    voice = cfg["edge_voice"]
    base_rate = _parse_offset(EDGE_VOICE_RATE, "%")
    base_pitch = _parse_offset(EDGE_VOICE_PITCH, "Hz")
    try:
        from app.services.personas import get_persona, get_persona_meta
        meta = get_persona_meta()
        secili = kullanici_sesi(get_persona())
        if secili:
            voice = secili
        rate = base_rate + int(meta.get("edge_rate", 0))
        pitch = base_pitch + int(meta.get("edge_pitch", 0))
    except Exception:
        rate = base_rate
        pitch = base_pitch
    # Makul aralığa sıkıştır
    rate = max(-40, min(60, rate))
    pitch = max(-50, min(50, pitch))
    return voice, f"{rate:+d}%", f"{pitch:+d}Hz"


async def _synthesize_edge(text: str) -> bytes:
    """Edge-TTS native stream() — temp dosya yok, async generator ile doğrudan bytes."""
    voice, rate, pitch = _edge_voice_params()
    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        chunks: list[bytes] = []
        async for item in communicate.stream():
            if item["type"] == "audio":
                chunks.append(item["data"])
        if chunks:
            return b"".join(chunks)
        raise RuntimeError("Edge boş ses döndürdü")
    except Exception as e:
        logger.warning("Edge TTS hatası (%s), Google TTS'e dönülüyor.", e)
        return await _synthesize_google(text, voice)


# ── Edge 403 → Google çeviri TTS (son çare) ──────────────────────────
# 🔴 2026-10-10: Microsoft Edge okuma ucunu/token'ını değiştirdi; edge-tts 7.2.8 her
# istekte `WSServerHandshakeError 403` alıyor (rany2/edge-tts#490, düzeltme yok).
# Anahtarsız kullanıcının TEK ses katmanı Edge olduğu için Yuki tamamen susuyordu.
# Google çeviri sesi resmî API DEĞİL (kapanabilir) ve metin Google'a gider — Edge
# düzelince kod kendiliğinden yine Edge'i kullanır; bu yol yalnız hata anında açılır.
# Tek istek ~200 karakter sınırlı → uzun metin kelime sınırından bölünür.
_GOOGLE_TTS_URL = "https://translate.google.com/translate_tts"
_GOOGLE_PARCA = 180


def _google_parcala(text: str) -> list[str]:
    parcalar, cur = [], ""
    for kelime in text.split():
        while len(kelime) > _GOOGLE_PARCA:
            if cur:
                parcalar.append(cur)
                cur = ""
            parcalar.append(kelime[:_GOOGLE_PARCA])
            kelime = kelime[_GOOGLE_PARCA:]
        if cur and len(cur) + 1 + len(kelime) > _GOOGLE_PARCA:
            parcalar.append(cur)
            cur = kelime
        else:
            cur = f"{cur} {kelime}" if cur else kelime
    if cur:
        parcalar.append(cur)
    return parcalar


async def _synthesize_google(text: str, voice: str = "") -> bytes:
    """Google çeviri TTS (mp3). Dil, kullanılacak Edge sesinden çıkarılır (tr-TR-… → tr, en-US-… → en)."""
    dil = (voice or get_lang_config()["edge_voice"]).split("-")[0]
    out: list[bytes] = []
    for parca in _google_parcala(text):
        r = await _get_shared_client().get(
            _GOOGLE_TTS_URL,
            params={"ie": "UTF-8", "client": "tw-ob", "tl": dil, "q": parca},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=15.0)
        if r.status_code != 200 or not r.content:
            raise RuntimeError(f"Google TTS HTTP {r.status_code}")
        out.append(r.content)
    if not out:
        raise RuntimeError("Google TTS: boş metin")
    return b"".join(out)


def split_sentences(text: str) -> list[str]:
    """Split text into sentences for streaming TTS."""
    parts = re.split(r'(?<=[.!?;:])\s+', text)
    return [s.strip() for s in parts if s.strip()]


async def synthesize_streaming(text: str) -> AsyncGenerator[bytes, None]:
    """TTS audio chunk'larını streaming olarak yield et (ilk chunk → anında ses).

    Fallback zinciri: Fish Speech S2 → ElevenLabs → Edge TTS → Google TTS.
    """
    if not seslendirilebilir_mi(text):
        logger.debug("TTS akışı atlandı — seslendirilebilir metin yok.")
        return

    if USE_FISH_TTS:
        got = False
        try:
            async for chunk in _stream_fish(text):
                got = True
                yield chunk
        except Exception as e:
            # Akış ortasında koptuysa kısmi ses gitti → çift ses olmaması için
            # alt katmana DÜŞME; baştan koptuysa (got=False) sonraki katmana geç.
            if got:
                logger.warning("Fish Speech akış ortasında koptu (%s), kısmi ses ile bitiriliyor.", e)
                return
            logger.warning("Fish Speech streaming hatası (%s), sonraki katmana dönülüyor.", e)
        else:
            if got:
                return
            logger.warning("Fish Speech boş akış döndürdü, sonraki katmana geçiliyor.")

    if _elevenlabs_kullanilabilir():
        got = False
        try:
            async for chunk in _stream_elevenlabs(text):
                got = True
                yield chunk
        except Exception as e:
            if got:
                logger.warning("ElevenLabs akış ortasında koptu (%s), kısmi ses ile bitiriliyor.", e)
                return
            logger.warning("ElevenLabs streaming hatası (%s), sonraki katmana dönülüyor.", e)
        else:
            if got:
                return
            logger.warning("ElevenLabs boş akış döndürdü, sonraki katmana geçiliyor.")

    async for chunk in _stream_edge(text):
        yield chunk


async def _stream_elevenlabs(text: str) -> AsyncGenerator[bytes, None]:
    """ElevenLabs streaming — chunk'ları anında yield et."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY,
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.85,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }
    client = _get_shared_client()
    async with client.stream("POST", url, json=data, headers=headers) as resp:
        await _elevenlabs_durum_dogrula(resp)
        async for chunk in resp.aiter_bytes(chunk_size=4096):
            if chunk:
                yield chunk


async def _stream_fish(text: str) -> AsyncGenerator[bytes, None]:
    """Fish Speech S2 streaming — api_server'dan ses chunk'larını anında yield et.

    `streaming: true` ile sunucu ham ses parçalarını akıtır (TTFA ~100ms).
    """
    import ormsgpack
    url = f"{FISH_TTS_URL.rstrip('/')}/v1/tts"
    body = ormsgpack.packb(_fish_payload(text, streaming=True))
    client = _get_shared_client()
    async with client.stream(
        "POST", url, content=body,
        headers={"Content-Type": "application/msgpack"},
        timeout=FISH_TTS_TIMEOUT,
    ) as resp:
        resp.raise_for_status()
        async for chunk in resp.aiter_bytes(chunk_size=4096):
            if chunk:
                yield chunk


async def _stream_edge(text: str) -> AsyncGenerator[bytes, None]:
    """Edge TTS streaming — chunk'ları anında yield et."""
    voice, rate, pitch = _edge_voice_params()
    got = False
    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        async for item in communicate.stream():
            if item["type"] == "audio":
                got = True
                yield item["data"]
    except Exception as e:
        if got:   # kısmi ses gitti → çift ses olmasın
            logger.warning("Edge akış ortasında koptu (%s), kısmi ses ile bitiriliyor.", e)
            return
        logger.warning("Edge TTS akış hatası (%s), Google TTS'e dönülüyor.", e)
        yield await _synthesize_google(text, voice)
        return
    if not got:
        logger.warning("Edge boş akış döndürdü, Google TTS'e dönülüyor.")
        yield await _synthesize_google(text, voice)

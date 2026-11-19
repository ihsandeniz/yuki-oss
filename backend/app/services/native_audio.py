"""Gemini Native Audio — bidirectional streaming ses konuşması.

Faz α: STT → LLM → TTS pipeline'ını tek Gemini Live API çağrısına indirir.
TTFA: ~2s → ~400ms

Kullanım:
    async with GeminiLiveSession(api_key, model, system_prompt) as sess:
        await sess.send_audio(wav_bytes)
        async for chunk in sess.receive():
            if chunk.audio:
                # 24kHz PCM16 ham ses
                yield chunk.audio
"""

import io
import logging
import wave

import numpy as np

logger = logging.getLogger(__name__)


def _wav_to_pcm16_16k(audio_bytes: bytes) -> bytes:
    """Ses kaydını Gemini'nin beklediği 16 kHz mono PCM16 ham veriye çevirir.

    İstemci (frontend/js/core.js `_nativeSendAudio`) MediaRecorder çıktısını
    (çoğunlukla webm/opus) olduğu gibi yollar, WAV değil. Bu yüzden önce ürünün
    kendi dönüştürücüsü `stt.ensure_wav` (PyAV, pakette var) çağrılır; sonra WAV
    standart `wave` modülüyle okunur. soundfile/librosa ürün bağımlılığı değildir.
    """
    from app.services.stt import ensure_wav

    wav = ensure_wav(audio_bytes)
    if wav[:4] != b"RIFF":
        raise ValueError("ses WAV'a çevrilemedi")  # i18n-istisna: iç hata, websocket_native genel hata mesajına sarar
    with wave.open(io.BytesIO(wav), "rb") as w:
        kanal, genislik, sr = w.getnchannels(), w.getsampwidth(), w.getframerate()
        ham = w.readframes(w.getnframes())

    if genislik == 2:
        data = np.frombuffer(ham, dtype="<i2").astype(np.float32) / 32768.0
    elif genislik == 1:
        data = (np.frombuffer(ham, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif genislik == 4:
        data = np.frombuffer(ham, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"desteklenmeyen örnek genişliği: {genislik}")  # i18n-istisna: iç hata, websocket_native genel hata mesajına sarar

    if kanal > 1:
        data = data[: len(data) - len(data) % kanal].reshape(-1, kanal).mean(axis=1)

    if sr != 16000 and len(data):
        n = max(1, int(round(len(data) * 16000 / sr)))
        data = np.interp(
            np.linspace(0, len(data) - 1, n), np.arange(len(data)), data
        ).astype(np.float32)

    return (data * 32767).clip(-32768, 32767).astype(np.int16).tobytes()


class NativeChunk:
    """Gemini Live API'den gelen tek bir yanıt parçası."""
    __slots__ = ("audio", "text", "turn_complete")

    def __init__(
        self,
        audio: bytes | None = None,
        text: str | None = None,
        turn_complete: bool = False,
    ):
        self.audio = audio
        self.text = text
        self.turn_complete = turn_complete


class GeminiLiveSession:
    """Gemini Live API oturumu — context manager ile kullanılır.

    Örnek::

        async with GeminiLiveSession(api_key, model, system_prompt) as sess:
            await sess.send_audio(wav_bytes)
            async for chunk in sess.receive():
                ...
    """

    def __init__(self, api_key: str, model: str, system_prompt: str, voice: str = "Aoede"):
        self._api_key = api_key
        self._model = model
        self._system_prompt = system_prompt
        self._voice = voice
        self._session = None
        self._client = None
        self._ctx = None

    async def __aenter__(self) -> "GeminiLiveSession":
        from google import genai
        from google.genai import types

        self._client = genai.Client(api_key=self._api_key)

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(
                parts=[types.Part(text=self._system_prompt)]
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self._voice)
                )
            ),
            # Live 3.x yalnız ses döndürür (response.text boş); yazı dökümü bu
            # ayarla server_content.output_transcription'dan gelir.
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )

        self._ctx = self._client.aio.live.connect(model=self._model, config=config)
        self._session = await self._ctx.__aenter__()
        logger.info("Gemini Live oturumu açıldı: model=%s", self._model)
        return self

    async def __aexit__(self, *args):
        if self._ctx is not None:
            try:
                await self._ctx.__aexit__(*args)
            except Exception as e:
                logger.warning("Gemini Live oturum kapanış hatası: %s", e)
        self._ctx = None
        self._session = None
        self._client = None

    async def send_audio(self, wav_bytes: bytes) -> None:
        """WAV formatında ses gönderir (otomatik olarak 16kHz PCM16'ya dönüştürülür)."""
        from google.genai import types

        if self._session is None:
            raise RuntimeError("GeminiLiveSession başlatılmamış — __aenter__ çağırın")  # i18n-istisna: programlama hatası (async with dışı kullanım)

        pcm = _wav_to_pcm16_16k(wav_bytes)
        blob = types.Blob(mime_type="audio/pcm;rate=16000", data=pcm)
        # google-genai 2.x: anahtar kelimeli, çağrı başına TEK argüman.
        await self._session.send_realtime_input(audio=blob)
        # İstemci tek parça kayıt yollayıp susuyor; akış sonu bildirilmezse
        # sunucu tarafı ses algılama (VAD) tamponu işlemeyebilir.
        await self._session.send_realtime_input(audio_stream_end=True)
        logger.debug("Ses gönderildi: %d bytes PCM", len(pcm))

    async def send_text(self, text: str) -> None:
        """Metin mesajı gönderir (text-only mod için)."""
        from google.genai import types

        if self._session is None:
            raise RuntimeError("GeminiLiveSession başlatılmamış — __aenter__ çağırın")  # i18n-istisna: programlama hatası (async with dışı kullanım)

        await self._session.send_client_content(
            turns=[
                types.Content(
                    role="user",
                    parts=[types.Part(text=text)],
                )
            ],
            turn_complete=True,
        )
        logger.debug("Metin gönderildi: %r", text[:80])

    async def receive(self):
        """Gemini'den gelen yanıt parçalarını stream eder.

        Yields:
            NativeChunk — .audio (bytes, 24kHz PCM16) veya .text veya .turn_complete
        """
        if self._session is None:
            raise RuntimeError("GeminiLiveSession başlatılmamış — __aenter__ çağırın")  # i18n-istisna: programlama hatası (async with dışı kullanım)

        # SDK 2.x: AsyncSession async-iterable değil; receive() bir model turunu
        # akıtır ve turn_complete gelince kendiliğinden biter.
        async for response in self._session.receive():
            icerik = response.server_content

            # Ses verisi (bir olayda birden çok parça gelebilir; .data hepsini birleştirir)
            ses = response.data
            if ses:
                yield NativeChunk(audio=ses)

            # Yazı dökümü (output_audio_transcription)
            dokum = getattr(getattr(icerik, "output_transcription", None), "text", None)
            if dokum:
                yield NativeChunk(text=dokum)

            # Tur tamamlandı — alan server_content altında, mesajın kendisinde değil
            if icerik is not None and icerik.turn_complete:
                yield NativeChunk(turn_complete=True)
                return

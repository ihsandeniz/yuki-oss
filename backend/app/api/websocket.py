"""WebSocket endpoint — gerçek zamanlı sesli konuşma + event akışı."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import subprocess
from collections import deque
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

from app.config import ALLOWED_ORIGINS
from app.services.event_bus import bus
from app.services.llm import chat_stream, _parse_tags
from app.services.runner import CancellationToken
from app.services.stt import transcribe, detect_speech, check_wake_word, analyze_voice_emotion, ensure_wav
from app.services.tts import synthesize_streaming, split_sentences
from app.services import dolgu_sesi
from app.services import ses_kimlik
from app.services.tools.approval_gate import onay_bekliyor
from app.services.state_machine import YukiState, get_state_machine
from app.services.emotion_engine import get_emotion_engine
from app.mesajlar import KATALOG, M

router = APIRouter(tags=["websocket"])


def _ogren_onekleri() -> tuple[str, ...]:
    """`/öğren` komutunun tanınan ön ekleri — KATALOGDAN, elle liste DEĞİL.

    🔴 Bu ayrım FAZ 3 · Dalga 2'de (2026-09-20) ölçülerek kondu: komut paleti
    etiketi İngilizce'de `/teach` oluyor, eski elle yazılmış liste yalnız
    Türkçe yazımları tanıyordu. Kullanıcı `/teach kahveyi sade severim` yazsa
    eşleşme tutmaz, cümle düz sohbet olarak modele giderdi — **hata vermeden**:
    kullanıcı öğrettiğini sanır, beceri belleğine hiçbir şey yazılmazdı.
    "Metni arayan kod, metin çevrilebilir olduğu an kırılır."

    ⚠️ HER dilin tokeni kabul edilir, yalnız aktif dilinki değil: kullanıcı
    Türkçe'yken `/öğren`i öğrenip sonra arayüzü İngilizce'ye alabilir, eski
    alışkanlığını cezalandırmanın bir faydası yok. Yanlış pozitif riski de
    yok — tokenler `/` ile başlıyor ve birbirinin ön eki değil.

    Aksansız yazımlar (`/ogren`, `/ögren`) elle korunuyor: Türkçe klavyesi
    olmayan kullanıcı `ğ`yi yazamıyor ve bu tarihî davranış ölçülmeden
    kaldırılmaz. (Eski listede `/ögren` İKİ KEZ vardı — aynı dizge; dört
    sanılan liste gerçekte üç yazım tanıyordu.)
    """
    tokenler = {
        (katalog.get("ui.komut-ogren") or "").lower()
        for katalog in KATALOG.values()
    }
    tokenler.discard("")
    tokenler |= {"/ogren", "/ögren"}  # i18n-istisna: komut önekleri — kullanıcının yazdığı girdiyle eşleşir, gösterilmez
    return tuple(sorted(tokenler))


_OGREN_ONEKLERI = _ogren_onekleri()


async def _ogren_kaydet(fact: str) -> str:
    """'/öğren' bilgisini skill belleğine yazar, kullanıcıya gösterilecek metni döndürür.

    "Öğrendim" yalnız kayıt GERÇEKTEN yazıldıysa denir. Gömme modeli yokken `add()` patlıyor,
    hata günlüğe yutulup yine "Öğrendim" deniyordu — hiçbir şey kaydedilmiyordu. Kapı
    `api/memory.py::_motor_hazir` ile aynı kaynak (`llm._embedding_engine_ready`).
    Bekçi: tests/test_ogren_kapisi.py
    """
    from app.services.llm import _embedding_engine_ready
    if not _embedding_engine_ready():
        return M("ogren.model-yok")
    try:
        from app.services.memory import get_memory_service
        await get_memory_service().add(
            fact, role="user", scope="skill", importance=0.8, emit_kind="taught")
    except Exception as e:  # noqa: BLE001 — sohbet düşmesin, ama "öğrendim" de denmesin
        logger.warning("/öğren kaydı yazılamadı: %s", e)
        return M("ogren.kaydedilemedi")
    return M("ogren.kaydedildi", bilgi=fact)


class ConnectionManager:
    """Aktif WebSocket bağlantılarını yönetir. Scheduler proaktif push için kullanır."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    def connect(self, ws: WebSocket) -> None:
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    async def broadcast(self, message: dict[str, Any]) -> int:
        """Bağlı tüm istemcilere JSON mesajı gönder. Kopuk bağlantılar sessizce atlanır.

        Ulaşılan istemci sayısını döndürür — BİLDİRİM odasının "ekrana ulaştı mı" izi bu sayı.
        """
        dead: list[WebSocket] = []
        ulasan = 0
        for ws in list(self._connections):
            try:
                await ws.send_json(message)
                ulasan += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)
        return ulasan


# Modül seviyesi singleton — scheduler.set_connection_manager() çağrısıyla paylaşılır
_manager = ConnectionManager()


def masaustu_capa_suz(msg: dict[str, Any]) -> dict[str, Any] | None:
    """Masaüstü Yuki çapası: ön yüzün PANEL / giriş çubuğu kutuları (CSS px) → masaüstü süreci.

    Yalnız sayı alanları geçer, yeniden kurulur (istemciden gelen başka alan yayına sızmaz). Bozuksa None.
    Kutu: [x, y, w, h] ya da null. Masaüstü tarafı ayrıca doğrular (masaustu/etkilesim.py capa_dogrula).
    paneller: açık pencere-panellerin kutuları; en çok 12, bozuk olan atlanır.
    """
    def sayi(v: Any, alt: float, ust: float) -> float | None:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not alt <= v <= ust:
            return None
        return round(float(v), 1)

    def kutu(v: Any) -> list[float] | None:
        if not isinstance(v, list) or len(v) != 4:
            return None
        k = [sayi(v[0], -20000, 20000), sayi(v[1], -20000, 20000), sayi(v[2], 0, 20000), sayi(v[3], 0, 20000)]
        return None if any(t is None for t in k) else k

    vw, vh = sayi(msg.get("vw"), 100, 20000), sayi(msg.get("vh"), 100, 20000)
    if vw is None or vh is None:
        return None
    pl = msg.get("paneller")
    paneller = [k for k in (kutu(v) for v in (pl[:12] if isinstance(pl, list) else [])) if k]
    return {"type": "masaustu_capa", "vw": vw, "vh": vh,
            "panel": kutu(msg.get("panel")), "cubuk": kutu(msg.get("cubuk")), "paneller": paneller}


async def duzenleme_penceresi(receive, orijinal: str, bekleyen: deque,
                              sure: float = 1.5, pong=None) -> tuple[str, bool]:
    """Sesli sözden sonraki düzeltme penceresi. (metin, durdur) döner.

    Yalnız `confirm_transcription` pencereye aittir; `cancel` turu hiç başlatmaz
    (durdur=True). Başka her mesaj (ikinci söz, ping, harita sonucu, bağlantı kopması)
    `bekleyen`e eklenir ve ana döngüde sırayla işlenir — yutulmaz. `ping` beklemez:
    `pong` verildiyse pencere içinde cevaplanır (kalp atışı 1,5 sn gecikmesin).
    """
    dongu = asyncio.get_running_loop()
    bitis = dongu.time() + sure
    while (kalan := bitis - dongu.time()) > 0:
        try:
            veri = await asyncio.wait_for(receive(), timeout=kalan)
        except asyncio.TimeoutError:
            break  # düzenleme yok — orijinal metin
        if not (isinstance(veri, dict) and veri.get("text")):
            bekleyen.append(veri)
            if isinstance(veri, dict) and veri.get("type") == "websocket.disconnect":
                break
            continue
        try:
            tip = json.loads(veri["text"]).get("type")
        except (ValueError, TypeError, AttributeError):
            return duzenlemeyi_uygula(veri, orijinal), False  # bozuk → orijinal
        if tip == "cancel":
            return orijinal, True
        if tip == "confirm_transcription":
            return duzenlemeyi_uygula(veri, orijinal), False
        if tip == "ping" and pong is not None:
            await pong()
            continue
        bekleyen.append(veri)
    return orijinal, False


def duzenlemeyi_uygula(edit_data: dict, orijinal: str) -> str:
    """Kullanıcının transkripsiyon düzeltmesini uygula; bozuk mesajda orijinali koru.

    🔴 2026-08-02: burası tüm WebSocket oturumunu düşüren bir çökme üretiyordu.
    `edit_msg.get("text", "")` — anahtar YOKSA `""` döner, ama anahtar VARSA ve
    değeri `null` ise `None` döner: varsayılan devreye GİRMEZ. `None.strip()` →
    `AttributeError: 'NoneType' object has no attribute 'strip'` → handler düşüyor,
    kullanıcı cevap alamadan soket ölüyordu.

    Kural: bozuk TEK bir mesaj tüm oturumu düşürmemeli — orijinal transkripsiyona
    dönülür ve sohbet devam eder.
    """
    try:
        if not (isinstance(edit_data, dict) and edit_data.get("text")):
            return orijinal
        edit_msg = json.loads(edit_data["text"])
        if not isinstance(edit_msg, dict) or edit_msg.get("type") != "confirm_transcription":
            return orijinal
        duzenlenmis = (edit_msg.get("text") or "").strip()
        return duzenlenmis or orijinal
    except (ValueError, TypeError, AttributeError, KeyError) as e:
        logger.warning(
            "Düzenleme mesajı okunamadı (%s) — orijinal transkripsiyon kullanılıyor.", e
        )
        return orijinal


async def _send_tts_streaming(ws: WebSocket, text: str) -> None:
    """TTS audio'yu streaming olarak üret ve chunk'ları anında gönder.

    Her chunk geldiğinde audio_chunk mesajı gönderir.
    Tamamlandığında tam audio'yu da audio mesajı olarak gönderir (geriye uyumluluk).
    """
    chunks: list[bytes] = []
    try:
        async for audio_chunk in synthesize_streaming(text):
            chunks.append(audio_chunk)
            await ws.send_json({
                "type": "audio_chunk",
                "data": base64.b64encode(audio_chunk).decode("ascii"),
            })
    except (WebSocketDisconnect, RuntimeError):
        raise   # bağlantı koptu → dış döngü kapatsın
    except Exception as e:
        # 🔴 2026-10-10 (Edge 403): TTS istisnası buradan dış `except Exception`'a
        # düşüp /ws/realtime bağlantısını İLK CÜMLEDE kapatıyordu — ses kesilince
        # metin akışı da yarıda kalıyordu. Ses üretilemezse metin sürsün, Yuki sussun.
        logger.warning("TTS üretilemedi, bu cümle sessiz geçiyor: %s", e)
        if not chunks:
            return
    # Geriye uyumluluk: tam audio mesajı
    full_audio = b"".join(chunks)
    await ws.send_json({
        "type": "audio",
        "data": base64.b64encode(full_audio).decode("ascii"),
        "text": text,
    })


def _check_ws_origin(ws: WebSocket) -> bool:
    """WebSocket bağlantısının izin verilen origin'den geldiğini doğrular."""
    origin = ws.headers.get("origin", "")
    if not origin:
        # Origin header olmayan bağlantılar (curl, yerel araçlar) kabul edilir — tarayıcı her zaman gönderir;
        # yerel araç ise Electron oturum çerezi olmadan app/yerel_kapi.py'den geçemez.
        return True
    # v0.8.1: kapıyla AYNI kural. Eski `startsWith` "http://127.0.0.1:8000" için
    # "http://127.0.0.1:8000.evil.example"yı da kabul ediyordu (denetim (b)) ve ağa açık kurulumda
    # telefonun aynı kökenli arayüzünü reddediyordu (canlı ölçüm: ?token= ile bile 403).
    from app.yerel_kapi import koken_izinli
    sema = "https" if ws.url.scheme in ("https", "wss") else "http"
    return koken_izinli(origin, ws.headers.get("host", ""), sema, ALLOWED_ORIGINS)


@router.websocket("/ws/realtime")
async def ws_realtime(ws: WebSocket):
    """Gerçek zamanlı konuşma + Live2D event akışı.

    Client → Server:
        binary frame  : ham ses baytları (WAV/WebM)
        text frame    : JSON {"type": "text", "message": "..."}

    Server → Client:
        {"type": "state",        "from": "idle", "to": "listening"}
        {"type": "emotion",      "emotion": "happy", "intensity": 0.8}
        {"type": "live2d",       "params": {"ParamEyeLSmile": 0.9, ...}}
        {"type": "behavior",     "action": "eye_blink", "duration": 0.12}
        {"type": "transcription","text": "..."}
        {"type": "text",         "chunk": "..."}
        {"type": "audio",        "data": "<base64>", "text": "..."}
        {"type": "done"}
    """
    # WP3: WebSocket token doğrulaması — middleware'de ölü kod, el-içi kontrol gerekli
    from app.config import AUTH_TOKEN
    from app.services import api_guard
    import secrets
    _token = ws.query_params.get("token", "")
    if AUTH_TOKEN and not api_guard.ws_gecer(ws, _token, AUTH_TOKEN):
        await ws.close(code=4401, reason="Unauthorized")
        return
    from app.services import ag_ayari
    if not ag_ayari.ws_izinli(ws):
        await ws.close(code=4401, reason="Unauthorized")
        return

    # F5: Origin kontrolü — izin verilmeyen origin'leri reddet (ek katman)
    if not _check_ws_origin(ws):
        await ws.close(code=4003, reason="Origin not allowed")
        return

    await ws.accept()
    _manager.connect(ws)
    dolgu_sesi.isit()   # dolgu açıksa sesi şimdiden hazırla (ilk tur da dolgulu olabilsin)

    sm = get_state_machine()
    ee = get_emotion_engine()
    event_q = bus.subscribe_all()
    active_task: asyncio.Task | None = None
    active_cancel: CancellationToken | None = None

    async def _forward_events():
        """Event bus'tan gelen olayları WebSocket'e ilet."""
        try:
            while True:
                event = await event_q.get()   # bus kaynağı hata verirse aşağıdaki except yakalar (sessiz ölüm yok)
                try:
                    await ws.send_json(event)
                except Exception:
                    break   # WS kapandı → forwarder biter
        except asyncio.CancelledError:
            raise   # finally'deki cancel — normal kapanış
        except Exception as e:
            logger.error("Event forwarder durdu: %s", e)

    forwarder = asyncio.create_task(_forward_events())

    async def _cancel_active():
        """Aktif runner ve task'ı iptal et."""
        nonlocal active_task, active_cancel
        if active_cancel is not None:
            active_cancel.cancel()
            logger.info("Aktif runner iptal edildi.")
        if active_task is not None and not active_task.done():
            active_task.cancel()
            try:
                await active_task
            except (asyncio.CancelledError, Exception):
                pass
            logger.info("Aktif task iptal edildi.")
        active_task = None
        active_cancel = None

    # Düzenleme penceresine düşüp pencereye ait olmayan mesajlar (ikinci söz, ping, ...).
    bekleyen_mesajlar: deque[dict[str, Any]] = deque()

    try:
        while True:
            data = bekleyen_mesajlar.popleft() if bekleyen_mesajlar else await ws.receive()
            if data.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect(data.get("code", 1000))
            user_text = "" # Her döngü başında sıfırla

            # ── Ses girişi ──────────────────────────────────────────── #
            if "bytes" in data and data["bytes"]:
                audio = data["bytes"]
                logger.debug("Ses verisi alındı: %d byte", len(audio))

                # Tek seferlik WAV dönüşümü (ffmpeg) — VAD, STT ve emotion hepsi WAV alır
                audio_wav = ensure_wav(audio)

                # D1/D2: VAD — sessiz ses ise STT'ye gönderme
                if not detect_speech(audio_wav):
                    logger.debug("VAD: Konuşma algılanamadı, atlanıyor.")
                    # 🔴 2026-08-01: burası sessizce `continue` ediyordu. Kullanıcı
                    # konuşuyor, ekranda HİÇBİR ŞEY olmuyordu — geliştiricinin Windows
                    # kurulumundaki "konuşma algılanmıyor" şikâyetinin görünen yüzü
                    # bu üç sessiz çıkıştan biri. Artık hepsi sebebini söylüyor.
                    await _manager.broadcast({
                        "type": "voice_hint",
                        "reason": "no_speech",
                        "text": M("ses.konusma-algilanamadi"),
                    })
                    continue

                # Ses kimliği (SES_KIMLIK, varsayılan kapalı): kayıtlı sesin değilse komut yok
                # sayılır — STT'ye ve dolguya hiç girmez. Kapalı / rıza yok / model yok → None (geçir).
                # Onay bekleyen bir araç varken daha sıkı eşik (ses_kimlik.Sonuc.esik).
                _sk = await asyncio.to_thread(ses_kimlik.dogrula, audio_wav)
                if _sk is not None and not _sk.kabul(onay=onay_bekliyor()):
                    logger.info("Ses kimliği: kayıtlı ses değil (skor=%s), komut yok sayıldı", _sk.skor)
                    await _manager.broadcast({
                        "type": "voice_hint",
                        "reason": "speaker_mismatch",
                        "text": M("ses.kayitli-ses-degil"),
                    })
                    continue

                await sm.transition(YukiState.LISTENING)
                # H3: transcribe + voice emotion analizi paralel çalış
                user_text, voice_emotion = await asyncio.gather(
                    transcribe(audio_wav),
                    asyncio.to_thread(analyze_voice_emotion, audio_wav),
                )
                logger.info("Transkripsiyon: '%s'", user_text)
                # Belirgin duygu varsa Event Bus'a yayınla (intensity yüksekse)
                if voice_emotion["emotion"] != "neutral":
                    await bus.publish("emotion", {
                        "emotion": voice_emotion["emotion"],
                        "intensity": min(1.0, voice_emotion["energy"] * 1.2),
                        "source": "voice",
                    })

                # D3: Wake-word kontrolü (WAKE_WORD_ENABLED=true ise aktif)
                if user_text.strip() and not check_wake_word(user_text):
                    logger.debug("Wake-word yok, atlanıyor.")
                    await _manager.broadcast({
                        "type": "voice_hint",
                        "reason": "no_wake_word",
                        "text": M("ses.uyandirma-yok"),
                    })
                    await sm.force(YukiState.IDLE)
                    continue

                if not user_text.strip():
                    # Ses vardı, VAD geçti, ama transkript boş. En sık sebebi: ses tanıma
                    # motoru bu makinede hiç yüklenememiş (Windows'ta native DLL sorunu) —
                    # `transcribe()` o durumda sessizce "" döner. Sebebi kullanıcıya söyle.
                    from app.services.stt import stt_status
                    _st = stt_status()
                    await _manager.broadcast({
                        "type": "voice_hint",
                        "reason": "empty_transcript",
                        "text": _st.get("reason") or M("stt.metne-cevrilemedi"),
                        "diagnostics": _st,
                    })
                    await sm.force(YukiState.IDLE)
                    continue

                if user_text.strip():
                    await _manager.broadcast({"type": "transcription", "text": user_text})
                    # Kesintisiz ses↔yazı (B6): düzenleme penceresi frontend timer'ıyla hizalı (1.5s).
                    # 🔴 Pencere YALNIZ düzeltme onayını alır: eskiden tek `receive()` gelen her
                    # şeyi düzenleme sanıyordu — pencereye düşen ikinci söz kayboluyor, DURDUR
                    # yutulup tur yine başlıyordu. Pencereye ait olmayan mesaj sıraya girer,
                    # bu tur bitince ana döngüde işlenir.
                    user_text, durdur = await duzenleme_penceresi(
                        ws.receive, user_text, bekleyen_mesajlar,
                        pong=lambda: ws.send_json({"type": "pong"}))
                    if durdur:
                        await _cancel_active()
                        await sm.force(YukiState.IDLE)
                        await ws.send_json({"type": "cancelled"})
                        continue

            # ── Metin girişi ────────────────────────────────────────── #
            elif "text" in data and data["text"]:
                msg = json.loads(data["text"])
                if msg.get("type") == "ping":
                    await ws.send_json({"type": "pong"})
                    continue
                if msg.get("type") == "harita_sonuc":
                    # MAP sekmesinin komut cevabı — bekleyen araca teslim edilir
                    # (services/harita_kopru.py). Sohbet akışına GİRMEZ: `continue`
                    # olmasaydı bu mesaj boş bir kullanıcı turu başlatırdı.
                    from app.services import harita_kopru
                    harita_kopru.sonuc_geldi(msg.get("istek_id", ""),
                                             msg.get("veri") or {})
                    continue
                if msg.get("type") == "masaustu_capa":
                    # Masaüstü Yuki çapası — süzülüp yayınlanır, masaüstü süreci dinler. Sohbet akışına GİRMEZ
                    # (yoksa boş kullanıcı turu açılırdı).
                    temiz = masaustu_capa_suz(msg)
                    if temiz:
                        await _manager.broadcast(temiz)
                    continue
                if msg.get("type") == "cancel":
                    await _cancel_active()
                    await sm.force(YukiState.IDLE)
                    await ws.send_json({"type": "cancelled"})
                    continue
                await sm.transition(YukiState.LISTENING)
                user_text = msg.get("message", "")
            else:
                continue

            if not user_text.strip():
                logger.debug("Boş metin, IDLE moduna dönülüyor.")
                await sm.force(YukiState.IDLE)
                continue

            # ── D — '/öğren <şey>' → skill belleğe yaz + 'öğretildi' kartı (LLM atlanır) ──
            # Arayüz her mesaja sekme bloğu ekler; kesilmezse blok "öğrenilen bilgi"nin
            # parçası olup kullanıcıya geri okunuyordu (2026-09-27)
            from app.services.memory import sekme_baglamini_ayikla
            _ut = sekme_baglamini_ayikla(user_text).strip()
            if _ut.lower().startswith(_OGREN_ONEKLERI):
                fact = _ut.split(" ", 1)[1].strip() if " " in _ut else ""
                if fact:
                    await _manager.broadcast({"type": "text", "chunk": await _ogren_kaydet(fact)})
                else:
                    await _manager.broadcast({"type": "text",
                                              "chunk": M("ogren.ne-ogreneyim")})
                await _manager.broadcast({"type": "done"})
                await sm.force(YukiState.IDLE)
                continue

            # ── Önceki aktif çalışmayı iptal et ────────────────────── #
            await _cancel_active()

            # ── LLM + TTS pipeline ──────────────────────────────────── #
            await sm.transition(YukiState.THINKING)

            cancel_token = CancellationToken()
            active_cancel = cancel_token

            buffer = ""
            first_chunk = True

            # Dolgu sesi (varsayılan kapalı): ilk ses gecikirse bir kez "hmm" — blok bitince söner.
            async with dolgu_sesi.tur(ws):
                async for chunk in chat_stream(user_text, cancel_token=cancel_token):
                    if cancel_token.is_cancelled:
                        break

                    if first_chunk:
                        await sm.transition(YukiState.TALKING)
                        first_chunk = False

                    if not chunk:
                        continue
                    buffer += chunk
                    await _manager.broadcast({"type": "text", "chunk": chunk})

                    # Cümle tamamlandığında TTS
                    sentences = split_sentences(buffer)
                    if len(sentences) > 1:
                        for sent in sentences[:-1]:
                            clean, emotion_tag, behavior = _parse_tags(sent)
                            if clean:
                                await _send_tts_streaming(ws, clean)
                            if emotion_tag.emotion != "neutral":
                                await ee.update(emotion_tag.emotion, emotion_tag.intensity)
                            if behavior and behavior != "idle":
                                await _manager.broadcast({"type": "behavior", "action": behavior})
                        buffer = sentences[-1]
                    elif len(buffer.split()) >= 15:
                        # Cümle bitmedi ama buffer yeterince büyüdü — şimdi gönder
                        clean, emotion_tag, behavior = _parse_tags(buffer)
                        if clean:
                            await _send_tts_streaming(ws, clean)
                        if emotion_tag.emotion != "neutral":
                            await ee.update(emotion_tag.emotion, emotion_tag.intensity)
                        if behavior and behavior != "idle":
                            await ws.send_json({"type": "behavior", "action": behavior})
                        buffer = ""

                # Son buffer (iptal edilmediyse)
                if not cancel_token.is_cancelled and buffer.strip():
                    clean, emotion_tag, behavior = _parse_tags(buffer)
                    if clean:
                        await _send_tts_streaming(ws, clean)
                    if emotion_tag.emotion != "neutral":
                        await ee.update(emotion_tag.emotion, emotion_tag.intensity)
                    if behavior and behavior != "idle":
                        await ws.send_json({"type": "behavior", "action": behavior})

            active_cancel = None
            await sm.force(YukiState.IDLE)
            await _manager.broadcast({"type": "done"})

    except (WebSocketDisconnect, RuntimeError):
        logger.info("Client bağlantısı kesildi.")
    except Exception as e:
        logger.error("Beklenmedik hata: %s", e)
    finally:
        _manager.disconnect(ws)
        forwarder.cancel()
        try:
            await forwarder   # cancel'ı bekle → "Task exception was never retrieved" uyarısı olmasın
        except (asyncio.CancelledError, Exception):
            pass
        bus.unsubscribe_all(event_q)
        logger.info("Kaynaklar temizlendi.")


# ── Screen Stream WebSocket ─────────────────────────────────────────── #
_screen_next_id: int = 0


def _get_wayland_outputs() -> list[dict]:
    """Bağlı monitörleri listeler. hyprctl kullanır."""
    from app.services.tools._base import _build_wayland_env
    import json as _json
    env = _build_wayland_env()
    try:
        result = subprocess.run(
            ["hyprctl", "monitors", "-j"],
            capture_output=True, text=True, timeout=3, env=env,
        )
        if result.returncode == 0:
            monitors = _json.loads(result.stdout)
            return [
                {"name": m["name"], "label": f"{m['name']} ({m['width']}×{m['height']})"}
                for m in monitors
            ]
    except Exception:
        pass
    return []


@router.get("/api/screen/outputs")
async def get_screen_outputs() -> JSONResponse:
    """Bağlı monitörlerin listesini döner."""
    outputs = await asyncio.to_thread(_get_wayland_outputs)
    return JSONResponse({"outputs": outputs})


async def _capture_frame(output: str | None, env: dict) -> bytes | None:
    """Belirtilen output'tan (veya tümünden) JPEG frame yakalar."""
    try:
        from PIL import Image
        _PIL_OK = True
    except ImportError:
        _PIL_OK = False

    cmd = ["grim", "-t", "jpeg", "-q", "85"]
    if output:
        cmd += ["-o", output]
    cmd.append("-")

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    raw, err = await asyncio.to_thread(proc.communicate)

    if proc.returncode != 0:
        logger.warning("grim error (output=%s): %s", output, err.decode()[:80])
        return None

    if _PIL_OK:
        try:
            img = Image.open(io.BytesIO(raw))
            if img.width > 1280:
                h = int(img.height * 1280 / img.width)
                img = img.resize((1280, h), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return buf.getvalue()
        except Exception:
            pass
    return raw


@router.websocket("/ws/screen")
async def websocket_screen(
    ws: WebSocket,
    output: str | None = Query(default=None, description="Monitor output adı (ör. DP-1). Boşsa tüm ekran."),  # i18n-istisna: OpenAPI açıklaması, geliştirici belgesi
) -> None:
    """Binary JPEG frame stream — ~1fps canlı ekran paylaşımı.

    Query param `output` ile belirli bir monitör seçilebilir.
    Örnek: /ws/screen?output=DP-1
    """
    # WP3: WebSocket token doğrulaması — middleware'de ölü kod, el-içi kontrol gerekli
    from app.config import AUTH_TOKEN
    from app.services import api_guard
    import secrets
    _token = ws.query_params.get("token", "")
    if AUTH_TOKEN and not api_guard.ws_gecer(ws, _token, AUTH_TOKEN):
        await ws.close(code=4401, reason="Unauthorized")
        return
    from app.services import ag_ayari
    if not ag_ayari.ws_izinli(ws):
        await ws.close(code=4401, reason="Unauthorized")
        return

    global _screen_next_id
    from app.services.tools import _build_wayland_env

    await ws.accept()
    client_id = _screen_next_id
    _screen_next_id += 1
    env = _build_wayland_env()

    logger.info("Screen client #%d bağlandı (output=%s)", client_id, output or "all")

    try:
        while True:
            frame = await _capture_frame(output, env)
            if frame:
                await ws.send_bytes(frame)
            await asyncio.sleep(1.0)
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception as e:
        logger.error("Screen WS #%d hata: %s", client_id, e)
    finally:
        logger.info("Screen client #%d ayrıldı.", client_id)

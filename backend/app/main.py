"""Yuki — FastAPI backend entry point."""

import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from app.hata_yaniti import beklenmeyen_hata_yaniti, hiz_siniri_yaniti

from app.api import chat, voice, websocket
from app.api import memory as memory_api
from app.api import vision as vision_api
from app.api import tools_api
from app.api import media as media_api
from app.api import push as push_api
from app.api import monitor as monitor_api
from app.api import devices_api  # cihaz yönetimi (Ultra; kapı router'da + WS el-içi)
from app.api import map as map_api  # Dalga 3 kalanı — MAP panosu (Pro)
from app.api import live_portrait as lp_api
from app.api import motor_api  # zarif kapanış ucu (Windows'ta sinyal yok)
from app.api import fitness as fitness_api
from app.api import planner as planner_api
from app.api import yedekleme as yedekleme_api  #  FAZ 4 — Drive yedekleme (Pro kapısı router'da)
from app.api import yedek_rclone_api  # Yedek › BULUTTA/AYARLAR/Kontrol/Kuru (rclone, salt okur)
from app.api import todo as todo_api
from app.api import ajan_api  # AJAN sekmesi (yalnız izleyici)
from app.api import llm_config_api
from app.api import language_api
from app.api import character_api
from app.api import face_api             # Yüz tanıma (Free) + canlılık kapılı yüzle giriş
from app.api import lock_api             # Uygulama kilidi — açılış parolası (Ayarlar → Güvenlik)
from app.api import pydeps_api           # indirilen Python kütüphanesini devreye alma
from app.api import duvar_api            # sekme bazlı duvar kâğıdı (kademesiz)
from app.api import yetki_api             # Yetki özeti (kademe yok; geliştirici araçları ayarı)
from app.api import galeri_api            # PC medya gezgini (salt okunur, Range'li)
from app.api import dosya_api             # PC dosya gezgini (salt okunur, terminalsiz)
from app.api import gorev as gorev_api    # Atölye: görev servisi uçları
from app.api import gorus_api            # Kamera görüşü (GORUS, varsayılan kapalı) + /ws/gorus
from app.api import ses_kimlik_api       # Ses kimliği (SES_KIMLIK, varsayılan kapalı)
from app.api import guvenli_dosya_api    # Dosya/galeri güvenli işlemler (kendi ayarı, varsayılan kapalı)
from app.api import chatgpt_api          # ChatGPT ile resmî giriş
from app.api import saglik_api            # Sağlık ölçeri (kayıtlı sensör skoru)
from app.api import self_check_api        # Kurulum sihirbazı + hata günlüğü (2026-08-01)
from app.api import settings_api          # HQ Ayarlar paneli
from app.api import modes_api             # HQ Mod Yöneticisi (CRUD)
from app.api import tts_api               # Faz 19 — TTS durum + test + referans yükleme
from app.config import MEMORY_ENABLED, MEMORY_BACKEND, EYE_TRACKING_ENABLED, EYE_TRACKING_CAMERA, EYE_TRACKING_FPS, AMBIENT_ENABLED, DBUS_ENABLED, ALLOWED_ORIGINS, AUTH_TOKEN, GEMINI_NATIVE_AUDIO
from app.db.connection import close_pool, init_db
from app.limiter import limiter
from app.logging_config import setup_logging
from app.services.behavior import get_behavior_layer
from app.services.state_machine import get_state_machine
from app.mesajlar import M

FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"

# ── Delta güncelleme: katmanlı frontend ─────────────────────────────────────
# Güncelleme kod yükü (~1,2 MiB) `frontend/assets`'i TAŞIMAZ — orası 33 MB medya.
# Overlay'den çalışırken `FRONTEND_DIR` overlay'i gösterir ve orada `assets/`
# yoktur; bu yüzden statik sunum KATMANLI olmalı. Katman sırası:
#
#   ① overlay            → güncel js/css/html          (YUKI_APP_OVERLAY yolu)
#   ② medya katmanı      → güncellenmiş görsel/klip     (YUKI_MEDIA_DIR)
#   ③ paketlenmiş dizin  → her şeyin fabrika hâli
#
# ② 2026-08-08'de eklendi: medyanın kendi yükü var artık (bkz. update_payload.py).
# O katman **sürümsüzdür** — overlay her güncellemede yenilenir, medya yerinde
# kalır. Sıra önemli: medya ②'de, ③'ten ÖNCE aranmalı, yoksa indirilmiş yeni
# görselin üstünü paketin fabrika görseli örterdi.
#
# Değişkenlerin ikisi de yalnız Electron tarafından verilir; düz (paketlenmiş ya
# da geliştirme) çalışmada boşturlar ve davranış hiç değişmez.
_FRONTEND_FALLBACK = os.getenv("YUKI_FRONTEND_FALLBACK") or ""
FRONTEND_FALLBACK_DIR = Path(_FRONTEND_FALLBACK) if _FRONTEND_FALLBACK else None

_MEDIA_DIR = os.getenv("YUKI_MEDIA_DIR") or ""
MEDIA_DIR = Path(_MEDIA_DIR) if _MEDIA_DIR else None

# Arama zinciri — `FRONTEND_DIR` (birincil) hariç, sırayla denenecek yedekler.
# ⚠️ MEDIA_DIR buraya GİRMEZ; o birincilin ÖNÜNDE aranır (`oncelikliler`).
# Sebep lookup_path'te yazılı: overlay yokken birincil dizin paketin kendisidir.
FRONTEND_YEDEKLER: list[Path] = [p for p in (FRONTEND_FALLBACK_DIR,) if p]
FRONTEND_ONCELIKLILER: list[Path] = [p for p in (MEDIA_DIR,) if p]


def frontend_dosyasi(rel: str) -> Path:
    """Bir frontend dosyasının gerçek yolu — medya → overlay → paket.

    Medya ÖNCE sorulur (KatmanliStatik.lookup_path ile aynı gerekçe): overlay
    yokken birincil dizin paketin kendisidir ve dosya orada da bulunur, sonra
    medyaya hiç bakılmazdı. Medya katmanı yalnız güncellenmiş dosyaları taşır.

    Katman yoksa davranış eskisiyle birebir aynı (tek dizin).
    """
    if MEDIA_DIR is not None:
        medya = MEDIA_DIR / rel
        if medya.exists():
            return medya
    birincil = FRONTEND_DIR / rel
    if birincil.exists():
        return birincil
    for yedek_kok in FRONTEND_YEDEKLER:
        yedek = yedek_kok / rel
        if yedek.exists():
            return yedek
    return birincil


class KatmanliStatik(StaticFiles):
    """Dosyayı önce kendi dizininde arar, bulamazsa yedek köklere sırayla düşer.

    Starlette `StaticFiles` birden çok dizini destekleyen bir API sunmuyor;
    `lookup_path` tek genişletme noktası. Yol güvenliği üst sınıfta kalır — burada
    yalnız "bulamadıysan öbür köklere de bak" ekleniyor.

    `fallback` (tekil) geriye dönük uyumluluk için korundu; `fallbacks` (çoğul)
    2026-08-08'de medya katmanı için eklendi. Tek eleman veren eski çağrılar
    birebir aynı davranır.
    """

    def __init__(self, *args, fallback: Path | None = None,
                 fallbacks: list[Path] | None = None,
                 oncelikliler: list[Path] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        koklar = list(fallbacks or [])
        if fallback:
            koklar.append(fallback)
        # Aynı kök iki kez verilirse boşuna ikinci kez aranmasın (sıra korunur).
        self._fallbacks: list[Path] = list(dict.fromkeys(koklar))
        self._oncelikliler: list[Path] = list(dict.fromkeys(oncelikliler or []))
        # Sunucular bir kez kurulur — her istekte StaticFiles yaratmak gereksiz
        # nesne + dizin doğrulaması demekti.
        self._on_sunucular = [StaticFiles(directory=str(p)) for p in self._oncelikliler
                              if p.is_dir()]
        self._yedek_sunucular = [StaticFiles(directory=str(p)) for p in self._fallbacks
                                 if p.is_dir()]

    def lookup_path(self, path: str):
        # ── öncelikli kökler: BİRİNCİLDEN ÖNCE ──────────────────────────────
        # 🔴 2026-08-08, canlı turda bulundu (birim testler yeşilken!):
        # medya katmanı yalnız *yedek* olarak verilmişti. Overlay yokken `/ui`'nin
        # birincil dizini paketin kendisidir ve aranan görsel orada DA vardır →
        # birincil bulur, medyaya hiç bakılmaz. Sonuç: kullanıcı 33 MB'ı indirir,
        # ekranda fabrika görselini görmeye devam eder — sessiz, tam da bu
        # katmanın önlemek için var olduğu hata.
        # Medya katmanı yalnızca GÜNCELLENMİŞ dosyaları taşır; içinde ne varsa
        # tanım gereği en yenisidir, dolayısıyla önce sorulmalıdır.
        for on in self._on_sunucular:
            o_full, o_stat = on.lookup_path(path)
            if o_stat is not None:
                return o_full, o_stat

        full, stat_result = super().lookup_path(path)
        if stat_result is not None:
            return full, stat_result
        for yedek in self._yedek_sunucular:
            y_full, y_stat = yedek.lookup_path(path)
            if y_stat is not None:
                return y_full, y_stat
        return full, stat_result


async def _monitor_ornek_al(aralik_sn: float) -> None:
    """Tek geçmiş örneği: anlık görüntü → monitor_samples + gün bazında süreç toplamı."""
    import asyncio as _asyncio
    import datetime as _dt
    from app.services.monitoring import history as _mon_hist
    from app.services.monitoring.collector import monitor as _monitor

    snap = await _asyncio.to_thread(_monitor.snapshot, include_processes=True, proc_limit=50)
    await _mon_hist.write_sample(snap)
    await _mon_hist.upsert_process_daily(snap.get("processes", []), aralik_sn,
                                         _dt.date.today().isoformat())


async def _monitor_ornekleyici_baslat(app: FastAPI) -> None:
    import asyncio as _asyncio
    from app.config import MONITOR_ENABLED, MONITOR_COLD_INTERVAL
    if not MONITOR_ENABLED:
        return
    try:
        from app.services.monitoring import history as _mon_hist
        from app.services.monitoring.collector import monitor as _monitor
        await _mon_hist.init_db()
        await _asyncio.to_thread(_monitor.prime)   # ilk CPU/ağ farkı için taban
    except Exception as e:  # noqa: BLE001
        logger.error("Sistem izleme geçmişi açılamadı: %s", e)
        return

    async def _dongu():
        while True:
            try:
                await _asyncio.sleep(MONITOR_COLD_INTERVAL)
                await _monitor_ornek_al(MONITOR_COLD_INTERVAL)
            except _asyncio.CancelledError:
                break
            except Exception as _e:  # noqa: BLE001
                logger.warning("izleme örnekleyici: %s", _e)

    app.state.monitor_task = _asyncio.create_task(_dongu())
    logger.info("Sistem izleme geçmişi aktif (örnek %ss)", MONITOR_COLD_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio as _asyncio
    import time as _time

    # Logging yapılandırması
    setup_logging()

    # Hata günlüğü — WARNING+ her kayıt kullanıcının görebileceği dosyaya da düşer.
    # 2026-08-01 dersi: "konuşma algılanmıyor" ve `401 Missing Authentication header`
    # şikâyetleri geldiğinde elimizde HİÇBİR kayıt yoktu.
    try:
        from app.services import error_log
        error_log.kur()
    except Exception as e:
        logger.warning("Hata günlüğü kurulamadı: %s", e)

    # Startup validation (D4)
    from app.services.startup_validator import validate_startup
    warnings = validate_startup()
    for w in warnings:
        logger.warning("Startup: %s", w)

    # Uptime sayacı (D3 health check için)
    app.state.start_time = _time.monotonic()

    # Başlangıç
    get_state_machine()
    get_behavior_layer().start()

    # STT modelini ARKA PLANDA ısıt — startup'ı BLOKE ETME.
    # Senkron `get_stt()` model yüklemesi birkaç saniye sürer (462MB int8) ve health-check'i
    # geciktirip Electron'un "backend başlamadı" timeout'unu tetikliyordu. Ayrıca STT opsiyoneldir:
    # native DLL/model yüklenemezse (bkz. stt.py) None döner, sesle-yazma kapanır, chat + TTS sürer.
    async def _warm_stt_task():
        try:
            from app.services.stt import _get_model as get_stt
            loaded = await _asyncio.get_running_loop().run_in_executor(None, get_stt)
            logger.info("STT pre-warm OK" if loaded is not None else "STT pre-warm atlandı (model/DLL yok)")
        except Exception as e:
            logger.warning("STT pre-warm beklenmedik hata: %s", e)
    _asyncio.create_task(_warm_stt_task())

    # Embedding modeli pre-warm (semantik arama için — cold start 5-6s azalt).
    # Aktif motoru memory.py seçer: ONNX (paketli ürün, torch yok) | sentence-transformers.
    if MEMORY_ENABLED:
        async def _warm_embedding_task():
            try:
                from app.services.memory import warm_embedding
                engine = await warm_embedding()
                logger.info("Embedding model pre-warm OK (%s)", engine)
            except Exception as e:
                logger.warning("Embedding pre-warm başarısız: %s", e)
                return
            # Eski sürümlerin hafızaya yanlış yazdıklarını bir kez düzelt — iki arka uçta da
            # (kullanıcı = sqlite, geliştirme/SaaS = pgvector). Motor ısınmadan koşmaz: blok
            # kesilen satırın vektörü yeniden hesaplanır. Düzeltilecek satır yoksa hiçbir şey
            # yazmaz → her açılışta güvenle çağrılır. Yarıda hata → işlem geri alınır.
            try:
                from app.services.memory import get_memory_service
                sonuc = await get_memory_service().sekme_baglami_temizle()
                if sonuc:
                    logger.info("Hafıza temizliği (sekme bloğu / kapsam): %s", sonuc)
            except Exception as e:
                logger.warning("Hafıza temizliği başarısız (veri değişmedi): %s", e)
        _asyncio.create_task(_warm_embedding_task())

    # TTS pre-warm (D5: timeout + hata izleme)
    from app.services.tts import synthesize as _tts_synthesize

    async def _tts_prewarm():
        try:
            await _asyncio.wait_for(_tts_synthesize("Merhaba"), timeout=10.0)
            logger.info("TTS pre-warm OK")
        except Exception as e:
            logger.warning("TTS pre-warm başarısız: %s", e)

    _asyncio.create_task(_tts_prewarm())

    # DB init (D5: bağımsız hata izolasyonu)
    # init_db() PGVECTOR içindir. sqlite-vec backend'inde depo ilk kullanımda
    # kendini kurar → burada Postgres'e bağlanmaya çalışmak, hafıza ÇALIŞIRKEN
    # "DB init başarısız — hafıza devre dışı" diye yanıltıcı hata basıyordu.
    if MEMORY_ENABLED and MEMORY_BACKEND != "sqlite":
        try:
            await init_db()
        except Exception as e:
            logger.error("pgvector bağlantısı kurulamadı: %s — semantik hafıza devre dışı "
                         "(gömülü hafıza için .env'de MEMORY_BACKEND=sqlite)", e)
    try:
        await todo_api.init_todo_db()
        logger.info("Todo DB init OK")
    except Exception as e:
        logger.error("Todo DB init başarısız: %s", e)
    try:
        await push_api.init_push_db()
        logger.info("Push DB init OK")
    except Exception as e:
        logger.error("Push DB init başarısız: %s", e)
    try:
        # Postgres varsa şema kurulur, yoksa gömülü depo (fitness_store.json).
        # Dönüş False = Postgres yok; bu bir hata DEĞİL, satılan paketin normali.
        from app import config as _cfg_fit
        if _cfg_fit.FITNES:        # kapalıyken (varsayılan) kurulmaz; HQ anahtarı açınca settings_api kurar
            pg = await fitness_api.init_fitness_db()
            logger.info("Fitness DB init OK (%s)", "PostgreSQL" if pg else "gömülü depo")
    except Exception as e:
        logger.error("Fitness DB init başarısız: %s", e)

    # Göz takibi (D5: bağımsız hata izolasyonu)
    if EYE_TRACKING_ENABLED:
        try:
            from app.services.eye_tracker import EyeTracker
            eye_tracker = EyeTracker(EYE_TRACKING_CAMERA, EYE_TRACKING_FPS)
            await eye_tracker.start()
        except Exception as e:
            logger.error("EyeTracker init başarısız: %s", e)

    # Ambient Intelligence (D5: bağımsız hata izolasyonu)
    if AMBIENT_ENABLED:
        try:
            from app.services.ambient import AmbientWatcher
            await AmbientWatcher().start()
        except Exception as e:
            logger.error("AmbientWatcher init başarısız: %s", e)

    # Faz 2 — Proaktif Scheduler
    try:
        from app.services import scheduler as _scheduler_mod
        from app.api.websocket import _manager as _ws_manager
        _scheduler_mod.set_connection_manager(_ws_manager)
        _scheduler_mod.startup()
    except Exception as e:
        logger.error("Scheduler init başarısız: %s", e)

    # Faz ε — D-Bus Watcher (sleep/wake + network events)
    if DBUS_ENABLED:
        try:
            from app.services import dbus_watcher as _dbus
            from app.api.websocket import _manager as _ws_manager
            await _dbus.start(cm=_ws_manager)
        except Exception as e:
            logger.error("D-Bus watcher init başarısız: %s", e)

    # Faz L — Yüz Tanıma Greeting Subscriber
    async def _face_greeting_worker():
        """face_recognized event'ını dinle → Yuki selamlasın."""
        import asyncio as _asyncio
        import base64 as _base64
        from app.services.event_bus import bus as _bus
        from app.services.tts import synthesize_streaming as _tts_stream
        from app.api.websocket import _manager as _ws_mgr

        q = _bus.subscribe("face_recognized")
        try:
            while True:
                event = await q.get()
                name = event.get("name")
                if not name:
                    continue
                greeting = M("bildirim.tanidim", ad=name)
                await _ws_mgr.broadcast({"type": "state_info", "text": greeting})
                try:
                    chunks: list[bytes] = []
                    async for chunk in _tts_stream(greeting):
                        chunks.append(chunk)
                        await _ws_mgr.broadcast({
                            "type": "audio_chunk",
                            "data": _base64.b64encode(chunk).decode("ascii"),
                        })
                    full = b"".join(chunks)
                    await _ws_mgr.broadcast({
                        "type": "audio",
                        "data": _base64.b64encode(full).decode("ascii"),
                        "text": greeting,
                    })
                except Exception as _tts_err:
                    logger.warning("Face greeting TTS hatası: %s", _tts_err)
        except _asyncio.CancelledError:
            _bus.unsubscribe("face_recognized", q)

    _asyncio.create_task(_face_greeting_worker())

    # Faz L2 — Tool Approval Worker KALDIRILDI (2026-10-04 ölçümü).
    # `tool_approval` zaten `_ALL_TOPICS`'te: her /ws/realtime bağlantısı onu
    # `subscribe_all` ile alıp iletiyor. Bu işçi AYNI olayı ikinci kez (ve `sunum`
    # alanı OLMADAN) yayınlıyordu → istemcide iki onay kutusu açılıyordu: biri insan
    # dilinde, biri ham JSON'lu "Araç Onayı Gerekli". Ayrıca kalıcı bir abone olduğu
    # için `bus.abone_var("tool_approval")` HER ZAMAN True dönüyordu → "onay
    # penceresini gören yok, bekleme" kapısı (orchestrator._maliyet_onayi)
    # hiç çalışmıyor, arka plan rutini 30 sn kilitlenip düşüyordu.
    # Bekçi: tests/test_ajan_sekmesi.py::test_onay_olayi_TEK_kanaldan

    # Faz 23 — MCP client köprüsü (mcp_servers.json'da etkin sunucular; boot-güvenli)
    try:
        from app.services import mcp_client as _mcp
        await _mcp.startup_from_config()
    except Exception as e:
        logger.error("MCP client startup başarısız: %s", e)

    # Faz 24 — Skill/plugin kaydı (skills/*.yaml → bileşik araç; boot-güvenli)
    try:
        from app.services import skill_registry as _skreg
        await _skreg.startup()
    except Exception as e:
        logger.error("Skill kaydı başarısız: %s", e)

    # Faz 25 — Rutinler (routines.json → APScheduler; restart-güvenli)
    try:
        from app.services import routines as _routines
        _routines.register_all()
    except Exception as e:
        logger.error("Routines register başarısız: %s", e)

    # Oto-başlatma modları (autostart=true olan enabled modlar)
    async def _run_autostart_modes():
        try:
            await _asyncio.sleep(3)  # diğer servisler ayağa kalksın
            from app.services.tools.modes import list_modes_struct, start_mode
            modes = list_modes_struct()
            for m in modes:
                if m.get("autostart") and m.get("enabled", True):
                    logger.info("Autostart modu çalıştırılıyor: %s", m.get("id"))
                    try:
                        await start_mode(m["id"])
                    except Exception as _me:
                        logger.warning("Autostart mod hatası [%s]: %s", m.get("id"), _me)
        except Exception as _ae:
            logger.error("Autostart başarısız: %s", _ae)

    _asyncio.create_task(_run_autostart_modes())

    # Bilgisayarım paneli — GEÇMİŞ grafiği + GÜN ÖZETİ bu döngünün yazdığını okur.
    # 🔴 2026-09-27: Dalga 3 taşımasında (09-10) bu döngü DÜŞMÜŞTÜ — okuyan uçlar
    # vardı, yazan yoktu; monitor.db 0 bayt kaldı, kullanıcı hep "veri birikiyor…" gördü.
    # Bekçi: tests/test_monitor_ornekleyici.py
    await _monitor_ornekleyici_baslat(app)

    # Masaüstü Yuki: ayar açıksa backend açılınca masaüstü de gelir (varsayılan kapalı)
    from app import config as _cfg_masa
    if getattr(_cfg_masa, "MASAUSTU_YUKI", False):
        from app.services import masaustu_yuki as _masaustu
        app.state.masaustu_task = _asyncio.create_task(_masaustu.acilista())

    yield
    # Kapanış
    try:   # bu backend'in açtığı masaüstü Yuki'yi kapat — ayar değişmez, sonraki açılışta yine gelir
        from app.services import masaustu_yuki as _masaustu
        await _masaustu.kapanista()
    except Exception:
        pass
    _mt = getattr(app.state, "monitor_task", None)
    if _mt:
        _mt.cancel()
    get_behavior_layer().stop()
    try:
        from app.services import dbus_watcher as _dbus
        await _dbus.stop()
    except Exception:
        pass
    try:
        from app.services import scheduler as _scheduler_mod
        _scheduler_mod.shutdown()
    except Exception:
        pass
    try:
        from app.services import mcp_client as _mcp
        await _mcp.shutdown()
    except Exception:
        pass
    await close_pool()


app = FastAPI(
    title="Yuki",
    description="Animasyonlu kisisel AI asistan backend",
    version="0.6.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
# Kullanıcıya ham teknik metin gösterilmez → app/hata_yaniti.py (2026-08-04).
# 429: "çok sık denedin" (slowapi'nin İngilizce "Rate limit exceeded" metni DEĞİL —
#      frontend onu geçersiz anahtar sanıyordu). 500: düz metin yerine JSON.
app.add_exception_handler(RateLimitExceeded, hiz_siniri_yaniti)
app.add_exception_handler(Exception, beklenmeyen_hata_yaniti)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET","POST","PUT","DELETE","OPTIONS"],
    allow_headers=["Authorization","Content-Type"],
)


# ── Auth Middleware ──────────────────────────────────────────────────── #
# İKİ ayrı kapı, TEK middleware:
#   1. AUTH_TOKEN  — .env'de duran, UZAKTAN erişim (tünel) parolası.
#   2. Uygulama kilidi — kullanıcının Ayarlar → Güvenlik'ten kurduğu, AYNI
#      MAKİNEDEKİ başka kişiye karşı açılış parolası (`services/app_lock.py`).
# İkisi de kapalıysa middleware tamamen devre dışı (yalın localhost kullanımı).
#
# 🔑 Neden tek middleware: istemcinin gönderebileceği TEK `Authorization`
# başlığı var. İki ayrı katman olsaydı, ikisi birden kuruluyken istemci hangi
# token'ı göndereceğini bilemez, biri daima 401 verirdi. Burada token bir kez
# okunur ve İKİSİNDEN BİRİNE uyması yeterlidir.
_SKIP_PATHS = {
    "/", "/health", "/ui", "/assets", "/sw.js", "/ui/sw.js",
    # ── Yüzle giriş ────────────────────────────────────────────
    # Bunlar token ISTEYEMEZ: kullanıcı henüz oturum açmamıştır, zaten token
    # almak için çağırıyor. Üçü de tek tek düşünüldü:
    #   login-status → yalnız "kayıt var mı" + kilit durumu. Sahip ADINI DÖNMEZ
    #                  (o bilgi /api/face/status'ta, token arkasında).
    #   challenge    → tek kullanımlık canlılık meydan okuması; kilitliyken 429.
    #   verify       → asıl giriş. Kendi deneme kilidi + rate limit + canlılık.
    # ⚠️ `_SKIP_PATHS` TAM eşleşmedir (`in`), önek değil — `_SKIP_PREFIXES`'e
    #    konsalardı `/api/face/verify-xyz` gibi bir yol da açılırdı.
    "/api/face/login-status",
    "/api/face/liveness/challenge",
    "/api/face/verify",
    #   frames       → `verify`'ın kare dizisinin ERKEN gönderilen dilimleri
    #                  (2026-09-10). Aynı akışın parçası, aynı gerekçe: kilit
    #                  ekranı henüz token'sız. Kendi kapıları var: meydan
    #                  okuma kimliği + IP eşleşmesi + TTL + kare tavanı, ve
    #                  **token ÜRETMEZ** — giriş kararı yalnız `verify`de.
    "/api/face/frames",
    #   warmup       → modeli arka planda yüklemeye başlatır, VERİ DÖNMEZ
    #                  ({basladi, hazir} + kütüphane yoksa sebep). Kilit
    #                  ekranı bunu geri sayım başlarken çağırır; token
    #                  isteseydi ısıtma tam da işe yarayacağı anda (giriş
    #                  öncesi) imkânsız olurdu.
    "/api/face/warmup",
    # ── Uygulama kilidi (2026-09-06) ────────────────────────────────────
    # Aynı gerekçe: kilit ekranı bunları çağırmak ZORUNDA, token almak için
    # çağırıyor. `/set`, `/disable`, `/lock` bilerek BURADA DEĞİL — onlar
    # kilidin arkasında durur ve ayrıca mevcut parolayı ister.
    "/api/lock/status",
    "/api/lock/unlock",
}
_SKIP_PREFIXES = ("/ui/", "/assets/", "/api/planner/google/callback", "/api/planner/ms/callback",
                  # Galeri biletli akışı: `<video src>` / `<a href>` Authorization başlığı
                  # gönderemez. Yetkiyi BİLET taşır — `/api/galeri/bilet/{id}` auth'ludur,
                  # verdiği bilet tek dosyaya bağlı ve 5 dakikada düşer; ana token URL'e girmez.
                  "/api/galeri/akis/")


def _token_kabul(token: str, kilit_kurulu: bool) -> bool:
    """Token iki kapıdan BİRİNE uyuyor mu?

    ⚠️ `AUTH_TOKEN and` koruması şart: token boşken `compare_digest("", "")`
    **True** döner ve boş `Authorization` başlığı her kapıyı açardı.
    """
    if AUTH_TOKEN and secrets.compare_digest(token, AUTH_TOKEN):
        return True
    if kilit_kurulu:
        from app.services import app_lock
        return app_lock.oturum_gecerli(token)
    return False


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    from app.services import app_lock

    # Kilit durumu her istekte okunur (dosya varlığı kontrolü). Süreç ömrü
    # boyunca önbelleğe alınamaz: kullanıcı Ayarlar'dan kilidi kurduğu anda
    # kapı kapanmalı, uygulamayı yeniden başlatınca değil.
    kilit_kurulu = app_lock.kurulu()

    # Ağa açma ayarıyla açılmış süreçte kilit sonradan kalktıysa: ağdan gelen HER istek reddedilir
    # (soket açık kalır, yeniden başlatmaya kadar). Yerel istek etkilenmez. → services/ag_ayari.py
    if not kilit_kurulu:
        from app.services import ag_ayari
        if not ag_ayari.uzak_izin(request.client.host if request.client else None, kilit_kurulu):
            return JSONResponse({"detail": M("cihaz.ag-kilitsiz-uzak")}, status_code=403)

    if not AUTH_TOKEN and not kilit_kurulu:
        return await call_next(request)

    path = request.url.path

    # Zarif kapanış ucu: kilit token'ı DEĞİL, oturum çerezi korur — onu en dıştaki
    # YerelKapi doğruladı. Kapanışı isteyen Electron/bekçi kilit token'ını taşımaz; burada
    # reddedilirse kilitli kurulumda kapanış hep zorla olur. Anahtarsız motorda uç kendini kapatır.
    # 🔴 Yalnız BU bilgisayardan: ağdan gelen istek YerelKapi'nin çerez kuralına girmez, onu
    # buradaki kilit kapısı korur — muafiyet ağa uzarsa telefon/LAN motoru kimliksiz kapatırdı.
    if path == motor_api.KAPAN_YOLU and request.method == "POST":
        from app.services.ag_ayari import loopback_istemci
        if loopback_istemci(request.client.host if request.client else None):
            return await call_next(request)

    # Statik dosyalar ve health serbest
    if path in _SKIP_PATHS or path.startswith(_SKIP_PREFIXES):
        return await call_next(request)

    # WebSocket: ?token= query param (tarayıcı header set edemiyor — KORU)
    # Yanlış anahtar SAYILIR: aynı istemci pencere içinde N farklı yanlış anahtar
    # denerse tüm API 429'la kapanır (services/api_guard.py).
    from app.services import api_guard
    kabul = lambda t: _token_kabul(t, kilit_kurulu)  # noqa: E731
    if path.startswith("/ws/"):
        durum, left = api_guard.dene(request, [request.query_params.get("token", "")], kabul)
        if durum == api_guard.OK:
            return await call_next(request)
        return _api_red(durum, left)

    # HTTP API: Authorization: Bearer <token>  veya  ?token= query param.
    # NOT: ?token= korunuyor çünkü medya URL'leri (ör. /api/live-portrait/clip,
    # <img>/<video> src) header set edemez. Query-param sızıntısı Referrer-Policy
    # (strict-origin-when-cross-origin) ile sınırlı; kalıcı çözüm: erişim log'unda
    # query string maskeleme + kısa ömürlü imzalı medya URL'leri.
    auth_header = request.headers.get("Authorization", "")
    bearer = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    durum, left = api_guard.dene(request, [bearer, request.query_params.get("token", "")], kabul)
    if durum == api_guard.OK:
        return await call_next(request)
    return _api_red(durum, left)


def _api_red(durum: str, left: float) -> JSONResponse:
    from app.services import api_guard
    if durum == api_guard.KILITLI:
        return JSONResponse({"detail": M("api.cok-yanlis-anahtar")}, status_code=429,
                            headers={"Retry-After": str(int(left) or 1)})
    return JSONResponse({"detail": "Unauthorized"}, status_code=401)


# ── Security Headers Middleware ──────────────────────────────────────────── #
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    # Uç kendi CSP'sini koyduysa (harita vekilleri: `sandbox`) EZİLMEZ — daha sıkı olan odur.
    if "content-security-policy" in response.headers:
        return response
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://unpkg.com; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "img-src 'self' data: blob: https:; "
        "media-src 'self' blob: data:; "
        "connect-src 'self' blob: ws: wss: https:; "  # blob: → GLTFLoader VRM doku fetch'i (OYUN 3D)
        "frame-src 'self' http://localhost:* http://127.0.0.1:*; "
        "worker-src 'self' blob:"
    )
    return response


# ── Demo veri kipi (YUKI_DEMO=1) — varsayılan kapalı → app/demo_kip.py ──────── #
from app import demo_kip as _demo_kip  # noqa: E402

if _demo_kip.acik():
    from fastapi.responses import Response as _Yanit

    @app.middleware("http")
    async def demo_suzgeci(request: Request, call_next):
        response = await call_next(request)
        response.headers["Permissions-Policy"] = "geolocation=()"
        tur = response.headers.get("content-type", "")
        if not (tur.startswith("text/html") or tur.startswith("application/json")):
            return response
        govde = b"".join([parca async for parca in response.body_iterator])
        if tur.startswith("text/html"):
            govde = _demo_kip.html_enjekte(govde)
        govde = _demo_kip.bayt_temizle(govde)
        basliklar = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        return _Yanit(content=govde, status_code=response.status_code, headers=basliklar)

    @app.get("/demo/demo-kip.js", include_in_schema=False)
    async def demo_betigi():
        return _Yanit(content=_demo_kip.tarayici_betigi(), media_type="application/javascript",
                      headers={"Cache-Control": "no-cache"})


# ── Yerel motor kapısı (v0.8.1) — Host + Origin + Electron oturum çerezi ──── #
# EN SON eklenir → EN DIŞTA koşar (Starlette add_middleware sırası). HTTP ve WebSocket'in
# ikisine de bakar; ayrıntı ve gerekçe → app/yerel_kapi.py
from app.yerel_kapi import YerelKapi  # noqa: E402


def _kapi_token_kabul(token: str) -> bool:
    from app.services import app_lock
    return _token_kabul(token, app_lock.kurulu())


app.add_middleware(
    YerelKapi,
    # /ws/agent: cihaz ajanı ayrı bir programdır, çerezi olamaz; kendi eşleştirme/cihaz token'ı
    # kapısı var (devices_api.agent_ws, sır boşken reddeder). Host + Origin ona da uygulanır.
    acik_yollar=_SKIP_PATHS | {"/ws/agent"},
    acik_onekler=_SKIP_PREFIXES,
    izinli_kokenler=ALLOWED_ORIGINS,
    token_kabul=_kapi_token_kabul,
)


app.include_router(chat.router)
app.include_router(voice.router)
app.include_router(websocket.router)
app.include_router(memory_api.router)
app.include_router(vision_api.router)
app.include_router(tools_api.router)
app.include_router(settings_api.router)  # HQ Ayarlar paneli
app.include_router(modes_api.router)     # HQ Mod Yöneticisi (CRUD)
app.include_router(tts_api.router)       # Faz 19 — TTS durum + test + referans yükleme
app.include_router(media_api.router)
app.include_router(push_api.router)  # Faz 12 — Android Companion
app.include_router(lp_api.router)    # Faz 13 — fal.ai Animasyon
app.include_router(planner_api.router)  # Google Calendar
app.include_router(yedek_rclone_api.router)  # rclone denetimi (salt okur, ayrı prefix)
app.include_router(yedekleme_api.router)  #  FAZ 4 — Drive yedekleme
app.include_router(todo_api.router)     # Custom Todo System
app.include_router(motor_api.router)     # POST /api/motor/kapan
app.include_router(ajan_api.router)      # AJAN sekmesi (router düzeyinde Ultra kapısı)
from app import config as _cfg_bayrak
# FITNES (varsayılan kapalı) kapalıyken uçlar 404 ve şemada yok —
# kapı services/yetki.ozellik_kapisi, istek anında okunur. Şema kararı açılıştaki değerle verilir.
# 🔴 2026-08-23: bu satır YOKTU → /api/fitness/* 404. Ekran ölü DEĞİLDİ (veri
# localStorage'daydı, fsApiPost hatayı yutuyordu) ama sunucu senkronu hiç
# çalışmıyordu: veri cihazda kalıyor, Yuki sohbetten göremiyordu.
app.include_router(fitness_api.router, include_in_schema=_cfg_bayrak.FITNES)  # PLAN > FİTNES
app.include_router(llm_config_api.router)  # LLM model seçici
app.include_router(language_api.router)     # Asistan dili (TR/JA)
app.include_router(character_api.router)    # Karakter/persona seçici (Faz 4)
app.include_router(face_api.router)         # Yüz tanıma (Free)
# 🔴 2026-09-10 (Dalga 3): bu satır YOKTU — `api/monitor.py` 142 satır kod ve 8
# rotayla depoda duruyordu ama HİÇ KAYITLI DEĞİLDİ, üstelik dört
# `electron-builder*.yml` onu kullanıcı paketinden ayrıca çıkarıyordu. Tek
# tüketicisi `game-mode.js`'ti ve OYUN modu üründe kapalı → kod ölüydü.
# HQ → SİSTEM paneli bunu uyandırıyor. Panel Free; içindeki TEK eylem
# (süreç sonlandırma) kendi kapısında kalır → `monitor.require_dev_tools`.
app.include_router(monitor_api.router)      # Dalga 3 — HQ SİSTEM paneli (Free)
# 🔴 2026-09-18: `devices_api` de `monitor.py` gibi depoda duruyor ama
# KAYITLI DEĞİLDİ ve dört `electron-builder*.yml` onu paketten ayrıca çıkarıyordu.
# Uyandırılmadan önce açık kapısı kapatıldı: `/ws/agent` artık eşleştirme kodu ya
# da cihaz tokeni ister (eski hâli AUTH_TOKEN boş olduğu için kimseyi durdurmuyordu,
# canlı ölçüldü). İKİ router da kayıtlı — REST kademe kapısını `dependencies` ile,
# WS kendi ilk satırında alır.
app.include_router(devices_api.router)      # cihaz yönetimi (Ultra)
app.include_router(devices_api.ws_router)   # /ws/agent — prefix yok (kapı handler'da)
# Dalga 3'ün kalan kalemi (2026-09-18): MAP panosu — 22 katman ucu, kademe Pro.
# `services/map_resilience.py` üründe ZATEN vardı ama hiçbir yerden
# çağrılmıyordu (ölü kod); bu router onu canlandırıyor.
app.include_router(map_api.router)          # MAP panosu (Pro)
app.include_router(lock_api.router)         # Uygulama kilidi — açılış parolası
app.include_router(pydeps_api.router)       # kütüphane indi, devreye al
app.include_router(yetki_api.router)        # GET /api/yetki
app.include_router(galeri_api.router)        # PC medya gezgini (salt okunur, Range'li)
app.include_router(dosya_api.router)         # PC dosya gezgini (salt okunur, terminalsiz)
# Atölye: görev listesi, başlat/onay/durdur/devam, sıra — `ATOLYE` bayrağı arkasında (varsayılan
# açık, g4; `ATOLYE=false` → uçlar 404, şemada yok). Kapı router'da (`gorev_api.atolye_kapisi`), istek anında okunur.
from app import config as _cfg_atolye
app.include_router(gorev_api.router, include_in_schema=_cfg_atolye.ATOLYE)
# Biyometrik özellikler (G8): kapı router'ın içinde, istek anında okunur (kapalı → 404, WS 4404).
app.include_router(gorus_api.router, include_in_schema=_cfg_atolye.GORUS)
app.include_router(ses_kimlik_api.router, include_in_schema=_cfg_atolye.SES_KIMLIK)
# Güvenli dosya (G7): ayar kendi dosyasında, kapalıyken işlem uçları 404; durum/ayar uçları şemada.
app.include_router(guvenli_dosya_api.router)
app.include_router(chatgpt_api.router)      # Continue with ChatGPT (BYOK'a ek yol)
app.include_router(saglik_api.router)        # Sağlık ölçeri: son kayıt + şimdi ölç
app.include_router(self_check_api.router)   # Kurulum denetimi + oto onarım + hata günlüğü
# Duvar kâğıdı — KADEME KAPISI YOK, geliştirici kararı: Free/Pro/Ultra üçünde de
# açık. Bu yüzden `FEATURE_MIN_TIER`/`FEATURE_DURUM` tablolarına GİRMİYOR; oraya
# yazmak "kademeli özellik" ilan etmek olurdu ve LİSANS paneli onu satılan bir şey
# gibi gösterirdi.
app.include_router(duvar_api.router)        # Sekme bazlı arka plan (resim · GIF · video)

# Faz α — Gemini Native Audio. Router HER ZAMAN kayıtlı: özellik kapalıysa
# handler accept + close(4503) ile istemciye SEBEBİNİ söyler. (Eskiden koşullu
# kayıttı → rota yokken Starlette WS'i 403 el sıkışmasıyla reddediyor, frontend
# 1006 görüp 3s'de bir sonsuz reconnect döngüsüne giriyordu.)
from app.api import websocket_native
app.include_router(websocket_native.router)

# Ela (HDC kişi tanıma) — ÜRÜNDE SÖKÜLDÜ (kişisel özellik + vision deps yok).
# ela_api / ela_service / app.ela / face_multi_auth / iris_capture silindi.

# Frontend — http://localhost:8001/
if FRONTEND_DIR.exists():


    app.mount("/ui", KatmanliStatik(directory=str(FRONTEND_DIR), html=True,
                                    oncelikliler=FRONTEND_ONCELIKLILER,
                                    fallbacks=FRONTEND_YEDEKLER), name="frontend")

    # Assets klasörünü doğrudan köke de bağlayalım ki görseller her yerden yüklensin.
    #
    # Sıra: medya katmanı → paketlenmiş → overlay.
    # ⚠️ 2026-08-08: eskiden paketlenmiş dizin BİRİNCİLdi ve yorumu şöyleydi:
    # *"overlay'de assets HİÇ yok → sıra bilinçli olarak ters"*. O gerekçe artık
    # geçersiz — medya güncellenebiliyor ve indirilen medya paketin fabrika
    # görsellerinin ÖNÜNDE olmalı. Ters bırakılsaydı kullanıcı 33 MB'ı indirir,
    # paketin eski görselini görmeye devam eder ve buna bakan hiç kimse
    # güncellemenin indiğini anlamazdı.
    _ASSET_KOKLERI = [d / "assets" for d in (MEDIA_DIR, FRONTEND_FALLBACK_DIR, FRONTEND_DIR) if d]
    _ASSET_KOKLERI = [d for d in _ASSET_KOKLERI if d.exists()]
    if _ASSET_KOKLERI:
        app.mount("/assets", KatmanliStatik(
            directory=str(_ASSET_KOKLERI[0]),
            fallbacks=_ASSET_KOKLERI[1:],
        ), name="assets")
    from app.api.live_portrait import CACHE_DIR as _ANIM_CACHE_DIR
    app.mount("/anim_cache", StaticFiles(directory=str(_ANIM_CACHE_DIR)), name="anim_cache")

    @app.get("/")
    async def serve_ui():
        resp = FileResponse(str(frontend_dosyasi("index.html")))
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    # ε: SW kök scope için — /sw.js root'tan serve edilir, /ui/sw.js de alias olarak kalır
    @app.get("/sw.js")
    async def serve_sw():
        resp = FileResponse(
            str(frontend_dosyasi("sw.js")),
            media_type="application/javascript",
        )
        resp.headers["Service-Worker-Allowed"] = "/"
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    @app.get("/ui/sw.js")
    async def serve_sw_alias():
        resp = FileResponse(
            str(frontend_dosyasi("sw.js")),
            media_type="application/javascript",
        )
        resp.headers["Service-Worker-Allowed"] = "/"
        resp.headers["Cache-Control"] = "no-cache"
        return resp


@app.get("/api/ping")
async def ping():
    """Auth kontrolü için korumalı endpoint."""
    return {"ok": True}


@app.get("/health")
async def health():
    from app.services.health import get_health_report
    start_time = getattr(app.state, "start_time", 0.0)
    report = await get_health_report(start_time)
    # Geriye uyumlu alanları koru
    sm = get_state_machine()
    report["state"] = sm.state.value
    report["memory"] = MEMORY_ENABLED
    return report


@app.get("/api/system")
async def system_metrics():
    """Halka HUD sol-rail için anlık sistem metrikleri (non-blocking psutil).

    cpu_percent(interval=None) bloklamaz; ilk çağrıda 0 dönebilir ama frontend
    periyodik poll ettiği için kendini düzeltir. net cumulative byte döner,
    hız (MB/s) hesabını frontend iki örnek arasından yapar.
    """
    import os as _os

    import psutil  # backend env'inde mevcut (tools/system.py kullanıyor)

    try:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        return {
            "cpu": round(psutil.cpu_percent(interval=None), 1),
            "cores": _os.cpu_count(),
            "ram": {
                "percent": round(mem.percent, 1),
                "used_gb": round(mem.used / (1024 ** 3), 1),
                "total_gb": round(mem.total / (1024 ** 3), 1),
            },
            "disk": {"percent": round(disk.percent, 1)},
            "net": {"sent": net.bytes_sent, "recv": net.bytes_recv},
        }
    except Exception as e:  # psutil yoksa/erişim hatası → frontend zarifçe düşer
        return {"error": str(e)}

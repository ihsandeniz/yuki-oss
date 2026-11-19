"""settings_api.py — HQ Ayarlar paneli.

İki tür ayar:
  1) config.user.json destekli ayarlar (ALLOWED_KEYS) → kalıcı; çoğu RESTART ister
     (config.py global'leri import'ta sabitlendiği için). POST kaydeder + en iyi
     çabayla canlı config global'ini günceller + needs_restart=true döner.
  2) Canlı üçlü (LLM model/sağlayıcı, dil, persona) → mevcut /api/llm/config,
     /api/language, /api/character endpoint'leri ANINDA uygular. Burada sadece
     mevcut durumları GET ile raporlanır; frontend yazma için o endpoint'leri kullanır.
"""
from __future__ import annotations

import asyncio
import importlib.util
import platform
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import config as cfg
from app import config_manager
from app.limiter import limiter
from app.mesajlar import M

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ── Ayarın GERÇEKTEN bir şeyi etkileyip etkilemediği ─────────────────────────
# 🔴 2026-08-12 ölçümü: ayar panelinde 34 ayar çiziliyordu, bunların 7'si satılan
# pakette fiziksel olarak bulunmayan özellikleri açıp kapatıyordu. Kullanıcı anahtarı
# açıyor, hiçbir şey olmuyor, ürünü bozuk sanıyor — `modes/gfx.js`'in "ya uygula,
# ya menüye koyma" kuralının ayarlar panelindeki ihlali.
#
# Anahtar ŞEMADAN SİLİNMEZ, yalnız `available:false` ile işaretlenir: kullanıcının
# `config.user.json` değeri bozulmasın ve paket içeriği ilerde değişirse ayar
# kendiliğinden geri gelsin (tek gerçek kaynak = kurulu paketin kendisi).

# Ürün paketiyle GELEN harici servisler. Fish Speech ayrı bir api_server ister
# (`services/tts.py::_synthesize_fish` → FISH_TTS_URL, varsayılan localhost:8080);
# satılan pakette o sunucu YOK. ⚠️ Modül denetimi burada YANLIŞ ölçüt olurdu:
# `ormsgpack` pakette VAR (ölçüldü) ama o yalnız serileştirme kütüphanesi — motor
# değil. Fish paketlenirse buraya eklenir, ayar kendiliğinden geri gelir.
PAKETLI_SERVISLER: frozenset[str] = frozenset()


@lru_cache(maxsize=None)
def _modul_var(ad: str) -> bool:
    """Modül bu kurulumda import edilebilir mi (yüklemeden, yalnız bakarak)."""
    try:
        return importlib.util.find_spec(ad) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        # find_spec, ana paketi bulunmayan alt modülde ImportError atar.
        return False


def _uygunluk(item: dict) -> tuple[bool, str]:
    """(kullanılabilir mi, değilse kullanıcıya söylenecek sebep)."""
    gerek = item.get("needs")
    if not gerek:
        return True, ""

    eksik = [m for m in gerek.get("modules", ()) if not _modul_var(m)]
    if eksik:
        return False, f"Bu sürümde kurulu değil ({', '.join(eksik)})."

    platformlar = gerek.get("platform")
    if platformlar and platform.system() not in platformlar:
        return False, f"Yalnız {'/'.join(platformlar)} üzerinde çalışır."

    servis = gerek.get("service")
    if servis and servis not in PAKETLI_SERVISLER:
        return False, f"Ayrıca kurulan bir {servis} sunucusu gerektirir."


    return True, ""


# Ayarı CANLI uygulanan (yeniden başlatma istemeyen) anahtarlar.
# 🔴 2026-08-28 (FAZ 9): bu küme yalnız POST yanıtında yaşıyordu; şema onu
# taşımadığı için arayüz hangi ayarın restart istediğini BİLMİYOR, "yeniden
# başlatma" etiketini AYIRT ETMEDEN her satıra basıyordu. Yani iki ayarda
# etiket yalandı. Tek kaynak burası — POST da bunu okur, ikisi ayrışamaz.
CANLI_UYGULANAN: frozenset[str] = frozenset({
    "WAKE_WORD_ENABLED",   # stt.wake_word_acik() global'i canlı okur (2026-08-05)
    "ASSISTANT_LANGUAGE",  # config.set_language() prompt cache'i temizler (2026-09-18)
    "PERSONA_VOICES",      # tts._edge_voice_params() her çağrıda taze okur (2026-09-18)
    "MODE_LAUNCHER_ENABLED",  # modes.start_mode her çağrıda app.config'ten okur (2026-09-27)
    "MASAUSTU_YUKI",       # kaydetmek = masaüstü Yuki'yi aç/kapat (services/masaustu_yuki.ayarla)
    "MASAUSTU_VRM",        # masaustu_yuki.model_yolu() her açılışta taze okur
    "FITNES",              # yetki.bayrak_acik istek anında okur; bildirim işleri koşarken bakar (g4, 11-12)
    "DOLGU_SESI",          # dolgu_sesi.acik() her turda config'ten okur (g4, 11-12)
})


# ── Bekleyen yeniden başlatma ( panel 10, 2026-09-28) ─────────────────
# Kaydedilmiş ama ancak süreç yeniden başlayınca geçerli olacak ayarlar. SÜREÇ
# BELLEĞİNDE tutulur: yeniden başlama listeyi kendiliğinden boşaltır, yani "bekliyor"
# iddiası yeniden başlatmadan sonra yalan kalamaz. Ayar açılıştaki değerine geri
# çevrilirse bekleyenden düşer — beklenen bir değişiklik kalmamıştır.
# SAĞLIK paneli bunu `/api/self-check` → `bekleyen_yeniden_baslatma` ile okur.
# Genel uçtan YAZILAMAYAN ayarlar: kendi kapısı olan, güvenlik şartı taşıyanlar. `AG_ACIK` yalnız
# `PUT /api/devices/ag` ile değişir (uygulama kilidi şartı orada) — burası açık kalsaydı kapı atlanırdı.
# `ARAYUZ_DILI` yalnız `POST /api/language` (`arayuz`) → `config.set_arayuz_dili()` ile değişir:
# jenerik `setattr` süreçteki `_arayuz_dili`'yi güncellemez, disk ile ekran ayrışırdı (2026-10-04).
# `CIHAZ_IZIN_*` yalnız `PUT /api/devices/izinler` ile açılır (erişim anahtarı şartı orada, 2026-11-01).
AYRI_KAPILI: frozenset[str] = frozenset({
    "AG_ACIK", "ARAYUZ_DILI",
    "CIHAZ_IZIN_DOSYA_YAZ", "CIHAZ_IZIN_DOSYA_SIL", "CIHAZ_IZIN_SUREC_KAPAT",
})

_ACILIS_DEGERI: dict[str, object] = {}
_BEKLEYEN: dict[str, object] = {}
_SIFIRLAMA = object()


# Şemada görünmeyen (başka panelin sahip olduğu) ayarların bekleyen-yeniden-başlatma etiketi.
# AG_ACIK'ın tek yazma kapısı `PUT /api/devices/ag` — burada yalnız adı taşınır.
EK_ETIKET: dict[str, str] = {"AG_ACIK": "Yuki'yi yerel ağa aç"}


def _etiketler() -> dict[str, str]:
    return {**EK_ETIKET, **{s["key"]: s.get("label", s["key"]) for s in SETTINGS_SCHEMA}}


def bekleyen_isaretle(key: str, onceki: object, yeni: object) -> None:
    """Başka modülün (cihazlar) yazdığı ayarı bekleyen listesine işler."""
    _bekleyen_isaretle(key, onceki, yeni)


def _bekleyen_isaretle(key: str, onceki: object, yeni: object) -> None:
    if key not in _ACILIS_DEGERI:
        _ACILIS_DEGERI[key] = onceki
    if yeni is not _SIFIRLAMA and yeni == _ACILIS_DEGERI[key]:
        _BEKLEYEN.pop(key, None)
    else:
        _BEKLEYEN[key] = yeni


def bekleyen_yeniden_baslatma() -> list[dict]:
    """[{key, label}] — yeniden başlayınca geçerli olacak kaydedilmiş ayarlar."""
    etiket = _etiketler()
    return [{"key": k, "label": etiket.get(k, k)} for k in _BEKLEYEN]


def _gorunur_sema() -> list[dict]:
    """Şema + her ayarın kullanılabilirlik damgası (`needs` dışarı sızmaz)."""
    out = []
    for item in SETTINGS_SCHEMA:
        uygun, sebep = _uygunluk(item)
        kayit = {k: v for k, v in item.items() if k != "needs"}
        kayit["available"] = uygun
        kayit["needs_restart"] = item["key"] not in CANLI_UYGULANAN
        if not uygun:
            kayit["unavailable_reason"] = sebep
        out.append(kayit)
    return out


# ── Ayar şeması (config.user.json destekli) ──────────────────────────────────
# tip: toggle | number | text | select
SETTINGS_SCHEMA: list[dict] = [
    # LLM / Zeka
    {"key": "USE_LOCAL_LLM", "cat": "llm", "label": "Yerel LLM (Ollama)", "type": "toggle"},
    {"key": "PROMPT_CACHE_ENABLED", "cat": "llm", "label": "Prompt Önbellek", "type": "toggle"},
    {"key": "SUMMARIZE_ENABLED", "cat": "llm", "label": "Otomatik Özetleme", "type": "toggle"},
    {"key": "LLM_MODEL_FAST", "cat": "llm", "label": "Hızlı Model ID", "type": "text"},
    {"key": "LLM_MODEL_STRONG", "cat": "llm", "label": "Güçlü Model ID", "type": "text"},
    {"key": "VISION_MODEL", "cat": "llm", "label": "Görüş Modeli ID", "type": "text"},
    # Companion ekibi (R5) — maliyet ayarları.
    {"key": "COUNCIL_MAX_TASKS", "cat": "llm", "label": "Ekip: en fazla uzman sayısı",
     "type": "number", "min": 1, "max": 4, "step": 1,
     "help": "Yuki bir işi en fazla kaç uzmana böler. Her uzman ayrı model isteği "
             "harcar — ücretsiz kotadaysan 2 önerilir."},
    {"key": "WORKER_MAX_STEPS", "cat": "llm", "label": "Ekip: uzman başına adım",
     "type": "number", "min": 1, "max": 4, "step": 1,
     "help": "Bir uzmanın araç kullanarak atabileceği en fazla adım. Düşürmek "
             "maliyeti düşürür, derinliği azaltır."},
    # Ses & TTS
    {"key": "USE_FISH_TTS", "cat": "ses", "label": "Fish Speech TTS (öncelikli)", "type": "toggle",
     "needs": {"service": "Fish Speech"}},
    {"key": "USE_ELEVENLABS_TTS", "cat": "ses", "label": "ElevenLabs TTS (.env'de API key gerekli)", "type": "toggle"},
    {"key": "EDGE_VOICE_RATE", "cat": "ses", "label": "Ses Hızı (örn +0%)", "type": "text"},
    {"key": "EDGE_VOICE_PITCH", "cat": "ses", "label": "Ses Tonu (örn -5Hz)", "type": "text"},
    # Dolgu sesi: cevap gecikince bir kez kısa "Hmm." (services/dolgu_sesi.py), varsayılan kapalı
    {"key": "DOLGU_SESI", "cat": "ses", "label": "Dolgu sesi (cevap gecikince \"Hmm.\")", "type": "toggle"},
    # Mikrofon / VAD / STT
    {"key": "WAKE_WORD_ENABLED", "cat": "mikrofon", "label": "Uyandırma Kelimesi", "type": "toggle"},
    {"key": "VAD_THRESHOLD", "cat": "mikrofon", "label": "VAD Eşiği", "type": "number", "min": 0.001, "max": 0.2, "step": 0.001},
    {"key": "VAD_SILERO_THRESHOLD", "cat": "mikrofon", "label": "Silero Eşiği", "type": "number", "min": 0.1, "max": 0.95, "step": 0.05},
    {"key": "WHISPER_MODEL", "cat": "mikrofon", "label": "Whisper Modeli", "type": "select", "options": ["tiny", "base", "small", "medium", "large-v3"]},
    # min 3: `stt.py` beam_size=max(değer, 3) — 1-2 seçmek hiçbir şey değiştirmiyordu (kişisel ölçümü)
    {"key": "WHISPER_BEAM_SIZE", "cat": "mikrofon", "label": "Çeviri Arama Genişliği", "type": "number", "min": 3, "max": 5, "step": 1},
    # Hafıza
    {"key": "MEMORY_RECENT_LIMIT", "cat": "hafiza", "label": "Yakın Mesaj Limiti", "type": "number", "min": 4, "max": 64, "step": 1},
    {"key": "MEMORY_SEARCH_LIMIT", "cat": "hafiza", "label": "Arama Sonuç Limiti", "type": "number", "min": 1, "max": 20, "step": 1},
    {"key": "MEMORY_MIN_SIMILARITY", "cat": "hafiza", "label": "Min. Benzerlik", "type": "number", "min": 0.1, "max": 0.9, "step": 0.05},
    # Algı & Gizlilik
    {"key": "BROWSER_ENABLED", "cat": "algi", "label": "Web Tarayıcı", "type": "toggle"},
    {"key": "AMBIENT_ENABLED", "cat": "algi", "label": "Ambient (Ekran İzleme)", "type": "toggle"},
    {"key": "AMBIENT_MODE", "cat": "algi", "label": "Ambient Modu", "type": "select", "options": ["passive", "active", "focused"]},
    {"key": "AMBIENT_INTERVAL", "cat": "algi", "label": "Ambient Aralığı (sn)", "type": "number", "min": 5, "max": 120, "step": 5},
    # Göz takibi: `services/eye_tracker.py` OpenCV + Mediapipe FaceMesh ister.
    # Ölçüldü (2026-08-12, lean venv): cv2 VAR, mediapipe YOK → servis hiç başlamaz.
    {"key": "EYE_TRACKING_ENABLED", "cat": "algi", "label": "Göz Takibi", "type": "toggle",
     "needs": {"modules": ["mediapipe", "cv2"]}},
    {"key": "EYE_TRACKING_FPS", "cat": "algi", "label": "Göz FPS", "type": "number", "min": 5, "max": 60, "step": 1,
     "needs": {"modules": ["mediapipe", "cv2"]}},
    {"key": "EYE_TRACKING_CAMERA", "cat": "algi", "label": "Kamera İndeksi", "type": "number", "min": 0, "max": 8, "step": 1,
     "needs": {"modules": ["mediapipe", "cv2"]}},
    # D-Bus yalnız Linux masaüstünde anlamlı; `dbus_next` pakette VAR ama Windows'ta
    # bağlanacak bir veri yolu yok — ölçüt modül değil işletim sistemi.
    {"key": "DBUS_ENABLED", "cat": "algi", "label": "D-Bus Entegrasyon", "type": "toggle",
     "needs": {"platform": ["Linux"]}},
    {"key": "MEDIA_CONTROL_ENABLED", "cat": "algi", "label": "Medya Kontrolü", "type": "toggle"},
    # Sistem
    {"key": "SCHEDULER_ENABLED", "cat": "gelistirici", "label": "Zamanlayıcı", "type": "toggle"},
    {"key": "MODE_LAUNCHER_ENABLED", "cat": "gelistirici", "label": "Mod Başlatıcı", "type": "toggle"},
    # Masaüstü Yuki: kaydetmek = aç/kapat (set_setting özel dalı); varsayılan kapalı, model kullanıcının kendi VRM'i
    {"key": "MASAUSTU_YUKI", "cat": "gelistirici", "label": "Masaüstü Yuki", "type": "toggle"},
    {"key": "MASAUSTU_VRM", "cat": "gelistirici", "label": "Masaüstü Yuki modeli (.vrm yolu)", "type": "text"},
    # Fitnes (PLAN › FİTNES): varsayılan kapalı, buradan açılır (g4 kararı 2026-11-12). Veri yerelde.
    {"key": "FITNES", "cat": "gelistirici", "label": "Fitnes (PLAN › FİTNES)", "type": "toggle"},
]

# Kategoriler kendi ÇİZİM BİÇİMİNİ beyan eder.
#
# `render` yoksa → kategori, şemadaki `cat` alanı kendisine eşit olan ayarlardan
# çizilir. `render` varsa → frontend'in o ada karşılık gelen özel bölümü çizilir
# (şemada ayarı olmaması normaldir).
#
# 🔴 Neden alan olarak duruyor: eskiden bu bilgi frontend'de `catId==='dil'`
# diye SABİT yazılıydı. Backend "7 kategori var" diyor, hangisinin gerçekten
# içeriği olduğunu yalnız frontend biliyordu → şemasız yeni bir kategori
# eklendiğinde kimse uyarmıyor, kullanıcı tıklayınca "Bu kategoride ayar yok"
# görüyordu. Alan burada olunca kural ölçülebilir hale geliyor:
# `test_ayar_kategorileri.py` boş kategori ilan edilmesini engelliyor.
RENDER_LIVE = "live"   # anında uygulanan üçlü: dil · karakter · LLM modeli
RENDER_GFX = "gfx"     # istemci-tarafı görünüm/performans (backend'de değeri yok)
# Güvenlik odası: açılış kilidi (parola) + yüz tanıma paneli. Şema ayarı taşımaz
# çünkü ikisi de `.env`/ayar değeri DEĞİL — parola hash'li kendi dosyasında
# (`services/app_lock.py`), yüz kayıtları kendi deposunda (`face_store.py`)
# yaşar. Ayar şemasına sokmak, parolayı "değer" olarak `/api/settings`
# çıktısına taşırdı.
RENDER_GUVENLIK = "guvenlik"

# `extra`: şema satırlarının ALTINA eklenen ek panel (kategoriyi tek başına
# doldurmaz, tamamlar). Eski SES sekmesi bu yolla Ses & TTS'in altında yaşıyor.
EXTRA_TTS = "tts"      # test/profil/referans sesi paneli (#hq-panel-tts)
EXTRA_GORUS = "gorus"  # kamera görüşü + ses kimliği kartları (gorus-panel.js; bayrak kapalıysa kart yok)
# `bolumler`: kategorinin taşıdığı, şemadan gelmeyen ek bölümler. `extra`dan
# FARKI — `extra` HTML'de hazır duran bir paneli o odaya gömer (#hq-panel-tts);
# `bolumler` ise odanın kendi içinde çizilen bir davranışı ilan eder. İkisini
# karıştırmak testi kırdı (test_bilinmeyen_extra_degeri_yok haklıydı: sıfırlama
# bir panel değil).
BOLUM_SIFIRLA = "sifirla"  # "tüm ayarları sıfırla" — TEK kategoride
# 🔴 2026-08-28 (FAZ 9): sıfırlama düğmesi SEKİZ kategorinin de altında
# tekrarlanıyordu; oda-özel olmayan bir eylem oda-özel görünüyordu. Tek yere
# indirilirken frontend'e `catId==='gelistirici'` diye yazılmıştı — bu projenin
# kapalı bir kusur sınıfı (test_ayar_kategorileri.py onu YAKALADI). Kategori
# kimliği frontend'de sabitlenmez; hangi odanın ne taşıdığını backend ilan eder.

CATEGORIES: list[dict] = [
    {"id": "llm", "label": "LLM / Zeka", "icon": "◈"},
    {"id": "ses", "label": "Ses & TTS", "icon": "♪", "extra": EXTRA_TTS},
    {"id": "mikrofon", "label": "Mikrofon / VAD", "icon": "◉"},
    {"id": "hafiza", "label": "Hafıza", "icon": "❖"},
    {"id": "algi", "label": "Algı & Gizlilik", "icon": "◎"},
    {"id": "dil", "label": "Dil & Karakter", "icon": "✦", "render": RENDER_LIVE},
    # Görünüm & Performans: değerleri tarayıcıda (localStorage) yaşar, backend'de
    # karşılığı yok → şema ayarı taşımaz, `render` ile çizilir. R0'ın ölçtüğü
    # HAFİF kademesi ve `PerfTier` kademesi buradan erişilebilir hale geliyor;
    # ikisi de vardı ama AYAR panelinden ulaşılamıyordu.
    {"id": "gorunum", "label": "Görünüm & Performans", "icon": "◐", "render": RENDER_GFX},
    # Güvenlik: açılış kilidi + yüz tanıma. Yüz, üst sekmelerden BURAYA taşındı
    # (geliştirici kararı 2026-09-06) — kimlik/erişimle ilgili her şey tek odada.
    {"id": "guvenlik", "label": "Güvenlik", "icon": "⚿", "render": RENDER_GUVENLIK},
    {"id": "gelistirici", "label": "Sistem", "icon": "⚙", "extra": EXTRA_GORUS, "bolumler": [BOLUM_SIFIRLA]},
]


class SettingUpdate(BaseModel):
    value: object  # str | int | float | bool


def _current_values() -> dict:
    """Şemadaki her anahtarın anlık (effective) config değeri."""
    out = {}
    for item in SETTINGS_SCHEMA:
        out[item["key"]] = getattr(cfg, item["key"], None)
    return out


def _live_blocks() -> dict:
    """Canlı uygulanabilen üçlünün durumu (frontend kendi endpoint'leriyle yazar)."""
    blocks: dict = {}
    # LLM
    try:
        from app.services.llm import get_runtime_config
        rc = get_runtime_config()
        blocks["llm"] = {
            **rc,
            "presets": cfg.model_presets() if hasattr(cfg, "model_presets") else getattr(cfg, "MODEL_PRESETS", {}),
            "openrouter_available": bool(getattr(cfg, "OPENROUTER_API_KEY", "")),
            "anthropic_available": bool(getattr(cfg, "ANTHROPIC_API_KEY", "")),
        }
    except Exception:
        blocks["llm"] = None
    # Dil
    try:
        from app.config import get_language, LANGUAGES
        from app.config import get_arayuz_dili, ARAYUZ_DILLERI
        _etiket = lambda c: (LANGUAGES[c].get("flag", "") + " " + LANGUAGES[c].get("name", c)).strip()
        # İki eksen (2026-10-04): `current`/`available` KONUŞMA dili (tr/en/ja),
        # `arayuz`/`arayuz_available` ARAYÜZ dili (tr/en — Japonca arayüz yok).
        blocks["language"] = {
            "current": get_language(),
            "available": [{"code": c, "label": _etiket(c)} for c in LANGUAGES],
            "arayuz": get_arayuz_dili(),
            "arayuz_available": [{"code": c, "label": _etiket(c)} for c in ARAYUZ_DILLERI],
        }
    except Exception:
        blocks["language"] = None
    # Karakter (paket kilidi bilgisiyle)
    try:
        from app.services.personas import get_persona, list_personas
        from app.services import yetki
        available = [
            {**p, "locked": not yetki.character_allowed(p["name"])}
            for p in list_personas()
        ]
        blocks["character"] = {"current": get_persona(), "available": available}
    except Exception:
        blocks["character"] = None
    return blocks


@router.get("")
@limiter.limit("100/minute")
async def get_settings(request: Request):
    """Tüm ayarlar: şema + kategoriler + anlık değerler + kullanıcı override'ları + canlı üçlü."""
    return {
        "categories": CATEGORIES,
        "schema": _gorunur_sema(),
        "values": _current_values(),
        "user_overrides": list(config_manager.load().keys()),
        "live": _live_blocks(),
        # 2026-09-27 (AYARLAR satır tasarımı): satır "SEN DEĞİŞTİRDİN · varsayılan: X" +
        # "varsayılana dön" gösterir. `user_overrides` yetmiyordu: panel kaydı varsayılanla
        # AYNI değerde olabilir (değiştirip geri almak) — o satır "değiştirdin" demez.
        "varsayilan": _varsayilanlar(),
        "degisti": _degisenler(),
    }


def _varsayilanlar() -> dict:
    """Panel kaydı uygulanmadan önceki değer (.env / config.py) — şemadaki her ayar için."""
    return {s["key"]: cfg.PANEL_ONCESI.get(s["key"]) for s in SETTINGS_SCHEMA
            if s["key"] in cfg.PANEL_ONCESI}


def _degisenler() -> list[str]:
    """Panel kaydı olup ŞU ANKİ değeri varsayılandan farklı olan ayarlar."""
    sema = {s["key"] for s in SETTINGS_SCHEMA}   # dil gibi satırı olmayan kayıtlar sayılmaz
    return [k for k in config_manager.load()
            if k in sema and k in cfg.PANEL_ONCESI and getattr(cfg, k, None) != cfg.PANEL_ONCESI.get(k)]


@router.get("/wake-word")
@limiter.limit("100/minute")
async def get_wake_word(request: Request):
    """Uyandırma kelimesi filtresi açık mı + hangi kelimeler.

    🔴 Neden ayrı (ve ucuz) bir uç: "Her zaman dinle" düğmesi bandrolünde
    *"Hey Yuki dinleniyor"* yazıyordu ama filtre varsayılan KAPALI olduğu için
    Yuki duyduğu **her** cümleye yanıt veriyordu. Banner artık gerçeği yazacak,
    bunun için de gerçeği bilmesi lazım. `/api/settings` bu iş için ağır
    (persona listesi + lisans kapıları + model ön ayarları döner).
    """
    from app.services.stt import wake_word_acik, _wake_words
    return {"ok": True, "enabled": wake_word_acik(), "words": _wake_words()}


@router.get("/persona-voices")
@limiter.limit("100/minute")
async def get_persona_voices(request: Request):
    """Karakter başına seçilmiş Edge TTS sesleri + aktif dilin varsayılanı.

    🔴 2026-09-18 (FAZ 0, A6): TTS panelindeki ses seçici seçimi yalnız
    `localStorage`'a yazıyordu ve onu okuyan hiçbir uç yoktu — seçim sunucuya hiç
    ulaşmıyordu. Panelin gerçek durumu göstermesi için önce gerçeği okuyabilmesi
    lazım; `/wake-word` ile aynı gerekçe (tam `/api/settings` bu iş için ağır).

    `secimler` boş bırakılan karakter `dil_varsayilani` sesini kullanır.
    """
    import json as _json
    from app.config import get_lang_config, get_language
    ham = (config_manager.get("PERSONA_VOICES", "") or "").strip()
    try:
        secimler = _json.loads(ham) if ham else {}
    except Exception:
        secimler = {}
    return {
        "ok": True,
        "value": ham,
        "secimler": secimler,
        "dil": get_language(),
        "dil_varsayilani": get_lang_config().get("edge_voice", ""),
    }


@router.post("/{key}")
@limiter.limit("30/minute")
async def set_setting(request: Request, key: str, body: SettingUpdate):
    """Bir ayarı config.user.json'a kaydet + en iyi çabayla canlı global'i güncelle.
    Çoğu ayar yeniden başlatma gerektirir (needs_restart=true)."""
    if key not in config_manager.ALLOWED_KEYS or key in AYRI_KAPILI:
        raise HTTPException(status_code=400, detail=M("ayar.bilinmeyen-anahtar", anahtar=key))
    # Kullanılamayan ayar (kademe / eksik modül / platform) YAZILMAZ. 🔴 09-27 ölçüldü: panel
    # Ultra ayarını yalnız ARAYÜZDE gizliyordu, uç her kademede kaydediyordu.
    _kalem = next((s for s in SETTINGS_SCHEMA if s["key"] == key), None)
    if _kalem is not None:
        _uygun, _sebep = _uygunluk(_kalem)
        if not _uygun:
            raise HTTPException(status_code=403, detail=M("ayar.kullanilamaz", sebep=_sebep))
    if key == "MASAUSTU_YUKI":   # kaydetmek = masaüstü Yuki'yi aç/kapat; açılamazsa ayar yazılmaz (hata değil, durum)
        from app.services import masaustu_yuki
        acik = body.value is True or str(body.value).strip().lower() in ("true", "1", "on")
        r = await asyncio.to_thread(masaustu_yuki.ayarla, acik)
        if not r.get("ok") and r.get("durum") in ("model_yok", "desteklenmiyor"):
            return {"ok": False, "key": key, "value": False, "needs_restart": False, "masaustu": r}
        if not r.get("ok"):
            raise HTTPException(status_code=409, detail=M("ayar.masaustu-acilamadi" if acik else "ayar.masaustu-kapanmadi", hata=r.get('hata')))
        return {"ok": True, "key": key, "value": config_manager.get(key), "needs_restart": False, "masaustu": r}
    # Boş metin, dolu bir varsayılanı EZMEZ. 🔴 09-27 ölçüldü: `LLM_MODEL_FAST` kutusu boş
    # kaydedilince `""` kalıcı kayıt oldu, yeniden başlatınca varsayılan `openai/gpt-4o-mini`
    # yerine BOŞ model kaldı. Varsayılana dönmek ayrı ve açık bir eylem: DELETE /{key}.
    # Varsayılanı zaten boş olan ayarda (ör. boş liste anlamındaki alanlar) boş değer meşru.
    if (isinstance(body.value, str) and not body.value.strip()
            and key not in ("PERSONA_VOICES", "ASSISTANT_LANGUAGE")
            and cfg.PANEL_ONCESI.get(key) not in (None, "")):
        raise HTTPException(status_code=400, detail=M("ayar.bos-olamaz"))
    # Dilin TEK yazma kapısı config.set_language() (2026-09-18, FAZ 0). Buradan
    # geçilmezse `config.user.json` yeni dili, çalışan süreç eskisini taşır —
    # `_current_language` bu jenerik yolun `setattr(cfg, key, ...)` satırıyla
    # güncellenmez. İki yazıcı = iki gerçeklik.
    if key == "ASSISTANT_LANGUAGE":
        from app.config import set_language, get_language, LANGUAGES
        if not set_language(str(body.value)):
            raise HTTPException(
                status_code=400,
                detail=M("ayar.gecersiz-dil", deger=body.value, secenekler=list(LANGUAGES)),
            )
        return {"ok": True, "key": key, "value": get_language(), "needs_restart": False}
    # Ses haritası dış servise (Edge TTS) gidiyor ve kullanıcıdan geliyor → biçim
    # doğrulanır. Serbest metin kabul edilirse geçersiz ses sessizce sentezi düşürür.
    if key == "PERSONA_VOICES":
        import json as _json
        from app.services.personas import PERSONAS
        from app.services.tts import GECERLI_SES
        ham = (body.value or "").strip() if isinstance(body.value, str) else ""
        if ham:
            try:
                harita = _json.loads(ham)
                assert isinstance(harita, dict)
            except Exception:
                raise HTTPException(status_code=400, detail=M("ayar.ses-haritasi-json"))
            for kisi, ses in harita.items():
                if kisi not in PERSONAS:
                    raise HTTPException(status_code=400, detail=M("ayar.bilinmeyen-karakter", karakter=kisi))
                # Boş değer = "dil varsayılanına dön" → geçerli, silinir
                if ses and not GECERLI_SES.match(str(ses)):
                    raise HTTPException(
                        status_code=400,
                        detail=M("ayar.gecersiz-ses", ses=ses),
                    )
            ham = _json.dumps({k: v for k, v in harita.items() if v}, ensure_ascii=False)
        ok, msg = config_manager.set_value(key, ham)
        if not ok:
            raise HTTPException(status_code=500, detail=M("ayar.kaydedilemedi", sebep=msg))
        return {"ok": True, "key": key, "value": ham, "needs_restart": False}
    onceki = getattr(cfg, key, None)
    ok, msg = config_manager.set_value(key, body.value)
    if not ok:
        raise HTTPException(status_code=500, detail=M("ayar.kaydedilemedi", sebep=msg))
    # en iyi çaba: bellekteki config global'ini de güncelle (yeni okumalar görebilir)
    value = config_manager.get(key)
    try:
        setattr(cfg, key, value)
    except Exception:
        pass
    if key == "FITNES" and value is True:
        # Açılışta FITNES kapalıysa depo kurulmamış ve Postgres v1 verisi içeri alınmamıştır
        # (main.lifespan) — anahtar canlı açıldığında aynı kurulum burada bir kez yapılır.
        try:
            from app.api import fitness as _fitness_api
            await _fitness_api.init_fitness_db()
        except Exception as e:  # noqa: BLE001 — kurulum hatası ayarı geri almaz, günlüğe düşer
            import logging
            logging.getLogger(__name__).warning("Fitnes canlı açılış kurulumu başarısız: %s", e)
    # Tek kaynak: CANLI_UYGULANAN (şema da aynı kümeyi okur — ayrışamazlar).
    needs_restart = key not in CANLI_UYGULANAN
    if needs_restart:
        _bekleyen_isaretle(key, onceki, value)
    return {"ok": True, "key": key, "value": value, "needs_restart": needs_restart}


@router.delete("/{key}")
@limiter.limit("30/minute")
async def varsayilana_don(request: Request, key: str):
    """Tek ayarın panel kaydını kaldır → .env / config.py varsayılanı (HQ "varsayılana dön").
    Bellekteki değer de hemen varsayılana çekilir; canlı uygulanmayan ayar için
    `needs_restart` döner."""
    if key not in config_manager.ALLOWED_KEYS or key in AYRI_KAPILI:
        raise HTTPException(status_code=400, detail=M("ayar.bilinmeyen-anahtar", anahtar=key))
    if key == "ASSISTANT_LANGUAGE":   # dilin tek yazma kapısı set_language — burada silinmez
        raise HTTPException(status_code=400, detail=M("ayar.bilinmeyen-anahtar", anahtar=key))
    onceki = getattr(cfg, key, None)
    ok, msg = config_manager.sil(key)
    if not ok:
        raise HTTPException(status_code=500, detail=M("ayar.kaydedilemedi", sebep=msg))
    if key == "MASAUSTU_YUKI":   # varsayılan kapalı → açıksa kapat
        from app.services import masaustu_yuki
        await asyncio.to_thread(masaustu_yuki.durdur)
    value = cfg.PANEL_ONCESI.get(key)
    try:
        setattr(cfg, key, value)
    except Exception:
        pass
    if key not in CANLI_UYGULANAN:
        _bekleyen_isaretle(key, onceki, value)
    return {"ok": True, "key": key, "value": value, "needs_restart": key not in CANLI_UYGULANAN}


@router.get("/reset-preview")
@limiter.limit("30/minute")
async def sifirlama_onizleme(request: Request):
    """Sıfırlama neyi değiştirecek: panel kaydı olup varsayılandan FARKLI olan her ayar
    (şimdi → sonra). Kişiselde önizleme "4 ayar" sanılanın aslında 5 olduğunu gösterdi —
    sıfırlama, varsayılanı açık olan bir özelliği de AÇABİLİR; kullanıcı onu önceden görmeli."""
    etiket = _etiketler()
    degisen = []
    for key, kayit in config_manager.load().items():
        if key in config_manager.SIFIRLAMADA_KORUNAN:   # dil + karakter sesleri (reset aynı listeyi kullanır)
            continue
        simdi = getattr(cfg, key, kayit)
        sonra = cfg.PANEL_ONCESI.get(key)
        if simdi != sonra:
            degisen.append({"key": key, "label": etiket.get(key, key), "simdi": simdi, "sonra": sonra,
                            # 🔑 Hepsi yeniden açılınca: `reset()` yalnız dosyayı siler, bellekteki
                            # değere dokunmaz — "HEMEN" işaretli ayar da sıfırlamada restart ister (goz 09-27)
                            "needs_restart": True})
    return {"ok": True, "degisen": degisen}


@router.patch("/reset")
@limiter.limit("10/minute")
async def reset_settings(request: Request, confirm: bool = False):
    """Tüm kullanıcı ayarlarını sil → .env varsayılanları (yeniden başlatma sonrası)."""
    if not confirm:
        raise HTTPException(status_code=400, detail=M("ayar.sifirla-onay"))
    sifirlanacak = [k for k in config_manager.load() if k not in config_manager.SIFIRLAMADA_KORUNAN]
    if not config_manager.reset():
        raise HTTPException(status_code=500, detail=M("ayar.sifirlama-basarisiz"))
    for k in sifirlanacak:
        _bekleyen_isaretle(k, getattr(cfg, k, None), _SIFIRLAMA)
    return {"ok": True, "needs_restart": True}

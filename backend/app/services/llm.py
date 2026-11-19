"""OpenRouter LLM wrapper — streaming + sync chat for Yuki.

Faz 3: MEMORY_ENABLED=True ise pgvector hafıza sistemi kullanılır.
       False ise Faz 1/2 davranışı (in-memory _history) korunur.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
import asyncio
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

from app.config import (
    MEMORY_ENABLED,
    MEMORY_RECENT_LIMIT,
    MEMORY_SEARCH_LIMIT,
    MEMORY_MIN_SIMILARITY,
    OPENROUTER_API_KEY,
    ANTHROPIC_API_KEY,
    LLM_MODEL,
    LLM_MODEL_FAST,
    LLM_MODEL_STRONG,
    LLM_PROVIDER,
    SESSION_ID,
    build_system_prompt,
    YUKI_SYSTEM_PROMPT,
    USE_LOCAL_LLM,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    PROMPT_CACHE_ENABLED,
    SUMMARIZE_ENABLED,
)
from app.services import llm_providers as _lp
from app.services.tools import TOOLS, get_active_tools
from app.services import arac_gecmisi
from app.services.tools.system import get_current_datetime
from app.services.runner import LLMRunner, CancellationToken
from app.services.security.dis_icerik import kullanici_metni_notu
from app.mesajlar import M

# ------------------------------------------------------------------ #
# Runtime model/provider state — API ile değiştirilebilir
# ------------------------------------------------------------------ #

_runtime_provider: str = LLM_PROVIDER   # "openrouter" | "anthropic"
_runtime_model: str = LLM_MODEL         # şu an kullanılan model ID

# 🔴 2026-08-01: "kullanıcı model seçti mi?" sorusu `_runtime_model != LLM_MODEL`
# karşılaştırmasıyla TAHMİN ediliyordu. BYOK paneli seçilen modeli `.env`'e de
# yazdığı için RESTART SONRASI ikisi eşitleniyor → kod "seçim yapılmamış" sanıp
# ücretli FAST/STRONG varsayılanlarına dönüyordu. Tahmin yerine açık bayrak.
_model_explicitly_set: bool = False


def set_runtime_config(provider: str, model: str) -> None:
    """Model ve sağlayıcıyı çalışırken değiştir. Client invalidate atomik swap ile yapılır."""
    global _runtime_provider, _runtime_model, _client, _last_mode, _model_explicitly_set
    _runtime_provider = provider
    _runtime_model = model
    _model_explicitly_set = True
    # Atomik swap: _client = None YAZMAYIZ; bunun yerine bir sonraki _get_client()
    # new_client oluştursa atama yapıp use edilir. Race: setter bu satırları çalıştırırken
    # pending _get_client() yalnız _client'in eski referansını okur (None değil, object);
    # _last_mode resetlemeyle _get_client() "mod değişti" kontrolünde yeniden kurulur.
    _last_mode = None  # ← mod değişimini işaret et (setter'ın yeni sağlayıcısını _get_client döngüsünde yakala)
    logger.info("LLM config değişti → provider=%s model=%s", provider, model)


def get_runtime_config() -> dict:
    """Mevcut sağlayıcı ve model bilgisini döner."""
    return {
        "provider": _runtime_provider,
        "model": _runtime_model,
        "use_local": USE_LOCAL_LLM,
    }


def set_provider_key(saglayici: str, key: str) -> None:
    """BYOK: bir sağlayıcının anahtarını çalışırken güncelle (atomik swap).

    Anahtarlar `llm_providers` deposunda sağlayıcı başına tutulur — biri
    girildiğinde öbürü SİLİNMEZ (kullanıcı sağlayıcılar arasında gidip gelirken
    anahtarını tekrar girmesin diye).

    `_client` yeniden kurma kararı artık `_istemci_damgasi()` ile veriliyor:
    (yerel mi · sağlayıcı · anahtar) üçlüsünden herhangi biri değişirse bir
    sonraki `_get_client()` istemciyi yeniden kurar. Eskiden yalnız "mod" (yerel/
    bulut) izleniyordu; sağlayıcı değişimi ve anahtar değişimi aynı bayrağa
    (`_last_mode = None`) yamanmıştı.
    """
    global OPENROUTER_API_KEY
    _lp.anahtar_ayarla(saglayici, key)
    if saglayici == "openrouter":
        # Geriye dönük uyum: modül global'ini de tazele (eski çağrı yerleri okuyor)
        OPENROUTER_API_KEY = key
    logger.info("%s API anahtarı güncellendi (runtime, %d karakter)", saglayici, len(key or ""))


def set_openrouter_key(key: str) -> None:
    """Geriye dönük uyum sarmalayıcısı — `set_provider_key("openrouter", key)`."""
    set_provider_key("openrouter", key)


def has_openrouter_key() -> bool:
    """Herhangi bir bulut sağlayıcısının anahtarı var mı?

    ⚠️ Ad tarihsel: eskiden tek sağlayıcı vardı. Çağıranlar (self_check, UI) bu
    soruyla aslında *"sohbet edebilir miyiz"*i soruyor — Google anahtarı girmiş
    bir kullanıcıya "anahtar yok" demek yanlış olurdu.
    """
    return bool(_lp.anahtarli_kimlikler())


_client: AsyncOpenAI | None = None
_last_mode: bool | None = None   # True=yerel, False=bulut (geriye dönük; testler okuyor)
_last_damga: tuple | None = None


def aktif_saglayici() -> str:
    """Kullanılan sağlayıcının kimliği (yerel modda 'ollama')."""
    if USE_LOCAL_LLM:
        return "ollama"
    return _runtime_provider or _lp.VARSAYILAN


def _istemci_damgasi(yerel: bool) -> tuple:
    if yerel:
        return ("ollama", OLLAMA_BASE_URL, "")
    kimlik = _runtime_provider or _lp.VARSAYILAN
    return ("bulut", kimlik, _lp.anahtar(kimlik))


def _get_client(force_cloud: bool = False) -> AsyncOpenAI:
    """LLM istemcisini döndürür. force_cloud=True ise yerel zeka ayarını baypas eder.

    TOCTOU (race): global'ler yerel değişkene okunur, kurma işlemi yerelde yapılır,
    sonuç tek atamayla global'e yazılır → ara duruma geçilmez.

    🔴 `claude_code` ve `anthropic` sağlayıcıları buradan GEÇMEZ; onların kendi
    akış yolları var (`_stream_claude_code` / `_stream_anthropic`). Buraya
    düşerlerse (ör. `quick_ask`) OpenAI-uyumlu uç bulunmadığı için varsayılan
    sağlayıcıya değil, **hata veren bir istemciye** düşmek yerine OpenRouter'a
    düşülür — anahtarı varsa çalışır, yoksa zaten anlaşılır bir hata döner.
    """
    global _client, _last_mode, _last_damga

    current_client = _client
    current_damga = _last_damga

    target_mode = not force_cloud if USE_LOCAL_LLM else False
    target_damga = _istemci_damgasi(target_mode)

    if current_client is None or current_damga != target_damga:
        if target_mode:
            logger.info("İstemci oluşturuluyor: YEREL (%s)", OLLAMA_BASE_URL)
            new_client = AsyncOpenAI(
                base_url=OLLAMA_BASE_URL,
                api_key="ollama",
            )
        else:
            kimlik = target_damga[1]
            sag = _lp.kayit(kimlik)
            if kimlik == "chatgpt":
                # ChatGPT hesabı (resmî giriş): kendi istemcisi, anahtar yok.
                from app.services.chatgpt_plan.istemci import ChatGPTAsyncClient
                logger.info("İstemci oluşturuluyor: ChatGPT (resmî giriş)")
                _client = new_client = ChatGPTAsyncClient()
                _last_mode, _last_damga = target_mode, target_damga
                return new_client
            if sag is None or sag.sdk != "openai":
                # OpenAI-uyumlu ucu olmayan sağlayıcı (anthropic/claude_code) ya da
                # bilinmeyen kimlik → OpenRouter'a düş.
                sag = _lp.kayit(_lp.VARSAYILAN)
            logger.info("İstemci oluşturuluyor: BULUT (%s)", sag.ad)
            new_client = AsyncOpenAI(
                base_url=sag.base_url,
                api_key=_lp.anahtar(sag.kimlik) or "anahtar-yok",
                default_headers=dict(sag.basliklar) or None,
            )
        # Atomik assignment — tek atama, ara duruma geçmez
        _client = new_client
        _last_mode = target_mode
        _last_damga = target_damga
        return new_client

    return current_client


_yan_client: AsyncOpenAI | None = None
_yan_damga: tuple | None = None


def _yan_uyumlu():
    """Seçili sağlayıcı kendi SDK'sıyla konuşuyorsa (Anthropic) ve OpenAI-uyumlu ucu
    kullanılabiliyorsa onun kaydı; değilse None (yerel mod dahil)."""
    if USE_LOCAL_LLM:
        return None
    sag = _lp.kayit(_runtime_provider or _lp.VARSAYILAN)
    if sag is None or sag.sdk == "openai":
        return None
    return _lp.uyumlu_kayit(sag.kimlik)


def _yan_istemci() -> AsyncOpenAI:
    """Arka plan işleri ve ekip işçisi için istemci — seçili sağlayıcıyı izler.

    🔴 2026-11-12 ölçümü: Anthropic seçili + anahtarlıyken `_get_client`
    OpenAI-uyumlu uç bulamayıp OpenRouter'a düşüyordu; ekip işçisi (run_team,
    delegate_to_companion), özet ve olgu çıkarımı kullanıcının sağlayıcısında değil
    OpenRouter'da koşuyor, OpenRouter anahtarı yoksa sessizce düşüyordu. Anthropic'in
    resmî OpenAI-uyumlu ucu varken o kullanılır; anahtar yoksa eski yol (`_get_client`).
    `_get_client`'in kendisi değişmedi: görüş yolu (`VISION_MODEL`, OpenRouter kimliği)
    onu kullanıyor.
    """
    global _yan_client, _yan_damga
    sag = _yan_uyumlu()
    if sag is None:
        return _get_client(force_cloud=True)
    damga = (sag.kimlik, sag.base_url, _lp.anahtar(sag.kimlik))
    istemci = _yan_client
    if istemci is None or _yan_damga != damga:
        istemci = AsyncOpenAI(base_url=sag.base_url, api_key=damga[2],
                              default_headers=dict(sag.basliklar) or None)
        _yan_client, _yan_damga = istemci, damga
    return istemci


async def quick_ask(
    prompt: str,
    system: str = "Sen Yuki, kullanıcının kişisel AI asistanısın.",
) -> str:
    """Tek seferlik LLM çağrısı — chat geçmişine dokunulmaz, max_tokens sınırlı."""
    client = _yan_istemci()
    model = _runtime_model or LLM_MODEL
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=250,
            temperature=0.6,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("quick_ask hata: %s", e)
        return ""


# ------------------------------------------------------------------ #
# Response types
# ------------------------------------------------------------------ #


@dataclass
class EmotionTag:
    emotion: str = "neutral"
    intensity: float = 0.5


@dataclass
class ChatResponse:
    text: str
    emotion: EmotionTag = field(default_factory=EmotionTag)


# ------------------------------------------------------------------ #
# In-memory fallback (MEMORY_ENABLED=False durumu — Faz 1/2 uyumluluğu)
# ------------------------------------------------------------------ #

_histories: dict[str, list[dict]] = {}
MAX_HISTORY = 20


class LLMUserError(Exception):
    """Kullanıcıya doğrudan gösterilebilir LLM hatası (ham SDK/HTTP hatası değil)."""


def llm_error_message(exc: BaseException) -> str:
    """Sağlayıcı hatasını kullanıcının anlayacağı TR mesaja çevir.

    Tanımadığı hata için "" döner → çağıran generic mesajı kullanır.
    Ham hata metni ASLA kullanıcıya gitmez; teknik ayrıntı log'a yazılır.
    """
    try:
        from openai import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            AuthenticationError,
            PermissionDeniedError,
            RateLimitError,
        )
    except ImportError:  # pragma: no cover
        return ""

    sag = _lp.kayit(aktif_saglayici())
    sag_ad = sag.ad if sag else M("llm.saglayici-genel")
    sag_url = sag.anahtar_url if sag else "https://openrouter.ai/keys"

    if isinstance(exc, AuthenticationError):
        return M("llm.anahtar-gecersiz", saglayici=sag_ad, url=sag_url)
    if isinstance(exc, PermissionDeniedError):
        return M("llm.model-erisimi-yok")
    if isinstance(exc, RateLimitError):
        return _kota_mesaji(exc, sag)
    if isinstance(exc, (APITimeoutError, APIConnectionError)):
        return M("llm.ulasilamadi")
    if isinstance(exc, APIStatusError):
        code = getattr(exc, "status_code", None)
        if code == 402:
            return M("llm.bakiye-bitti", saglayici=sag_ad)
        if code == 429:
            # Bazı sağlayıcılar kotayı RateLimitError yerine düz 429 APIStatusError
            # olarak döndürüyor (SDK sınıflandırması uca göre değişiyor).
            return _kota_mesaji(exc, sag)
        if code == 404:
            return M("llm.model-bulunamadi")
        # 🔴 2026-08-02 — SAHA RAPORU: kullanıcı ekranında yalnız "HTTP 400" görünüyordu.
        # Sebep gövdedeydi ve atılıyordu. Bu, aynı gün ElevenLabs'te düzeltilen hatanın
        # (kota aşımını "geçersiz anahtar" sanmak) BİREBİR aynı sınıfı: durum satırına
        # bakıp gövdeyi çöpe atmak. Durum kodu "ne oldu"yu söylemez, gövde söyler.
        detay = _saglayici_hata_metni(exc)
        if (code == 401 and "missing authentication header" in detay.lower()
                and (sag is None or sag.kimlik == "openrouter")):
            # ÖLÇÜLDÜ: OpenRouter, anahtar `sk-or-` biçiminde değilse tam olarak
            # bunu döndürüyor. 07-31'den beri kaynağı bulunamayan hata buydu —
            # en sık sebebi LİSANS anahtarının API anahtarı kutusuna yapıştırılması.
            return M("llm.anahtar-bicimi")
        if detay:
            return M("llm.reddedildi-detayli", kod=code, detay=detay)
        return M("llm.reddedildi", kod=code)
    return ""


def _kota_mesaji(exc: BaseException, sag) -> str:
    """429'u kullanıcının anlayacağı kotaya çevir — GÜNLÜK mü DAKİKALIK mı?

    🔴 2026-08-05: eski metin *"biraz bekleyip tekrar dene"*ydi. Ücretsiz
    OpenRouter kullanıcısı günlük 50 isteği bitirdiğinde bu cümle **yanlış tavsiye**:
    beklemekle geçmez, ertesi güne kadar sürer. Kullanıcı bunu "Yuki bozuldu" diye
    okur — 08-03'teki *"bazı ücretsiz modeller çalışmıyor"* raporunun aynı sınıfı.

    Ayrım gövdeden yapılır, durum kodundan DEĞİL (ikisi de 429). OpenRouter günlük
    kotada gövdede `free-models-per-day` der; dakikalık sınırda demez.
    """
    detay = _saglayici_hata_metni(exc).lower()
    gunluk = any(k in detay for k in ("per-day", "per day", "daily", "günlük", "free-models-per"))
    model = _runtime_model or ""
    ucretsiz_model = model.endswith(":free")

    if gunluk:
        m = M("llm.kota-gunluk")
        if sag and sag.kimlik == "openrouter":
            m += M("llm.kota-openrouter-eki")
        return m + M("llm.kota-alternatif")

    m = M("llm.kota-dakikalik")
    if ucretsiz_model:
        m += M("llm.kota-ucretsiz-eki")
    return m


def _saglayici_hata_metni(exc: Exception) -> str:
    """Sağlayıcının gerçek hata mesajını çıkar. Gövde yoksa boş döner.

    OpenAI SDK'sı gövdeyi `exc.body` (çözümlenmiş) ya da `exc.response` üzerinden
    verir; ikisi de olmayabilir, o yüzden her adım ayrı korunuyor.
    """
    govde = getattr(exc, "body", None)
    if isinstance(govde, dict):
        hata = govde.get("error", govde)
        if isinstance(hata, dict):
            m = hata.get("message") or hata.get("detail")
            if m:
                return str(m)[:300]
        if isinstance(hata, str):
            return hata[:300]
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            j = resp.json()
            hata = j.get("error", j) if isinstance(j, dict) else j
            if isinstance(hata, dict) and (hata.get("message") or hata.get("detail")):
                return str(hata.get("message") or hata.get("detail"))[:300]
        except Exception:
            pass
        try:
            return (resp.text or "")[:300]
        except Exception:
            pass
    return ""


# Frontend, kullanıcının mesajına o anki sekme durumunu ekler
# (`map-init.js::buildContext` → "[TAB_CONTEXT …] Sistem: Uptime=… [/TAB_CONTEXT]").
# Blok **o tur için** modele gider; geçmişe girmesi iki ayrı arıza üretir:
#   ① Ekranda görünür. Etiket "sadece sen gör" dediği hâlde kullanıcı kendi
#      balonunda okur — uygulama yeniden açılınca geçmiş diskten yüklendiği için
#      her mesajda (ölçüldü 2026-09-20).
#   ② Bayat veri modele taze diye gider. Dünkü "Uptime=00:40:56 / BTC=…" satırı
#      geçmişte durur ve sonraki turlarda güncel bağlam gibi okunur.
# Bu yüzden blok kayda girmeden kesilir — canlı tura dokunulmaz.
# Desen tek yerde (memory.sekme_baglamini_ayikla): hafıza servisleri de aynısını kullanır.
def _strip_tab_context(content: str) -> str:
    from app.services.memory import sekme_baglamini_ayikla
    return sekme_baglamini_ayikla(content)


def _gecmis_anahtari() -> str:
    """Araç defterinin anahtarı: konuşma geçmişiyle aynı (aktif karakter)."""
    try:
        from app.services.personas import get_persona
        return get_persona()
    except Exception:
        return "yuki"


def _get_history() -> list[dict]:
    """Aktif karakterin konuşma geçmişini döndürür (ilk erişimde diskten yükler)."""
    from app.services.personas import get_persona
    from app.services import lite_memory
    key = get_persona()
    if key not in _histories:
        gecmis = lite_memory.load_history(key)
        # Eski kayıtlar bu temizlikten önce yazılmış olabilir — yüklerken de süz,
        # yoksa düzeltme yalnız yeni mesajlara uygulanır ve kullanıcı kendi eski
        # geçmişinde etiketi görmeye devam eder.
        for m in gecmis:
            if m.get("role") == "user" and "[TAB_CONTEXT" in (m.get("content") or ""):
                m["content"] = _strip_tab_context(m["content"])
        _histories[key] = gecmis
    return _histories[key]


def _add_message(role: str, content: str) -> None:
    from app.services.personas import get_persona
    from app.services import lite_memory
    if role == "user":
        content = _strip_tab_context(content)
    h = _get_history()
    h.append({"role": role, "content": content})
    if len(h) > MAX_HISTORY:
        h.pop(0)
    key = get_persona()
    lite_memory.save_history(key, h)
    # Orta seviye hafıza (pgvector yokken): her N kullanıcı mesajında profil özetini tazele
    if role == "user" and not _semantic_active() and lite_memory.note_user_message(key):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None  # sync bağlam (test) — özet N mesaj sonra tekrar denenir
        if loop:
            loop.create_task(_update_lite_profile(key))


async def _update_lite_profile(character_key: str) -> None:
    """Profil özetini LLM ile güncelle (BYOK; anahtar yoksa quick_ask '' döner → no-op)."""
    from app.services import lite_memory
    history = list(_histories.get(character_key) or [])
    if not history:
        return
    prompt = lite_memory.build_profile_prompt(lite_memory.get_profile(character_key), history)
    summary = await quick_ask(prompt, system="Sen kullanıcı profili özetleyen bir yardımcısın.")
    if summary:
        lite_memory.set_profile(character_key, summary)


# ------------------------------------------------------------------ #
# Emotion tag parser
# ------------------------------------------------------------------ #


def _parse_tags(text: str) -> tuple[str, EmotionTag, str]:
    """Metin içindeki [EMOTION:...] ve [BEHAVIOR:...] etiketlerini temizle ve ayıkla."""
    emotion = EmotionTag()
    behavior = "idle"

    # Duygu yakala
    emo_match = re.search(r'[\[\(]EMOTION:\s*({[^}]+})[\]\)]', text)
    if emo_match:
        try:
            d = json.loads(emo_match.group(1))
            emotion = EmotionTag(emotion=d.get("emotion", "neutral"), intensity=float(d.get("intensity", 0.5)))
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.debug("EMOTION parse: %s", e)

    # Davranış yakala (JSON formatı)
    beh_match = re.search(r'[\[\(]BEHAVIOR:\s*({[^}]+})[\]\)]', text)
    if beh_match:
        try:
            d = json.loads(beh_match.group(1))
            behavior = d.get("action", "idle")
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.debug("BEHAVIOR parse: %s", e)
    else:
        # Fallback: LLM bare string çıkardıysa — metin sonunda
        _ACTIONS = r'wave|nod|shake|bow|think|shy|surprised|idle'
        bare_match = re.search(rf'"?({_ACTIONS})"?\s*$', text, re.IGNORECASE)
        if bare_match:
            behavior = bare_match.group(1).lower()

    # Temiz metin
    clean = re.sub(r'[\[\(](?:EMOTION|BEHAVIOR):\s*\{[^}]*\}\s*[\]\)]', '', text)
    _ACTIONS_PAT = r'wave|nod|shake|bow|think|shy|surprised|idle|thinking'
    clean = re.sub(rf'\n?"?(?:{_ACTIONS_PAT})"?\s*$', '', clean, flags=re.IGNORECASE).strip()
    return clean, emotion, behavior


# ------------------------------------------------------------------ #
# Memory-aware context builder (Faz 3)
# ------------------------------------------------------------------ #


def _semantic_memory_allowed() -> bool:
    """Semantik hafıza (Ultra P7 paywall) bu lisansta açık mı?

    Ürün: Free/Pro → False · Ultra → True · dev YUKI_PACKAGE=full → True.
    Hata → False (Ultra sızmasın). SaaS/kişisel pgvector'de env-full = daima True."""
    try:
        from app.services import yetki
        return yetki.feature_allowed("semantic_memory")
    except Exception:
        return False


def _embedding_engine_ready() -> bool:
    """Embedding motoru gerçekten çalışabilir durumda mı?

    Ürün paketinde model indir-gerektiğinde gelir: kullanıcı indirmeyi iptal
    ettiyse/yarım kaldıysa dosya yoktur. Bunu kontrol etmezsek Ultra kullanıcısı
    hafızasız kalmak yerine **hiç sohbet edemez** (embedding çağrısı 500 verir).
    `EMBED_BACKEND=st` (geliştirme) → sentence-transformers, dosya şartı yok."""
    try:
        from app.config import EMBED_BACKEND
        if EMBED_BACKEND == "st":
            return True
        from app.services import embedding_onnx
        if embedding_onnx.available():
            return True
        # auto modunda ONNX yoksa sentence-transformers'a düşülebilir (dev makine)
        if EMBED_BACKEND == "auto":
            import importlib.util
            return importlib.util.find_spec("sentence_transformers") is not None
        return False
    except Exception:
        return False


def _semantic_active() -> bool:
    """Bu istek için gerçek semantik hafıza (sqlite-vec/pgvector) aktif mi.

    MEMORY_ENABLED (config: DB var mı) AND Ultra entitlement AND embedding motoru
    hazır. False ise lite_memory. Mevcut configlerde davranış korunur:
    pgvector-full → MEMORY_ENABLED ile aynı; MEMORY_ENABLED=False → yine False.
    Ürün-sqlite + Free/Pro'da ve model-indirilmemiş Ultra'da lite'a düşer."""
    return MEMORY_ENABLED and _semantic_memory_allowed() and _embedding_engine_ready()


async def _build_context(message: str) -> tuple[str, list[dict]]:
    """Sistem promptu ve mesaj geçmişini hazırla."""
    _dt_suffix = f"\n\n## Şu Anki Zaman\n{get_current_datetime()}"
    if not _semantic_active():
        # build_system_prompt() → aktif dile göre üretir (statik sabit değil)
        from app.services.personas import get_persona
        from app.services import lite_memory
        profile = lite_memory.get_profile(get_persona())
        if profile:
            _dt_suffix += f"\n\n## Kullanıcı Hakkında Bilinenler (kalıcı hafıza)\n{profile}"
        return build_system_prompt() + _dt_suffix, list(_get_history())

    from app.services.memory import get_memory_service, _get_active_character
    from app.config import MEMORY_GLOBAL_CHARACTERS
    mem = get_memory_service()

    # Global hafıza: aktif karakter (örn. Yuki) TÜM karakterlerin anılarını okur.
    active_char = _get_active_character()
    is_global = active_char in MEMORY_GLOBAL_CHARACTERS

    relevant = await mem.search(
        message,
        limit=MEMORY_SEARCH_LIMIT,
        session_id=SESSION_ID,
        min_similarity=MEMORY_MIN_SIMILARITY,
        cross_character=is_global,
    )

    # Reinforcement: erişilen anıların önemini arka planda artır
    if relevant:
        asyncio.create_task(
            mem.reinforce([m.id for m in relevant], delta=0.03)
        )

    # Global modda başka karakterle konuşulan anıyı kaynağıyla etiketle
    def _src_tag(m) -> str:
        if not is_global or not m.character_key or m.character_key == active_char:
            return ""
        try:
            from app.services.personas import get_persona_meta
            label = get_persona_meta(m.character_key).get("label", m.character_key)
        except Exception:
            label = m.character_key
        return f"[{label}'yla konuşulan] "

    # İkinci kapı da SABİT değil GÖRELİ (0.4/0.55 sabitleri TR'de doğru anıyı
    # eliyordu — bkz. memory_gate.py). Konuşma anıları gürültülü olduğu için
    # olgu/tercihe göre daha dar bir aralık alır.
    from app.config import MEMORY_REL_RATIO
    from app.services.memory_gate import relative_cutoff
    best_sim = max((m.similarity for m in relevant), default=0.0)
    fact_gate = relative_cutoff(best_sim, MEMORY_MIN_SIMILARITY, MEMORY_REL_RATIO)
    conv_gate = relative_cutoff(best_sim, MEMORY_MIN_SIMILARITY + 0.10, 0.85)

    memory_ctx_parts: list[str] = []
    for m in relevant:
        if m.category in ("preference", "fact") and m.similarity >= fact_gate:
            memory_ctx_parts.append(f"- {_src_tag(m)}{m.content}")
        elif m.category == "conversation" and m.similarity >= conv_gate:
            memory_ctx_parts.append(f"- {_src_tag(m)}({m.role}) {m.content}")

    # Meta-recall (global hafıza): kullanıcı başka bir karakterin ADINI andıysa,
    # o karakterin son konuşmaları semantik skordan BAĞIMSIZ olarak eklenir.
    # "X'e ne söylemiştim?" gibi meta-sorular içerik embedding'iyle eşleşmez
    # (içerik '150 yıl yaşam', soru 'X'e ne dedim' → uzak) — bu katman ismi
    # yakalar ve o karakterin son anılarını Yuki'nin bağlamına taşır.
    if is_global:
        try:
            from app.services.personas import get_persona_meta
            from app.services.memory import VALID_CHARACTERS
            msg_low = message.lower()
            for ckey in VALID_CHARACTERS:
                if ckey == active_char:
                    continue
                label = str(get_persona_meta(ckey).get("label", ckey))
                named = re.search(rf"\b{re.escape(ckey)}\b", msg_low) or \
                        re.search(rf"\b{re.escape(label.lower())}\b", msg_low)
                if not named:
                    continue
                others = await mem.get_recent(
                    limit=4, session_id=SESSION_ID,
                    category="conversation", character_key=ckey,
                )
                for m in others:
                    if m.role not in ("user", "assistant"):
                        continue
                    line = f"- [{label}'yla konuşulan] ({m.role}) {m.content}"
                    if line not in memory_ctx_parts:
                        memory_ctx_parts.append(line)
        except Exception:
            pass

    memory_ctx = "\n".join(memory_ctx_parts)
    system_prompt = build_system_prompt(memory_ctx)

    # E3: Gerekirse eski mesajları özetle
    await _maybe_summarize(SESSION_ID)

    recent = await mem.get_recent(limit=MEMORY_RECENT_LIMIT, session_id=SESSION_ID)
    messages = [
        {"role": m.role, "content": m.content}
        for m in recent
        if m.role in ("user", "assistant")
    ]

    return system_prompt + _dt_suffix, messages


# ------------------------------------------------------------------ #
# E2: Model routing — basit → fast, karmaşık/tool → strong
# ------------------------------------------------------------------ #

_TOOL_HINT_KEYWORDS = [
    "dosya", "ekran", "aç", "çalıştır", "liste", "oku", "yaz", "sil", "kopyala",
    "file", "open", "run", "list", "show", "directory", "screenshot", "execute",
]


def _route_model(message: str) -> str:
    """Mesaj karmaşıklığına göre model seç.

    Runtime model seçili → onu kullan (otomatik routing devre dışı).
    Yerel mod → OLLAMA_MODEL (değişmez).
    Basit mesaj (≤80 karakter, araç ipucu yok) → LLM_MODEL_FAST.
    Karmaşık / araç ipucu var → LLM_MODEL_STRONG (yoksa LLM_MODEL).
    """
    if USE_LOCAL_LLM:
        return OLLAMA_MODEL
    # Runtime'da kullanıcı model seçtiyse otomatik routing atlanır
    if _kullanici_model_secti():
        return _runtime_model
    if not _fast_strong_gecerli():
        return _runtime_model or LLM_MODEL
    strong = LLM_MODEL_STRONG or LLM_MODEL
    lower = message.lower()
    has_tool_hint = any(kw in lower for kw in _TOOL_HINT_KEYWORDS)
    hedef = LLM_MODEL_FAST if (len(message) <= 80 and not has_tool_hint) else strong
    # Aktif model ücretsizse hız/güç yönlendirmesi ücretli modele atlamamalı
    aktif = _runtime_model or LLM_MODEL
    if _ucretsiz_model(aktif) and not _ucretsiz_model(hedef):
        return aktif
    return hedef


def _kullanici_model_secti() -> bool:
    """Aktif model kullanıcının açık tercihi mi?

    İki sinyal: ① panelden `set_runtime_config` çağrıldı ② config varsayılanından
    farklı bir model aktif. ②'yi tek başına kullanmak restart sonrası bozuluyordu.
    """
    return _model_explicitly_set or _runtime_model != LLM_MODEL


def _fast_strong_gecerli() -> bool:
    """`LLM_MODEL_FAST` / `LLM_MODEL_STRONG` aktif sağlayıcıda anlamlı mı?

    🔴 2026-08-08'de ölçüldü: bu iki değişkenin varsayılanları **OpenRouter model
    ID'leridir** (`openai/gpt-4o-mini`). Kullanıcı Google/Ollama/başka bir
    sağlayıcı seçtiğinde ve **yeniden başlattığında** `_kullanici_model_secti()`
    False'a düşer (BYOK paneli seçilen modeli `.env`'e de yazdığı için
    `_runtime_model == LLM_MODEL` olur) → yönlendirme sessizce
    `openai/gpt-4o-mini` gönderir ve sağlayıcı 404 verir. Sohbet ilk mesajda ölür.

    Kural: hız/güç yönlendirmesi yalnız bu ID'lerin ait olduğu sağlayıcıda —
    OpenRouter'da — geçerlidir. Başka sağlayıcıda aktif model olduğu gibi kullanılır.
    """
    return (_runtime_provider or _lp.VARSAYILAN) == _lp.VARSAYILAN


def _ucretsiz_model(model: str) -> bool:
    return (model or "").endswith(":free")


def _background_model(tercih: str) -> str:
    """Arka plan işleri (özetleme, olgu çıkarımı) için model seç.

    🔴 2026-08-01 dersi: bu işler `LLM_MODEL_FAST`/`LLM_MODEL_STRONG` varsayılanlarına
    sabitlenmişti — ikisi de ÜCRETLİ (`gpt-4o-mini` / `gpt-4.1-mini`). Kullanıcı BYOK
    panelinden ücretsiz bir model seçse bile bu iki yol ücretli kapıyı çalıyordu;
    kredisiz anahtarda sessizce başarısız oluyor, yani sohbet çalışırken **hafıza ve
    özet çalışmıyordu**. Geliştiricinin anahtarında kredi olduğu için görünmüyordu.

    Kural `_route_model`'inkiyle aynı: kullanıcı açıkça bir model seçtiyse her yerde o
    geçerlidir. Seçmediyse config tercihi kullanılır — ama aktif model ÜCRETSİZ ise
    arka planı sessizce ücretli bir modele kaydırmak yasak (ikinci güvenlik ağı: seçim
    sinyali bir şekilde kaybolsa bile kredisiz kullanıcı çalışmaya devam eder).
    """
    # Seçili sağlayıcının OpenAI-uyumlu ucundan giden yan iş (Anthropic): ucuz yan model.
    # `_yan_istemci` ile aynı koşul — istemci ile model aynı sağlayıcıda kalır.
    sag = _yan_uyumlu()
    if sag is not None and sag.yan_model:
        return sag.yan_model
    if _kullanici_model_secti():
        return _runtime_model
    aktif = _runtime_model or LLM_MODEL
    # Aktif sağlayıcı OpenRouter değilse `tercih` (FAST/STRONG) o sağlayıcıda
    # olmayan bir ID'dir → arka plan işleri sessizce 404 alırdı.
    if not _fast_strong_gecerli():
        return aktif
    if _ucretsiz_model(aktif) and not _ucretsiz_model(tercih):
        return aktif
    return tercih or LLM_MODEL


# ------------------------------------------------------------------ #
# E4: Token sayacı
# ------------------------------------------------------------------ #

_session_tokens: dict[str, int] = {"prompt": 0, "completion": 0}
_last_summarize_time: float = 0.0


def get_token_stats() -> dict[str, int]:
    """Oturum genelindeki toplam token kullanımını döner."""
    return dict(_session_tokens)


def _log_tokens(prompt: int, completion: int) -> None:
    _session_tokens["prompt"] += prompt
    _session_tokens["completion"] += completion
    total = prompt + completion
    session_total = _session_tokens["prompt"] + _session_tokens["completion"]
    logger.info("token istek=%dp+%dc=%d | oturum=%d", prompt, completion, total, session_total)


# ------------------------------------------------------------------ #
# E1: Prompt caching — cache_control destekli mesaj listesi oluştur
# ------------------------------------------------------------------ #


def _apply_cache_control(messages: list[dict]) -> list[dict]:
    """PROMPT_CACHE_ENABLED=true ise sistem mesajına cache_control ekler.

    OpenRouter üzerinden Anthropic/destekleyen modellerde prompt caching sağlar.
    Desteklemeyen modeller bu alanı sessizce yoksayar.
    """
    if not PROMPT_CACHE_ENABLED or not messages:
        return messages
    first = messages[0]
    if first.get("role") != "system" or not isinstance(first.get("content"), str):
        return messages
    cached = [
        {
            "role": "system",
            "content": [
                {"type": "text", "text": first["content"], "cache_control": {"type": "ephemeral"}}
            ],
        }
    ] + messages[1:]
    return cached


# ------------------------------------------------------------------ #
# E3: Konuşma özetleme — MEMORY_RECENT_LIMIT aşıldığında eski mesajları özetle
# ------------------------------------------------------------------ #


def _yanit_dili() -> str:
    from app.config import yanit_dili
    return yanit_dili()


async def _maybe_summarize(session_id: str) -> None:
    """Context window dolduğunda eski mesajların ilk yarısını özetle ve sil.

    Yalnızca SUMMARIZE_ENABLED=true ve MEMORY_ENABLED=true durumunda çalışır.
    Ardışık çağrıları önlemek için 5 dakika debounce uygulanır.
    """
    if not SUMMARIZE_ENABLED or not _semantic_active():
        return

    global _last_summarize_time
    if time.monotonic() - _last_summarize_time < 300:  # 5 dakika cooldown
        return
    _last_summarize_time = time.monotonic()

    from app.services.memory import get_memory_service
    mem = get_memory_service()

    recent = await mem.get_recent(limit=MEMORY_RECENT_LIMIT + 1, session_id=session_id)
    if len(recent) < MEMORY_RECENT_LIMIT:
        return

    cutoff = len(recent) // 2
    to_summarize = recent[:cutoff]
    if not to_summarize:
        return

    conversation_text = "\n".join(
        f"{m.role.upper()}: {m.content}" for m in to_summarize
    )

    client = _yan_istemci()
    strong = _background_model(LLM_MODEL_STRONG or LLM_MODEL)
    try:
        resp = await client.chat.completions.create(
            model=strong,
            max_tokens=200,
            messages=[
                {"role": "system", "content": f"Aşağıdaki konuşmayı 2-3 cümleyle özetle (dil: {_yanit_dili()}). Sadece özeti yaz."},
                {"role": "user", "content": conversation_text},
            ],
            timeout=15.0,
        )
        summary = resp.choices[0].message.content or ""
        if resp.usage:
            _log_tokens(resp.usage.prompt_tokens, resp.usage.completion_tokens)

        if summary:
            await mem.add(
                content=f"[ÖZET] {summary}",
                role="assistant",
                category="conversation",
                importance=0.65,
                session_id=session_id,
                scope="conversation",
            )
            from app.db.connection import get_pool
            pool = await get_pool()
            if pool:
                ids = [m.id for m in to_summarize]
                async with pool.acquire() as conn:
                    await conn.execute(
                        "DELETE FROM memories WHERE id = ANY($1::int[])", ids
                    )
            logger.info("Özetlendi: %d mesaj → 1 özet kaydedildi.", len(to_summarize))
    except Exception as e:
        logger.warning("Özetleme hatası: %s", e)


# ------------------------------------------------------------------ #
# Otomatik scope tespiti (Faz C — keyword matching, LLM çağrısız)
# ------------------------------------------------------------------ #

_SCOPE_KEYWORDS: dict[str, list[str]] = {
    "preference": [
        "seviyorum", "sevmiyorum", "tercih", "hoşlanıyorum", "hoşlanmıyorum",
        "favorim", "en sevdiğim", "beğeniyorum", "nefret", "bıktım",
        "i like", "i love", "i hate", "i prefer", "my favorite",
    ],
    "fact": [
        "benim adım", "adım", "yaşıyorum", "yaşındayım", "mesleğim",
        "çalışıyorum", "doğum günüm", "öğrenciyim", "memleketim",
        "my name is", "i live in", "i work", "i am a", "my birthday",
    ],
    "skill": [
        "nasıl yapılır", "öğret", "adımlar", "yöntem", "prosedür",
        "how to", "tutorial", "steps to", "guide",
    ],
}


def _detect_scope(text: str) -> str:
    """Metinden scope çıkar. Eşleşme yoksa 'conversation' döner."""
    lower = text.lower()
    for scope, keywords in _SCOPE_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return scope
    return "conversation"


# ------------------------------------------------------------------ #
# Self-learning: arka plan fact çıkarımı (LLM tabanlı)
# ------------------------------------------------------------------ #

_EXTRACT_PROMPT = """\
Kullanıcının mesajından kişisel bilgi, tercih veya öğrenilen beceri çıkar.
Yalnızca açıkça belirtilen bilgileri listele. Tahmin yapma.
Çıktı: JSON array — [{"type": "fact|preference|skill", "content": "..."}]
Yoksa: []"""


async def _extract_facts_background(user_msg: str) -> None:
    """Kullanıcı mesajından arka planda fact/preference/skill çıkar ve kaydet.

    asyncio.create_task() ile fire-and-forget çağrılır — yanıtı geciktirmez.
    Başarısız olursa yanıt kesilmez ama hata WARNING olarak loglanır — bu çağrının
    sessizce ölmesi Ultra'nın satılan hafızasının çalışmaması demektir.
    """
    if not _semantic_active():
        return
    try:
        client = _yan_istemci()
        resp = await client.chat.completions.create(
            model=_background_model(LLM_MODEL_FAST),
            max_tokens=150,
            messages=[
                {"role": "system", "content": _EXTRACT_PROMPT},
                {"role": "user", "content": user_msg[:500]},
            ],
            timeout=8.0,
        )
        raw = (resp.choices[0].message.content or "").strip()
        if resp.usage:
            _log_tokens(resp.usage.prompt_tokens, resp.usage.completion_tokens)

        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if not match:
            return
        items = json.loads(match.group())
        if not isinstance(items, list) or not items:
            return

        from app.services.memory import get_memory_service
        mem = get_memory_service()
        to_save = []
        for item in items[:5]:
            if not isinstance(item, dict):
                continue
            fact_type = item.get("type", "fact")
            content = item.get("content", "").strip()
            if not content or len(content) < 8:
                continue
            scope = fact_type if fact_type in ("fact", "preference", "skill") else "fact"
            importance = {"fact": 0.80, "preference": 0.85, "skill": 0.75}.get(scope, 0.80)
            to_save.append({
                "content": content,
                "role": "user",
                "category": scope,
                "importance": importance,
                "scope": scope,
            })

        if to_save:
            await mem.add_batch(to_save, session_id=SESSION_ID)
            logger.info("Fact çıkarımı: %d yeni kayıt eklendi.", len(to_save))
    except Exception as e:
        # ⚠️ Eskiden debug + "(normal)" idi. Normal DEĞİL: bu çağrı ölürse hafızaya
        # hiçbir olgu yazılmaz ve kullanıcı bunu yalnız "Yuki beni hatırlamıyor"
        # diye fark eder. Görünür seviyede kalsın.
        logger.warning("Fact çıkarımı başarısız — hafızaya kayıt yapılamadı: %s", e)


async def _save_exchange(user_msg: str, assistant_reply: str) -> None:
    """Kullanıcı ve asistan mesajını DB'e kaydet (batch embed — tek seferde)."""
    if not _semantic_active():
        return
    from app.services.memory import get_memory_service
    mem = get_memory_service()

    # Sekme bloğu burada da kesilir (hafıza servisi zaten keser): kapsam tespiti, ">20
    # karakter" eşiği ve fact çıkarımı bloğu görmesin. Blok her mesajda olduğu için eşik
    # "naber" için bile aşılıyor, her mesaj kullanıcının anahtarından ek bir LLM çağrısı
    # yapıyordu (ölçüldü 2026-09-27).
    user_msg = _strip_tab_context(user_msg)
    if not user_msg:
        return

    user_scope = _detect_scope(user_msg)
    # Soru bilgi değildir: "En sevdiğim renk ne?" anahtar kelimeye takılıp preference
    # olarak kaydediliyordu (kişiselde cbbc581, üründe 2026-09-27 ölçüldü).
    if user_scope != "conversation" and user_msg.rstrip().endswith("?"):
        user_scope = "conversation"
    importance_map = {"preference": 0.8, "fact": 0.75, "skill": 0.7, "conversation": 0.5}
    user_imp = importance_map.get(user_scope, 0.5)

    await mem.add_batch([
        {"content": user_msg, "role": "user", "category": user_scope, "importance": user_imp, "scope": user_scope},
        # Yuki'nin cevabı HER ZAMAN konuşmadır. Kullanıcının kapsamını izlediğinde "Adını
        # kaydettim, Deniz!" gibi onaylar "senin hakkında bilgi" diye birikiyordu.
        {"content": assistant_reply, "role": "assistant", "category": "conversation", "importance": 0.5, "scope": "conversation"},
    ])

    # Conversation scope mesajlarında arka planda LLM fact çıkarımı yap
    if user_scope == "conversation" and len(user_msg) > 20:
        asyncio.create_task(_extract_facts_background(user_msg))


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #


async def chat_sync(message: str) -> ChatResponse:
    """Mesaj gönder, tam yanıt + duygu etiketi al."""
    system_prompt, messages = await _build_context(message)
    system_prompt += kullanici_metni_notu(message)
    target_model = _route_model(message)  # E2

    if not _semantic_active():
        _add_message("user", message)

    client = _get_client()
    if not _semantic_active():
        full_messages = [{"role": "system", "content": system_prompt}] + list(_get_history())
    else:
        full_messages = [{"role": "system", "content": system_prompt}] + messages + [{"role": "user", "content": message}]

    full_messages = _apply_cache_control(full_messages)  # E1

    try:
        response = await client.chat.completions.create(
            model=target_model,
            max_tokens=1024,
            messages=full_messages,
        )
    except Exception as e:
        # Geçersiz/iptal edilmiş anahtar burada 401 olarak gelir. Eskiden yakalanmıyordu
        # → FastAPI 500 "Internal Server Error" dönüyordu (kullanıcı sebebi göremiyordu).
        logger.error("chat_sync LLM hatası: %s: %s", type(e).__name__, e)
        raise LLMUserError(
            llm_error_message(e) or M("llm.baglanamadi-tekrar")
        ) from e

    # E4: Token log
    if response.usage:
        _log_tokens(response.usage.prompt_tokens, response.usage.completion_tokens)

    raw_text = response.choices[0].message.content or ""
    clean_text, emotion, _ = _parse_tags(raw_text)

    if _semantic_active():
        await _save_exchange(message, clean_text)
    else:
        _add_message("assistant", clean_text)

    return ChatResponse(text=clean_text, emotion=emotion)


_active_cancel_token: CancellationToken | None = None


def get_active_cancel_token() -> CancellationToken | None:
    """Aktif runner'ın cancellation token'ını döndürür."""
    return _active_cancel_token


async def chat_stream(
    message: str,
    cancel_token: CancellationToken | None = None,
) -> AsyncGenerator[str, None]:
    """Streaming yanıt — SSE, token bazlı. Hibrit Zeka (Yerel + Bulut Fallback)."""
    global _active_cancel_token

    # ── MOD PRE-TRIGGER: LLM hallucination bypass ────────────────────────
    # Mesaj kesin mod keyword'üyle eşleşiyorsa LLM'e gitmeden direkt çalıştır.
    # LLM "başlatıldı" deyip aslında hiçbir şey yapmama sorununu giderir.
    try:
        from app.services.tools.modes import find_mode_by_trigger, start_mode as _start_mode_direct
        _pre_mode = find_mode_by_trigger(message)
        if _pre_mode and _pre_mode.get("id"):
            logger.info("mod pre-trigger: '%s' → start_mode(%s)", message, _pre_mode["id"])
            result = await _start_mode_direct(_pre_mode["id"])
            arac_gecmisi.ekle(_gecmis_anahtari(), message, [("start_mode", {"mode_id": _pre_mode["id"]}, result)])
            if _semantic_active():
                await _save_exchange(message, result)
            else:
                _add_message("user", message)
                _add_message("assistant", result)
            yield result
            return
    except Exception as _pt_err:
        logger.warning("mod pre-trigger hata (atlanıyor): %s", _pt_err)

    system_prompt, history = await _build_context(message)
    system_prompt += kullanici_metni_notu(message)

    if not _semantic_active():
        _add_message("user", message)
        full_messages = [{"role": "system", "content": system_prompt}] + list(_get_history())
    else:
        full_messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": message}]
    full_messages = _apply_cache_control(full_messages)  # E1

    # ── CLAUDE CODE CLI MOD ──────────────────────────────────────────────
    if _runtime_provider == "claude_code" and not USE_LOCAL_LLM:
        logger.info("CLAUDE CODE MOD aktif")
        collected: list[str] = []
        try:
            async for chunk in _stream_claude_code(system_prompt, history, message, cancel_token):
                collected.append(chunk)
                yield chunk
        except Exception as e:
            logger.error("Claude Code stream hatası: %s", e)
            yield M("llm.hata-onek", mesaj=M("llm.claude-code-baglanti", sebep=e))
        full_text = "".join(collected)
        if full_text and _semantic_active():
            clean, _, _ = _parse_tags(full_text)
            await _save_exchange(message, clean)
        elif full_text and not _semantic_active():
            clean, _, _ = _parse_tags(full_text)
            _add_message("assistant", clean)
        return

    # ── ANTHROPIC DİREKT MOD ─────────────────────────────────────────────
    if _runtime_provider == "anthropic" and not USE_LOCAL_LLM:
        logger.info("ANTHROPİC MOD: %s", _runtime_model)
        collected: list[str] = []
        try:
            async for chunk in _stream_anthropic(system_prompt, history, message, cancel_token):
                collected.append(chunk)
                yield chunk
        except Exception as e:
            logger.error("Anthropic stream hatası: %s", e)
            yield M("llm.hata-onek", mesaj=M("llm.anthropic-baglanti", sebep=e))
        full_text = "".join(collected)
        if full_text and _semantic_active():
            clean, _, _ = _parse_tags(full_text)
            await _save_exchange(message, clean)
        elif full_text and not _semantic_active():
            clean, _, _ = _parse_tags(full_text)
            _add_message("assistant", clean)
        return

    # ── YEREL MOD (Ollama) — tools yok, streaming var ──────────────────
    if USE_LOCAL_LLM:
        logger.info("YEREL MOD: Streaming başlatılıyor (Model: %s)...", OLLAMA_MODEL)
        client = _get_client(force_cloud=False)
        try:
            stream = await asyncio.wait_for(
                client.chat.completions.create(
                    model=OLLAMA_MODEL,
                    messages=full_messages,
                    stream=True,
                ),
                timeout=20.0,
            )
            collected: list[str] = []
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    collected.append(delta.content)
                    yield delta.content

            full_text = "".join(collected)
            if full_text and _semantic_active():
                clean, _, _ = _parse_tags(full_text)
                await _save_exchange(message, clean)
            elif full_text and not _semantic_active():
                # Hafif hafızada kullanıcı mesajı yukarıda yazıldı; cevap da yazılmazsa
                # geçmişte yalnız kullanıcı kalır ve model kendi cevaplarını görmez.
                clean, _, _ = _parse_tags(full_text)
                _add_message("assistant", clean)
            return

        except (asyncio.TimeoutError, Exception) as e:
            logger.warning("Yerel zeka başarısız (%s: %s), buluta geçiliyor...", type(e).__name__, e)

    # ── BULUT MODU (OpenRouter) — LLMRunner ─────────────────────────────
    routed_model = _route_model(message)  # E2
    logger.info("BULUT MODU: LLMRunner başlatılıyor (Model: %s)...", routed_model)
    client = _get_client(force_cloud=True)

    token = cancel_token or CancellationToken()
    _active_cancel_token = token

    # Araç şeması tur başına daraltılır (alan_secici): kullanıcının cümlesinin
    # alanları + gerçekten kullanılmış çekirdek. `sema_sec` verilen listeye
    # DOKUNMAZ, yeni liste döndürür. Kapatma: YUKI_TAM_SEMA=1.
    aktif_araclar = get_active_tools()
    try:
        from app.services.tools.alan_secici import sema_sec, yonlendirme_notu
        tur_semasi = sema_sec(message, aktif_araclar)
        # Daraltma yapıldıysa modele yedek yolu söyle — yoksa eksik aracı fark
        # etmez, dolambaçlı yol dener (sessiz yeteneksizlik).
        not_ = yonlendirme_notu(tur_semasi, aktif_araclar)
        if not_ and full_messages and full_messages[0].get("role") == "system":
            ilk = dict(full_messages[0])
            if isinstance(ilk.get("content"), str):
                ilk["content"] += not_
                full_messages = [ilk] + full_messages[1:]
    except Exception as e:  # seçici bozulursa yetenek kaybı olmamalı
        logger.warning("alan seçici başarısız (%s) — tam şema gönderiliyor", e)
        tur_semasi = aktif_araclar

    runner = LLMRunner(
        client=client,
        model=routed_model,
        tools=tur_semasi,
        max_steps=5,
        cancel_token=token,
    )

    collected_tokens: list[str] = []

    # Önceki turların araç kaydı yalnız bu isteğin son kullanıcı mesajına eklenir, geçmişe yazılmaz.
    _defter_anahtari = _gecmis_anahtari()
    if full_messages and full_messages[-1].get("role") == "user" and isinstance(full_messages[-1].get("content"), str):
        full_messages = full_messages[:-1] + [{
            **full_messages[-1],
            "content": arac_gecmisi.mesaja_ekle(_defter_anahtari, full_messages[-1]["content"]),
        }]

    try:
        async for chunk in runner.run(full_messages):
            if token.is_cancelled:
                break
            yield chunk
            collected_tokens.append(chunk)

        full_text = "".join(collected_tokens)
        if full_text:
            clean, _, _ = _parse_tags(full_text)
            if _semantic_active():
                await _save_exchange(message, clean)
            else:
                _add_message("assistant", clean)

        # Kaçırılan araç: bu turda hiç araç çalışmadıysa ve isteğin bir aracı
        # varsa kart ile hatırlat. Cevaptan SONRA çalışır, yanıtı geciktirmez.
        try:
            from app.services.arac_ipucu import belki_hatirlat
            await belki_hatirlat(message, runner.total_tool_calls)
        except Exception:
            pass

    except Exception as e:
        import traceback
        logger.error("Hata: %s", traceback.format_exc())
        # Ham SDK hatasını kullanıcıya basma — tanınan sağlayıcı hataları için net TR mesaj.
        yield M("llm.hata-onek", mesaj=(llm_error_message(e) or M("llm.islem-sorunu")))
    finally:
        arac_gecmisi.ekle(_defter_anahtari, message, runner.arac_kayitlari)
        _active_cancel_token = None


def _convert_tools_anthropic(openai_tools: list[dict]) -> list[dict]:
    """OpenAI tool formatını Anthropic formatına çevirir."""
    result = []
    for tool in openai_tools:
        if tool.get("type") != "function":
            continue
        fn = tool["function"]
        result.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return result


#: 1024 kısa kalıyordu: uzun cevap kelime ortasında kesiliyor, araç girdisi yarım kalıyordu.
ANTHROPIC_MAX_TOKENS = 4096
#: Sistem metninin turdan tura değişmeyen öneki bu başlıkta biter (hafıza + saat sonra gelir).
SISTEM_SABIT_SINIRI = "## Hafıza Bağlamı"
_ONBELLEK = {"type": "ephemeral"}


def _anthropic_araclari() -> list[dict]:
    """Ad sırasında araç listesi, son araçta önbellek işareti.

    Sıra sabit olmazsa aynı araç kümesi farklı önbellek anahtarı üretir ve her turda tüm
    şema (on binlerce jeton) yeniden yazılır. Önbellek işareti araçları + öncesini kapsar.
    """
    araclar = sorted(_convert_tools_anthropic(get_active_tools()), key=lambda a: a["name"])
    if araclar:
        araclar[-1] = {**araclar[-1], "cache_control": _ONBELLEK}
    return araclar


def _anthropic_sistem(system_prompt: str) -> list[dict]:
    """Sistem metnini sabit önek (önbellekli) + değişen kuyruk (hafıza, saat) olarak böler."""
    onek, sinir, kuyruk = system_prompt.partition(SISTEM_SABIT_SINIRI)
    if not sinir or not onek:
        return [{"type": "text", "text": system_prompt}]
    return [
        {"type": "text", "text": onek, "cache_control": _ONBELLEK},
        {"type": "text", "text": sinir + kuyruk},
    ]


async def _stream_anthropic(
    system_prompt: str,
    history: list[dict],
    user_message: str,
    cancel_token: CancellationToken | None = None,
) -> AsyncGenerator[str, None]:
    """Anthropic SDK ile direkt streaming — tool calling destekli."""
    try:
        import anthropic as _anthropic
    except ImportError:
        yield M("llm.hata-onek", mesaj=M("llm.anthropic-paket-yok"))
        return

    # 🔴 Anahtar `llm_providers` deposundan okunur, modül global'inden DEĞİL:
    # BYOK panelinden girilen anahtar runtime'da oraya yazılır, import anındaki
    # global'e değil. Eskiden buraya yalnız .env'deki değer geliyordu → panelden
    # Anthropic anahtarı giren kullanıcı "anahtar ayarlanmamış" hatası alırdı.
    _ant_key = _lp.anahtar("anthropic") or ANTHROPIC_API_KEY
    if not _ant_key:
        yield M("llm.anthropic-anahtari-yok")
        return

    client = _anthropic.AsyncAnthropic(api_key=_ant_key)
    ant_tools = _anthropic_araclari()
    sistem = _anthropic_sistem(system_prompt)

    # Mesaj geçmişini Anthropic formatına çevir (system hariç)
    messages: list[dict] = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    defter_anahtari = _gecmis_anahtari()
    messages.append({"role": "user", "content": arac_gecmisi.mesaja_ekle(defter_anahtari, user_message)})
    arac_kayitlari: list[tuple[str, object, object]] = []
    try:
        async for parca in _anthropic_adimlari(client, ant_tools, sistem, messages, arac_kayitlari, cancel_token):
            yield parca
    finally:
        arac_gecmisi.ekle(defter_anahtari, user_message, arac_kayitlari)


async def _anthropic_adimlari(client, ant_tools, sistem, messages, arac_kayitlari, cancel_token):
    """Araç döngüsü. `arac_kayitlari` çalışan araçlarla dolar (defter için)."""
    from app.services.tools import call_tool
    from app.services.event_bus import bus
    from app.services.runner import arac_suresi

    yazildi = False
    for step in range(5):
        if cancel_token and cancel_token.is_cancelled:
            return

        # TEK çağrı: metin parçaları geldikçe akar, araç çağrıları ve `stop_reason` aynı
        # yanıttan okunur. (Eskiden önce `create` ile tam cevap üretilip atılıyor, sonra aynı
        # istek `stream` ile yeniden üretiliyordu → her cevap iki kez faturalanıyordu.)
        async with client.messages.stream(
            model=_runtime_model,
            max_tokens=ANTHROPIC_MAX_TOKENS,
            system=sistem,
            messages=messages,
            tools=ant_tools,
        ) as stream:
            async for text in stream.text_stream:
                if cancel_token and cancel_token.is_cancelled:
                    return
                if text:
                    yazildi = True
                yield text
            response = await stream.get_final_message()

        tool_uses = [b for b in response.content if b.type == "tool_use"]

        if getattr(response, "stop_reason", None) == "max_tokens":
            # Tavana takılan yanıtta araç girdisi YARIM olabilir (ör. write_file içeriğin
            # yarısıyla) — yürütme; metin zaten aktı, kesildiğini söyle.
            logger.warning("Anthropic cevabı max_tokens tavanında kesildi")
            yield M("llm.cevap-kesildi")
            return

        if not tool_uses:
            if not yazildi:
                # Model bazen yalnız düşünme bloğu üretip bitiriyor: sessiz kalma.
                logger.warning("Anthropic metinsiz yanıt: %s", [b.type for b in response.content])
                yield M("llm.bos-cevap")
            return          # cevap zaten akıtıldı

        if step < 4:
            # Tool çağrılarını çalıştır
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for tu in tool_uses:
                logger.info("Anthropic tool: %s", tu.name)
                await bus.publish("state_info", {"text": M("llm.arac-kullaniyor", arac=tu.name)})
                try:
                    res = await asyncio.wait_for(call_tool(tu.name, dict(tu.input)), timeout=arac_suresi(tu.name))
                except Exception as e:
                    res = f"Hata: {e}"
                arac_kayitlari.append((tu.name, dict(tu.input), res))
                # P1 E (denetim 10-06 H5): OpenAI-uyumlu yol `runner.py`'de maskeliyordu, bu yol
                # maskesizdi → Anthropic modunda okunan `.env`/token dosyası modele aynen gidiyordu.
                from app.services.credential_scrubber import scrub as _scrub
                from app.services.security import dis_icerik
                metin = str(res)
                if metin.startswith("SCREENSHOT_DATA:"):
                    # Ekran görüntüsü görsel blok olarak gider (runner yolundaki gibi); eskiden
                    # base64 metin olarak gidiyordu: model görmüyor, jeton yakıyordu.
                    icerik: object = [{"type": "image", "source": {
                        "type": "base64", "media_type": "image/jpeg", "data": metin.split(":", 1)[1]}}]
                else:
                    icerik = dis_icerik.bulguda_zarfla(tu.name, _scrub(metin))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": icerik,
                })
            messages.append({"role": "user", "content": tool_results})
        else:
            # Final yanıtı stream et
            # Adım tavanı doldu, model hâlâ araç istiyor: araçsız son bir cevap.
            async with client.messages.stream(
                model=_runtime_model,
                max_tokens=ANTHROPIC_MAX_TOKENS,
                system=sistem,
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    if cancel_token and cancel_token.is_cancelled:
                        return
                    if text:
                        yazildi = True
                    yield text
            if not yazildi:
                yield M("llm.bos-cevap")
            return


async def _stream_claude_code(
    system_prompt: str,
    history: list[dict],
    user_message: str,
    cancel_token: CancellationToken | None = None,
) -> AsyncGenerator[str, None]:
    """Claude Code CLI üzerinden yanıt — üyelik kullanır, API key gerekmez."""
    import shutil

    if not shutil.which("claude"):
        yield M("llm.hata-onek", mesaj=M("llm.claude-cli-yok"))
        return

    # Son 8 mesajı formatla
    ctx_lines: list[str] = []
    for m in history[-8:]:
        if m.get("role") == "user":
            ctx_lines.append(f"Kullanıcı: {m['content']}")
        elif m.get("role") == "assistant":
            ctx_lines.append(f"Yuki: {m['content']}")

    ctx = "\n".join(ctx_lines)
    if ctx:
        full_prompt = (
            f"{system_prompt}\n\n[Önceki Konuşma]\n{ctx}\n\n"
            f"[Şu An]\nKullanıcı: {user_message}\nYuki:"
        )
    else:
        full_prompt = f"{system_prompt}\n\nKullanıcı: {user_message}\nYuki:"

    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", full_prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=90.0)

        if proc.returncode != 0:
            err = stderr.decode(errors="replace")[:300]
            yield M("llm.hata-onek", mesaj=M("llm.claude-cli-hata", sebep=err or M("llm.bilinmeyen-hata")))
            return

        text = stdout.decode(errors="replace").strip()
        if not text:
            yield M("llm.yanit-alinamadi")
            return

        # Kelime kelime simüle edilmiş streaming
        words = text.split(" ")
        for i, word in enumerate(words):
            if cancel_token and cancel_token.is_cancelled:
                return
            yield word + (" " if i < len(words) - 1 else "")
            await asyncio.sleep(0.012)

    except asyncio.TimeoutError:
        yield M("llm.hata-onek", mesaj=M("llm.claude-cli-zaman-asimi", sn=90))
    except Exception as e:
        yield f"Hata: {e}"


async def clear_history(clear_pgvector: bool = True) -> None:
    """Aktif karakterin konuşma geçmişini temizle.

    clear_pgvector=False → semantik depoya dokunma. Depo backend'e göre seçilir
    (pgvector | sqlite-vec) — sqlite'ta vec tablosu da temizlenir.
    """
    from app.services.personas import get_persona
    from app.services import lite_memory
    _get_history().clear()
    arac_gecmisi.temizle(get_persona())
    lite_memory.clear_history(get_persona())  # diskteki kopya da gitsin (profil özeti KALIR)
    if clear_pgvector and _semantic_active():
        from app.services.memory import get_memory_service
        try:
            await get_memory_service().clear_conversations(SESSION_ID)
        except Exception as e:  # depo erişilemezse geçmiş temizliği yine de başarılı
            logger.warning("clear_history: semantik depo temizlenemedi: %s", e)

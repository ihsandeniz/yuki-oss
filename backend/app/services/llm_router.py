"""Hybrid LLM Router — OpenRouter ↔ Ollama circuit-breaker + fallback.

Neden bu modül?
  runner.py'deki _get_client() sadece config flag'ine bakıyor (USE_LOCAL_LLM).
  Ağ kesintisi, rate limit veya Ollama crash durumunda retry yok, circuit breaker yok.

Bu modül:
  1. Circuit Breaker   → provider art arda N kez başarısız → cooldown'a gir
  2. Health probe      → cooldown bitince tek istek → başarılıysa CLOSED'a dön
  3. Latency tracking → her çağrı p95 latency izlenir
  4. SOLID:
     - S: Router, CircuitBreaker, ProviderStats ayrı sorumluluklar
     - O: Yeni provider eklemek için LLMProvider subclass yeterli
     - L: LLMProvider örnekleri birbirinin yerine geçebilir
     - I: Dar arayüzler (complete / health_check)
     - D: LLMRouter somut provider'a değil LLMProvider arayüzüne bağımlı

Entegrasyon (runner.py):
  from app.services.llm_router import get_router
  client, model = await get_router().get_client(prefer_local=USE_LOCAL_LLM)
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import AsyncGenerator

import httpx
from openai import AsyncOpenAI

from app.services import llm_providers as _lp
from app.config import (
    LLM_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OPENROUTER_API_KEY,
    USE_LOCAL_LLM,
)

# OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1" — host kısmını ayır
_OLLAMA_HOST = OLLAMA_BASE_URL.rstrip("/v1").rstrip("/")

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Circuit Breaker
# ------------------------------------------------------------------ #

class CircuitState(Enum):
    CLOSED    = auto()   # normal — istekler geçiyor
    OPEN      = auto()   # arızalı — tüm istekler reddedilir
    HALF_OPEN = auto()   # recovery probe — tek istek izin verilir


@dataclass
class CircuitBreaker:
    """Sliding window circuit breaker.

    failure_threshold  : CLOSED → OPEN için art arda hata sayısı
    cooldown_seconds   : OPEN kalma süresi (sonra HALF_OPEN)
    success_threshold  : HALF_OPEN'da CLOSED'a dönmek için başarı sayısı
    """
    name: str
    failure_threshold: int = 3
    cooldown_seconds: float = 30.0
    success_threshold: int = 1

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _opened_at: float = field(default=0.0, init=False)

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._opened_at >= self.cooldown_seconds:
                logger.info("[CB:%s] OPEN → HALF_OPEN (cooldown bitti)", self.name)
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
        return self._state

    def allow_request(self) -> bool:
        """Bu provider'a istek gönderilebilir mi?"""
        s = self.state
        if s == CircuitState.CLOSED:
            return True
        if s == CircuitState.OPEN:
            return False
        # HALF_OPEN: sadece bir probe isteğine izin ver
        return True

    def record_success(self) -> None:
        self._failure_count = 0
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                logger.info("[CB:%s] HALF_OPEN → CLOSED", self.name)
                self._state = CircuitState.CLOSED
        # CLOSED'da success: sayaç reset zaten yapıldı

    def record_failure(self) -> None:
        self._failure_count += 1
        if self._state == CircuitState.HALF_OPEN:
            logger.warning("[CB:%s] HALF_OPEN → OPEN (probe başarısız)", self.name)
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            return
        if self._failure_count >= self.failure_threshold:
            logger.warning("[CB:%s] CLOSED → OPEN (%d hata)", self.name, self._failure_count)
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()


# ------------------------------------------------------------------ #
# Provider arayüzü (Dependency Inversion)
# ------------------------------------------------------------------ #

class LLMProvider(ABC):
    """LLM provider sözleşmesi — tüm provider'lar bu arayüzü uygular."""

    name: str = "base"

    @abstractmethod
    def get_client(self) -> AsyncOpenAI:
        """OpenAI uyumlu async istemci döndür."""
        ...

    @abstractmethod
    def get_model(self) -> str:
        """Kullanılacak model adını döndür."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Provider'ın erişilebilir olup olmadığını kontrol et."""
        ...


class BulutProvider(LLMProvider):
    """Kullanıcının seçtiği bulut sağlayıcısı (OpenRouter · OpenAI · Google · …).

    🔴 2026-08-05 — ÖNCEKİ HALİ BOZUKTU: istemci `__init__`'te, yani **modül
    import edilirken** kuruluyordu; `api_key=OPENROUTER_API_KEY` o anki (çoğu
    zaman BOŞ) değerdi. Sohbetin gerçek yolu bu router'dan geçtiği için, BYOK
    panelinden anahtar girmek `llm.py`'nin istemcisini tazeliyor ama **router'ınkini
    tazelemiyordu**: anahtarı girdikten sonra restart etmeden sohbet edilirse eski
    (anahtarsız) istemci kullanılıyordu. Singleton ilk sohbette kurulduğu için
    çoğu kullanıcıda gizli kaldı.

    Artık istemci `get_client()` anında, (sağlayıcı, anahtar) damgası değiştiyse
    yeniden kurulur — `llm.py::_get_client` ile aynı desen.
    """

    name = "bulut"

    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None
        self._damga: tuple | None = None

    def _aktif(self):
        from app.services import llm as _llm
        kimlik = _llm.aktif_saglayici()
        # Anthropic gibi kendi SDK'sı olan sağlayıcı, anahtarı varsa resmî
        # OpenAI-uyumlu ucundan kullanılır (ekip işçisi seçili sağlayıcıda kalır);
        # yoksa eski yedek: varsayılan sağlayıcı.
        return _lp.uyumlu_kayit(kimlik) or _lp.kayit(_lp.VARSAYILAN)

    def get_client(self) -> AsyncOpenAI:
        from app.services import llm as _llm
        if _llm.aktif_saglayici() == "chatgpt":
            # ChatGPT hesabı (resmî giriş): istemci anahtarsız, oturumdan beslenir.
            if self._damga != ("chatgpt",):
                from app.services.chatgpt_plan.istemci import ChatGPTAsyncClient
                self._client, self._damga = ChatGPTAsyncClient(), ("chatgpt",)
            return self._client
        sag = self._aktif()
        damga = (sag.kimlik, _lp.anahtar(sag.kimlik))
        if self._client is None or self._damga != damga:
            self._client = AsyncOpenAI(
                api_key=damga[1] or "anahtar-yok",
                base_url=sag.base_url,
                default_headers=dict(sag.basliklar) or None,
                timeout=30.0,
            )
            self._damga = damga
        return self._client

    def get_model(self) -> str:
        # Kullanıcının BYOK panelinde seçtiği model — config'deki ilk değer değil.
        from app.services import llm as _llm
        return _llm.get_runtime_config().get("model") or LLM_MODEL

    async def health_check(self) -> bool:
        try:
            resp = await self.get_client().models.list()
            return len(resp.data) > 0
        except Exception as exc:
            logger.debug("[bulut] health_check başarısız: %s", exc)
            return False


#: Geriye dönük ad — dışarıdan `OpenRouterProvider` diye çağıran kod kırılmasın.
OpenRouterProvider = BulutProvider


class OllamaProvider(LLMProvider):
    """Ollama — yerel sınır hesaplama (Llama 3.1)."""

    name = "ollama"

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key="ollama",
            base_url=OLLAMA_BASE_URL,
            timeout=60.0,  # lokal model daha yavaş
        )
        self._http = httpx.AsyncClient(timeout=5.0)

    def get_client(self) -> AsyncOpenAI:
        return self._client

    def get_model(self) -> str:
        return OLLAMA_MODEL  # llama3.1

    async def health_check(self) -> bool:
        try:
            r = await self._http.get(f"{_OLLAMA_HOST}/api/tags")
            return r.status_code == 200
        except Exception as exc:
            logger.debug("[ollama] health_check başarısız: %s", exc)
            return False


# ------------------------------------------------------------------ #
# ProviderStats — p95 latency takibi
# ------------------------------------------------------------------ #

@dataclass
class ProviderStats:
    """Son N çağrının latency istatistiklerini tutar (ring buffer)."""
    name: str
    window: int = 20

    _latencies: list[float] = field(default_factory=list, init=False)

    def record(self, latency_ms: float) -> None:
        self._latencies.append(latency_ms)
        if len(self._latencies) > self.window:
            self._latencies.pop(0)

    @property
    def p95(self) -> float:
        if not self._latencies:
            return 0.0
        s = sorted(self._latencies)
        idx = int(len(s) * 0.95)
        return s[min(idx, len(s) - 1)]

    @property
    def avg(self) -> float:
        return sum(self._latencies) / len(self._latencies) if self._latencies else 0.0


# ------------------------------------------------------------------ #
# LLMRouter — ana yönlendirici
# ------------------------------------------------------------------ #

class LLMRouter:
    """Fault-tolerant LLM yönlendirici.

    Öncelik sırası (prefer_local=False):  OpenRouter → Ollama
    Öncelik sırası (prefer_local=True):   Ollama     → OpenRouter

    Circuit breaker her provider için bağımsız çalışır.
    Tüm provider'lar OPEN durumundaysa son çalışan provider zorla kullanılır
    (graceful degradation — hata vermek yerine yavaş yanıt tercih edilir).
    """

    def __init__(self) -> None:
        self._bulut       = BulutProvider()
        self._ollama      = OllamaProvider()
        self._openrouter  = self._bulut     # geriye dönük ad
        self._cb: dict[str, CircuitBreaker] = {
            "bulut":  CircuitBreaker("bulut",  failure_threshold=3, cooldown_seconds=30),
            "ollama": CircuitBreaker("ollama", failure_threshold=2, cooldown_seconds=20),
        }
        self._stats: dict[str, ProviderStats] = {
            "bulut":  ProviderStats("bulut"),
            "ollama": ProviderStats("ollama"),
        }
        self._last_working: str = "bulut"

    @staticmethod
    def _ad(provider_name: str) -> str:
        """Eski çağrı yerleri 'openrouter' diyor — devre kesici anahtarı artık 'bulut'."""
        return "bulut" if provider_name == "openrouter" else provider_name

    def _ordered_providers(self, prefer_local: bool) -> list[LLMProvider]:
        """Tercih sırasına göre provider listesi döndür."""
        if prefer_local:
            return [self._ollama, self._bulut]
        return [self._bulut, self._ollama]

    async def get_client(
        self,
        prefer_local: bool | None = None,
    ) -> tuple[AsyncOpenAI, str]:
        """Kullanılabilir provider'ı seç; (client, model_name) döndür.

        prefer_local=None → config'den USE_LOCAL_LLM oku.
        Tüm provider'lar OPEN → last working provider'ı zorla kullan.
        """
        pref = USE_LOCAL_LLM if prefer_local is None else prefer_local
        providers = self._ordered_providers(pref)

        for provider in providers:
            cb = self._cb[provider.name]
            if not cb.allow_request():
                logger.debug("[router] %s OPEN — atlanıyor", provider.name)
                continue

            logger.debug("[router] → %s seçildi", provider.name)
            self._last_working = provider.name
            return provider.get_client(), provider.get_model()

        # Tüm provider OPEN — graceful degradation: son çalışan zorla
        logger.warning("[router] tüm provider'lar OPEN → %s zorla", self._last_working)
        fallback = self._ollama if self._last_working == "ollama" else self._bulut
        return fallback.get_client(), fallback.get_model()

    def record_success(self, provider_name: str, latency_ms: float) -> None:
        """Başarılı çağrı → CB success + latency kaydet."""
        ad = self._ad(provider_name)
        if ad in self._cb:
            self._cb[ad].record_success()
            self._stats[ad].record(latency_ms)

    def record_failure(self, provider_name: str) -> None:
        """Başarısız çağrı → CB failure."""
        ad = self._ad(provider_name)
        if ad in self._cb:
            self._cb[ad].record_failure()

    def status(self) -> dict:
        """Dashboard için provider durumu."""
        return {
            name: {
                "state":    self._cb[name].state.name,
                "p95_ms":   round(self._stats[name].p95, 1),
                "avg_ms":   round(self._stats[name].avg, 1),
            }
            for name in ("bulut", "ollama")
        }


# ------------------------------------------------------------------ #
# Singleton
# ------------------------------------------------------------------ #

_router: LLMRouter | None = None


def get_router() -> LLMRouter:
    """Uygulama genelinde tek LLMRouter örneği."""
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router

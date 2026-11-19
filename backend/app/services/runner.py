"""Agentic LLM Runner — tool-calling döngüsü, paralel çağrı, cancellation.

Faz B: chat_stream'deki while döngüsünü bu modüle taşıyoruz.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import os
from dataclasses import dataclass, field
from typing import AsyncGenerator

from openai import AsyncOpenAI

from app.services.tools import call_tool  # noqa: F401 (module-level for patch support)
from app.services.credential_scrubber import scrub as _scrub_credentials
from app.services.security import dis_icerik
from app.mesajlar import M


def _yerel_istemci(client) -> bool:
    """İstemci yerel Ollama'ya mı bakıyor?

    Sağlayıcı adına göre değil ADRESE göre karar verilir: bulut sağlayıcıların
    listesi değişkendir (kullanıcı OpenAI/Google/Groq… seçebilir), yerel uç ise
    tek ve bilinir. Devre kesici ve model seçimi bu ayrıma dayanıyor.
    """
    from app.config import OLLAMA_BASE_URL
    try:
        adres = str(client.base_url).rstrip("/")
    except Exception:
        return False
    return adres == OLLAMA_BASE_URL.rstrip("/") or ":11434" in adres

#: Bulut sağlayıcıda ilk token saniyeler içinde gelir; 30 sn cömert bir tavan.
LLM_TIMEOUT = 30.0
#: Yerel modelde aynı tavan ARIZA ÜRETİR — ölçüldü (2026-08-08, gerçek
#: `ollama serve` + llama3.1:latest, RTX 5060). Yuki'nin sistem promptu + 20 araç
#: tanımı ≈ 4.100 token ve prompt işleme tek başına **14–17 sn** sürüyor
#: (~60-70 tok/s); üretimle birlikte 30 sn'yi geçiyordu. Sonuç: **4 turun 4'ünde
#: de** ilk istek 30,03 sn'de düştü (Ollama log'unda `| 500 | 30.02s`), OpenAI
#: SDK'sı sessizce yeniden denedi ve kullanıcı her mesaj için ~30 sn fazladan
#: bekledi. Yavaşlık modelin doğasında; ona bulut tavanını dayatmak arıza üretir.
LLM_TIMEOUT_YEREL = 300.0


def _llm_zaman_asimi(client) -> float:
    """Bu istemci için istek zaman aşımı — yerel model bulut tavanına sığmaz."""
    return LLM_TIMEOUT_YEREL if _yerel_istemci(client) else LLM_TIMEOUT


logger = logging.getLogger(__name__)

TOOL_TIMEOUT = 10.0  # saniye (varsayılan araç)
LONG_TOOL_TIMEOUT = 180.0  # saniye — orkestrasyon/uzun araçlar (LLM alt-turları, dış kuyruk)
# Bu araçlar iç LLM alt-turları veya dış kuyruk kullanır → 10s cap'ten muaf.
_LONG_TOOLS = {"run_team", "delegate_to_companion"}


#: Kendi süre bütçesi olan araçlar (sn). check_updates'in alt süreç tavanı 60+30 sn;
#: genel 10 sn tavanında kesilip "yanıt vermedi" deniyordu (kişiselde 13,6 sn ölçüldü).
_ARAC_SURESI = {"check_updates": 60.0}


def arac_suresi(name: str, varsayilan: float = TOOL_TIMEOUT) -> float:
    """Araç zaman aşımı (sn). Runner ve Anthropic yolu aynı bütçeyi kullanır.

    Eskiden Anthropic yolu her araca sabit 10 sn veriyordu: `run_team`, `mcp__*`,
    `skill__*` gibi uzun araçlar o yolda yarıda kesiliyordu. Kendi bütçesi olan araç
    (`_ARAC_SURESI`) varsayılandan kısa süreye düşürülmez. Onaya tabi araçta onay
    penceresi ayrıca eklenir: onay beklemesi `call_tool` içinde, araç süresini yemez.
    """
    from app.services.tools.approval_gate import onay_payi
    if name in _LONG_TOOLS or name.startswith(("mcp__", "skill__")):
        return LONG_TOOL_TIMEOUT + onay_payi(name)
    return max(varsayilan, _ARAC_SURESI.get(name, 0.0)) + onay_payi(name)


MAX_STEPS_DEFAULT = int(os.getenv("MAX_STEPS", "5"))



def _inject_screen_context(messages: list[dict]) -> list[dict]:
    """Ekran bağlamı tazeyse system mesajına ekle (K-3b).

    Mesaj listesini kopyalar, orijinale dokunmaz.
    screen_context modülü yüklü değilse veya bağlam eskiyse dokunmaz.
    """
    try:
        from app.services.screen_context import get_screen_context
        ctx = get_screen_context()
        if not ctx.is_fresh():
            return messages
        block = ctx.to_prompt_block()
        if not block:
            return messages
        msgs = list(messages)
        if msgs and msgs[0].get("role") == "system":
            msgs[0] = {**msgs[0], "content": msgs[0]["content"] + f"\n\n{block}"}
        return msgs
    except ImportError:
        return messages

# E4: Runner düzeyinde token sayacı
_runner_tokens: dict[str, int] = {"prompt": 0, "completion": 0}


# Görev saati — testler sahte saatle değiştirir (süre tavanı gerçek bekleme istemez).
_saat = time.monotonic


@dataclass
class GorevTavanlari:
    """Atölye görevinin tavanları — tür tanımından gelir.

    Sohbet bunu VERMEZ (`gorev=None`): sohbet davranışı aynen kalır.
    Süre ve token tavanı ADIM BAŞINDA denetlenir: koşan bir LLM çağrısı ya da araç
    yarıda kesilmez. Aşım en çok bir adımdır (LLM zaman aşımı + `arac_zaman_asimi`).
    """
    adim: int = 60
    sure_sn: float = 30 * 60
    token: int = 1_500_000            # girdi + çıktı, görev boyunca toplam
    arac_zaman_asimi: float = 60.0


@dataclass
class GorevSonucu:
    """Görev modunda `LLMRunner.sonuc` — koşu bitince neden bittiği.

    durum: ``bitti`` · ``yarim`` (tavan; neden ``adim`` / ``sure`` / ``token``) ·
    ``iptal`` · ``hata``.
    """
    durum: str = "kosuyor"
    neden: str | None = None
    son_adim: int = 0
    token: int = 0
    token_tahmini: bool = False       # sağlayıcı usage vermedi → karakterden tahmin
    sure_sn: float = 0.0
    son_araclar: list[str] = field(default_factory=list)
    istisna: BaseException | None = field(default=None, repr=False)


def _tahmini_token(*parcalar: object) -> int:
    """Usage gelmezse kaba tahmin (~4 karakter/token). Tavan sessizce kör kalmasın."""
    try:
        return len(json.dumps(parcalar, ensure_ascii=False, default=str)) // 4
    except Exception:
        return 0



def get_runner_token_stats() -> dict[str, int]:
    return dict(_runner_tokens)


def _log_runner_tokens(prompt: int, completion: int) -> None:
    _runner_tokens["prompt"] += prompt
    _runner_tokens["completion"] += completion
    total = prompt + completion
    session_total = _runner_tokens["prompt"] + _runner_tokens["completion"]
    logger.info("token istek=%dp+%dc=%d | oturum=%d", prompt, completion, total, session_total)


class CancellationToken:
    """asyncio.Event tabanlı iptal mekanizması.

    Bool flag yerine Event kullanılır:
    - cancel() → tüm izlenen asyncio.Task'ları iptal eder (bellek sızıntısı yok)
    - track(task) → task tamamlanınca otomatik temizlenir
    """

    def __init__(self) -> None:
        self._event: asyncio.Event = asyncio.Event()
        self._tasks: set[asyncio.Task] = set()

    def cancel(self) -> None:
        self._event.set()
        for task in list(self._tasks):
            if not task.done():
                task.cancel()
        self._tasks.clear()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def track(self, task: asyncio.Task) -> asyncio.Task:
        """Task'ı izlemeye al; tamamlanınca otomatik temizle."""
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task


@dataclass
class RunnerResult:
    """Tek bir runner adımının sonucu."""
    content: str | None = None
    tool_calls_made: int = 0
    steps_used: int = 0
    cancelled: bool = False


class LLMRunner:
    """Agentic tool-calling döngüsü.

    Kullanım:
        runner = LLMRunner(client, model, tools)
        async for chunk in runner.run(messages):
            yield chunk
    """

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        tools: list[dict],
        max_steps: int = MAX_STEPS_DEFAULT,
        cancel_token: CancellationToken | None = None,
        gorev: GorevTavanlari | None = None,
        arac_cagir=None,
        adim_bildir=None,
    ):
        self.client = client
        self.model = model
        self.tools = tools
        # Görev modunda adım tavanı TÜRDEN gelir; `max_steps` yok sayılır.
        self.max_steps = gorev.adim if gorev is not None else max_steps
        self.cancel_token = cancel_token or CancellationToken()
        self.steps_used = 0
        self.total_tool_calls = 0
        self.arac_kayitlari: list[tuple[str, object, object]] = []   # (ad, argüman, sonuç) — arac_gecmisi okur
        self.gorev = gorev
        self.sonuc: GorevSonucu | None = GorevSonucu() if gorev is not None else None
        self._t0 = 0.0
        # Görev servisi kendi araç kapısını (tür izin listesi) ve adım kaydını bağlar.
        self.arac_cagir = arac_cagir      # None → modül düzeyi call_tool
        self.adim_bildir = adim_bildir    # async (adim, messages) — araç sonuçlarından sonra

    def _gorev_bitir(self, durum: str, neden: str | None) -> None:
        if self.sonuc is None or self.sonuc.durum != "kosuyor":
            return
        self.sonuc.durum = durum
        self.sonuc.neden = neden
        logger.info("Görev %s (%s) — adım %d/%d, %d token",
                    durum, neden, self.sonuc.son_adim, self.max_steps, self.sonuc.token)

    async def run(
        self,
        messages: list[dict],
    ) -> AsyncGenerator[str, None]:
        """Agentic döngü — `_dongu`yu sarar; görev modunda sonucu kapatır."""
        self._t0 = _saat()
        try:
            async for parca in self._dongu(messages):
                yield parca
        finally:
            if self.sonuc is not None:
                self.sonuc.sure_sn = round(_saat() - self._t0, 3)
                if self.cancel_token.is_cancelled:
                    self._gorev_bitir("iptal", "iptal")
                else:
                    self._gorev_bitir("hata", "beklenmedik_cikis")

    async def _dongu(
        self,
        messages: list[dict],
    ) -> AsyncGenerator[str, None]:
        """Agentic döngü. Tool call varsa çalıştır, content varsa yield et.

        Her adımda cancellation kontrol edilir.
        Tool call döngüsü non-streaming (tool_calls JSON parse gerekli).
        Final response streaming (token-by-token yield, TTFT minimizasyonu).
        """
        from app.services.event_bus import bus

        # K-3b: Ekran bağlamı enjeksiyonu
        # Görevde YOK: görev kişisel servislere (ekran) bağlanmaz.
        if self.gorev is None:
            messages = _inject_screen_context(messages)

        for step in range(1, self.max_steps + 1):
            if self.cancel_token.is_cancelled:
                return

            # Görev tavanları adım BAŞINDA. Bu iki kontrol sökülürse "hiç bitirmeyen"
            # model görevi adım tavanına kadar sürükler.
            if self.gorev is not None:
                if _saat() - self._t0 >= self.gorev.sure_sn:
                    self._gorev_bitir("yarim", "sure")
                    return
                if self.sonuc.token >= self.gorev.token:
                    self._gorev_bitir("yarim", "token")
                    return

            self.steps_used = step
            logger.info("Adım %d/%d (Model: %s)", step, self.max_steps, self.model)

            # Streaming çağrı — araç çağrısı yoksa token'lar anında akar (TTFT minimizasyonu)
            # Router üzerinden client al — circuit breaker devrede
            from app.services.llm_router import get_router as _get_router
            _router = _get_router()
            _client, _model = await _router.get_client()
            # 🔴 2026-08-01: burada router'ın modeli körlemesine kullanılıyordu.
            # Router `get_model()` → config'deki `LLM_MODEL` (varsayılan ÜCRETLİ
            # gpt-4.1-mini) döner; kullanıcının BYOK panelinde seçtiği modelden
            # habersizdir. Sonuç: aynı sohbet turunda araç adımları BİR modele,
            # final yanıt (satır 303) BAŞKA modele gidiyordu — ücretsiz anahtarlı
            # kullanıcıda araç adımları sessizce ölüyordu.
            # Kural: aynı sağlayıcıdaysak kullanıcının modeli geçerli; router yerel
            # sağlayıcıya düştüyse (ollama) onun kendi model adı kullanılmalı.
            # 🔴 2026-08-05: burada "openrouter" in base_url yazıyordu. Ürün artık
            # OpenAI/Google/Groq gibi sağlayıcıları da kabul ediyor; o kontrol
            # onların hepsini "yabancı sağlayıcı" sayıp kullanıcının SEÇTİĞİ modeli
            # sessizce ıskartaya çıkarır, router'ın varsayılan modeline düşerdi —
            # 08-01'de OpenRouter'da düzeltilen hatanın birebir aynısı.
            # Soru "OpenRouter mı?" değil, "yerel mi değil mi?".
            _same_provider = not _yerel_istemci(_client)
            _step_model = self.model if (_same_provider and self.model) else _model
            if _step_model != self.model:
                # Ayrışma artık sessiz değil — yukarıdaki log'un "Model: X" demesi
                # ama başka modele gidilmesi tam olarak bu hatayı gizliyordu.
                logger.warning(
                    "Adım modeli seçilenden farklı: %s ≠ %s (router sağlayıcı değiştirdi)",
                    _step_model, self.model,
                )
            _t0 = asyncio.get_event_loop().time()
            try:
                stream = await _client.chat.completions.create(
                    model=_step_model,
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto",
                    stream=True,
                    timeout=_llm_zaman_asimi(_client),
                    # Görevde token tavanı için sayaç gerekir; sohbet isteği değişmez.
                    **({"stream_options": {"include_usage": True}}
                       if self.gorev is not None else {}),
                )
            except Exception as _llm_exc:
                _router.record_failure('ollama' if _yerel_istemci(_client) else 'bulut')
                if self.gorev is not None:
                    self.sonuc.istisna = _llm_exc
                    self._gorev_bitir("hata", type(_llm_exc).__name__)
                    return
                raise _llm_exc

            # Araç çağrısı akümülatörleri
            tool_calls_raw: list[dict] = []
            has_tool_calls = False
            yayinlanan_karakter = 0  # bu adımda kullanıcıya GERÇEKTEN giden metin
            _usage_son = None

            try:
                async for chunk in stream:
                    if self.cancel_token.is_cancelled:
                        await stream.close()
                        return

                    # Sayaç parçası `choices=[]` ile gelir; continue'dan ÖNCE okunmalı.
                    _u = getattr(chunk, "usage", None)
                    if _u is not None:
                        _usage_son = _u

                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    delta = choice.delta

                    # Tool call delta'larını biriktir
                    if delta.tool_calls:
                        has_tool_calls = True
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            while len(tool_calls_raw) <= idx:
                                tool_calls_raw.append({
                                    "id": "", "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                })
                            if tc_delta.id:
                                tool_calls_raw[idx]["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    tool_calls_raw[idx]["function"]["name"] += tc_delta.function.name
                                if tc_delta.function.arguments:
                                    tool_calls_raw[idx]["function"]["arguments"] += tc_delta.function.arguments

                    # İçerik delta'larını direkt yayınla (araç çağrısı yoksa)
                    if delta.content:
                        if not has_tool_calls:
                            yayinlanan_karakter += len(delta.content)
                            yield delta.content
                        # Tool call varken gelen içerik (premature) sessizce atılır
            except asyncio.CancelledError:
                await stream.close()
                raise

            _router.record_success(
                'ollama' if _yerel_istemci(_client) else 'bulut',
                (asyncio.get_event_loop().time() - _t0) * 1000,
            )

            if self.sonuc is not None:
                if _usage_son is not None:
                    self.sonuc.token += (getattr(_usage_son, "prompt_tokens", 0) or 0) + (
                        getattr(_usage_son, "completion_tokens", 0) or 0)
                else:
                    self.sonuc.token += _tahmini_token(messages, self.tools, tool_calls_raw)
                    self.sonuc.token_tahmini = True
                self.sonuc.son_adim = step

            # ── Araç çağrısı yoktu → içerik doğrudan yield edildi, tamamlandı ──
            if not has_tool_calls:
                self._gorev_bitir("bitti", None)
                # 🔴 2026-08-03 — SAHA RAPORU: *"bazı ücretsiz modeller çalışmıyor."*
                # Ölçüldü (gerçek anahtar, 13 canlı `:free`+tools modeli): bir model
                # (`nvidia/nemotron-nano-9b-v2:free`) 200 OK döndürüyor ama İÇERİK BOŞ
                # ve araç çağrısı da yok. Eski kod burada sessizce `return` ediyordu →
                # Yuki hiçbir şey yazmıyor, hata da yok. Kullanıcı "ürün bozuk" diyor,
                # log'da hiçbir iz yok. Sağlayıcı 429/504 verse mesajlanıyordu; bu
                # sınıf (başarılı ama boş yanıt) tamamen sessizdi.
                # Kural: sessiz başarısızlık, gürültülü başarısızlıktan kötüdür.
                if yayinlanan_karakter == 0 and self.gorev is None:
                    logger.warning(
                        "Boş yanıt: model=%s adım=%d — içerik yok, araç çağrısı yok",
                        _step_model, step,
                    )
                    yield M("llm.model-bos-yanit", grup=M("llm.grup-ucretsiz-dogrulandi"))
                return

            # ── Araç çağrısı var → akümüle edilen çağrıları çalıştır ──
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": tool_calls_raw,
            })
            if self.cancel_token.is_cancelled:
                return

            # tool_calls_raw'ı _execute_tools'un beklediği formata sarmala
            class _FakeFn:
                def __init__(self, d):
                    self.name = d["function"]["name"]
                    self.arguments = d["function"]["arguments"]

            class _FakeTC:
                def __init__(self, d):
                    self.id = d["id"]
                    self.function = _FakeFn(d)

            fake_tool_calls = [_FakeTC(d) for d in tool_calls_raw]
            results = await self._execute_tools(
                fake_tool_calls, self.arac_cagir or call_tool, bus)
            if self.sonuc is not None:
                self.sonuc.son_araclar = [nm for (_id, nm, _r) in results]

            # Sonuçları mesaj geçmişine ekle
            for tc_id, tc_name, tc_res in results:
                if isinstance(tc_res, str) and tc_res.startswith("SCREENSHOT_DATA:"):
                    base64_data = tc_res.split(":", 1)[1]
                    messages.append({
                        "tool_call_id": tc_id,
                        "role": "tool",
                        "name": tc_name,
                        "content": "Ekran görüntüsü alındı.",  # i18n-istisna: LLM'e giden araç sonucu/mesajı — kullanıcı ekranında çizilmez
                    })
                    messages.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "İşte ekranım:"},  # i18n-istisna: LLM'e giden araç sonucu/mesajı — kullanıcı ekranında çizilmez
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_data}"
                                },
                            },
                        ],
                    })
                else:
                    messages.append({
                        "tool_call_id": tc_id,
                        "role": "tool",
                        "name": tc_name,
                        "content": dis_icerik.zarfla(tc_name, _scrub_credentials(str(tc_res))),
                    })

            # İptal edilen adım KAYDEDİLMEZ: DEVAM son tutarlı noktadan sürer.
            if self.adim_bildir is not None and not self.cancel_token.is_cancelled:
                await self.adim_bildir(step, messages)

            # C — çok-araçlı görev başarısı → 'görev tamam' kartı (eşik ≥3, cooldown'lı)
            # Atölye görevinde kart yok (sohbet arayüzünü doldururdu).
            if self.gorev is None:
                try:
                    n_ok = sum(
                        1 for (_id, _nm, r) in results
                        if not (isinstance(r, str) and r.lstrip()[:6].lower().startswith(("hata", "error", "❌")))
                    )
                    if n_ok >= 3:
                        from app.services.skill_events import note_task
                        await note_task(n_ok)
                except Exception:
                    pass

            # Tool sonrası final response'u streaming al
            if self.cancel_token.is_cancelled:
                return
            # `arac_alani_ac` iş yapmaz, yalnız şemayı genişletir. Buradan
            # `_stream_final`e geçilirse model genişlemiş listeyi hiç görmez ve
            # işi yapmadan "yaptım" der — döngü bir adım daha sürer.
            if self.gorev is not None:
                # Görevde araç adımından sonra döngü şemayla sürer; tavan = "yarım".
                if step < self.max_steps:
                    continue
                self._gorev_bitir("yarim", "adim")
                return
            if step < self.max_steps and any(
                nm == "arac_alani_ac" for (_id, nm, _r) in results
            ):
                logger.info("Alan açıldı — döngü sürüyor (adım %d/%d, %d araç)",
                            step, self.max_steps, len(self.tools or []))
                continue
            async for chunk in self._stream_final(messages):
                yield chunk
            return

        # max_steps <= 0: döngü hiç koşmadı.
        self._gorev_bitir("yarim", "adim")

    async def _stream_final(
        self,
        messages: list[dict],
    ) -> AsyncGenerator[str, None]:
        """Tool call'lar bittikten sonra final yanıtı streaming olarak al."""
        logger.info("Final streaming response başlatılıyor...")

        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                timeout=_llm_zaman_asimi(self.client),
            )
            try:
                async for chunk in stream:
                    if self.cancel_token.is_cancelled:
                        await stream.close()
                        return
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
            except asyncio.CancelledError:
                await stream.close()
                raise
        except Exception as e:
            logger.warning("Streaming hatası (%s), fallback non-streaming...", e)
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                timeout=_llm_zaman_asimi(self.client),
            )
            if response.usage:
                _log_runner_tokens(response.usage.prompt_tokens, response.usage.completion_tokens)
            content = response.choices[0].message.content or ""
            if content:
                yield content

    async def _execute_tools(
        self,
        tool_calls: list,
        call_tool_fn,
        bus,
    ) -> list[tuple[str, str, str]]:
        """Tool çağrılarını paralel çalıştır. Timeout + hata izolasyonu."""

        async def _run_one(tc) -> tuple[str, str, str]:
            name = tc.function.name
            args = json.loads(tc.function.arguments)
            logger.info("Araç: %s", name)
            await bus.publish("state_info", {"text": M("llm.arac-kullaniyor", arac=name)})
            # görevde varsayılan süre türden gelir
            _to = arac_suresi(name, self.gorev.arac_zaman_asimi if self.gorev is not None else TOOL_TIMEOUT)
            try:
                result = await asyncio.wait_for(
                    call_tool_fn(name, args),
                    timeout=_to,
                )
            except asyncio.TimeoutError:
                result = f"Hata: '{name}' aracı {_to}s içinde yanıt vermedi."  # i18n-istisna: LLM'e giden araç sonucu/mesajı — kullanıcı ekranında çizilmez
                logger.warning("TIMEOUT: %s", name)
            except Exception as e:
                result = f"Hata: '{name}' aracında sorun oluştu — {e}"  # i18n-istisna: LLM'e giden araç sonucu/mesajı — kullanıcı ekranında çizilmez
                logger.error("HATA: %s → %s", name, e)
            self.total_tool_calls += 1
            self.arac_kayitlari.append((name, args, result))
            return tc.id, name, result

        if self.cancel_token.is_cancelled:
            return []
        tasks = [
            self.cancel_token.track(asyncio.create_task(_run_one(tc)))
            for tc in tool_calls
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        output = []
        for tc, res in zip(tool_calls, results):
            if isinstance(res, BaseException):
                output.append((tc.id, tc.function.name,
                                f"[İPTAL/HATA] {type(res).__name__}: {res}"))  # i18n-istisna: LLM'e giden araç sonucu/mesajı — kullanıcı ekranında çizilmez
            else:
                output.append(res)
        return output

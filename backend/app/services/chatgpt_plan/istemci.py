"""ChatGPT oturumuyla sohbet istemcisi — Chat Completions çağrısını Responses'a çevirir.

Yuki'nin akış katmanı (`runner.py`, `llm.py`) OpenAI Chat Completions biçiminde konuşur
(`client.chat.completions.create(...)`, `chunk.choices[0].delta`). Bu istemci aynı yüzü
sunar; içeride resmî OpenAI SDK'sının `responses` ucunu kullanır:

  messages            → instructions (system) + input öğeleri
  tools (function)    → düz function araçları
  Responses olayları  → Chat Completions "chunk" nesneleri (metin deltası, araç çağrısı deltası)

Uç `api.openai.com/v1` (Bearer = kullanıcının ChatGPT oturumundan gelen erişim anahtarı).
Üçüncü taraf istemci başlığı yok. Anahtar log'a ve istisna metnine girmez.
"""

from __future__ import annotations

import asyncio
import logging
import time
from types import SimpleNamespace
from typing import Any, AsyncIterator

import httpx
from openai import AsyncOpenAI, AuthenticationError

from app.services.chatgpt_plan import kimlik

logger = logging.getLogger(__name__)

USER_AGENT = "Yuki"
VARSAYILAN_MODEL = "gpt-5"
KATALOG_OMRU_SN = 600.0


# ------------------------------------------------------------------ #
# Biçim çevirme (saf fonksiyonlar — ağsız test edilir)
# ------------------------------------------------------------------ #


def _metin(icerik: Any) -> str:
    if isinstance(icerik, str):
        return icerik
    if isinstance(icerik, list):
        return "\n".join(str(p.get("text") or "") for p in icerik
                         if isinstance(p, dict) and p.get("type") in ("text", "input_text"))
    return "" if icerik is None else str(icerik)


def _kullanici_icerigi(icerik: Any) -> Any:
    """Düz metin ya da çok parçalı (metin + görsel) kullanıcı içeriği."""
    if not isinstance(icerik, list):
        return _metin(icerik)
    parcalar: list[dict[str, Any]] = []
    for p in icerik:
        if not isinstance(p, dict):
            continue
        if p.get("type") in ("text", "input_text"):
            parcalar.append({"type": "input_text", "text": str(p.get("text") or "")})
        elif p.get("type") == "image_url":
            url = p.get("image_url")
            url = url.get("url") if isinstance(url, dict) else url
            if url:
                parcalar.append({"type": "input_image", "image_url": str(url)})
    return parcalar or ""


def mesajlari_cevir(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Chat Completions mesajları → (instructions, Responses input öğeleri)."""
    talimat: list[str] = []
    girdi: list[dict[str, Any]] = []
    for m in messages:
        rol = m.get("role")
        if rol in ("system", "developer"):
            t = _metin(m.get("content"))
            if t:
                talimat.append(t)
        elif rol == "user":
            girdi.append({"role": "user", "content": _kullanici_icerigi(m.get("content"))})
        elif rol == "assistant":
            t = _metin(m.get("content"))
            if t:
                girdi.append({"role": "assistant", "content": t})
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                girdi.append({
                    "type": "function_call",
                    "call_id": str(tc.get("id") or ""),
                    "name": str(fn.get("name") or ""),
                    "arguments": str(fn.get("arguments") or "{}"),
                })
        elif rol == "tool":
            girdi.append({
                "type": "function_call_output",
                "call_id": str(m.get("tool_call_id") or ""),
                "output": _metin(m.get("content")),
            })
    return "\n\n".join(talimat), girdi


def araclari_cevir(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """`{"type":"function","function":{...}}` → Responses'un düz function aracı."""
    cikti = []
    for t in tools or []:
        fn = t.get("function") if isinstance(t, dict) else None
        if not fn or not fn.get("name"):
            continue
        cikti.append({
            "type": "function",
            "name": fn["name"],
            "description": fn.get("description") or "",
            "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return cikti


def _chunk(icerik: str | None = None, arac: list[Any] | None = None,
           bitis: str | None = None, usage: Any = None) -> Any:
    delta = SimpleNamespace(content=icerik, tool_calls=arac, role="assistant")
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=bitis, index=0)],
                           usage=usage)


def _arac_deltasi(index: int, id_: str = "", ad: str = "", arguman: str = "") -> Any:
    return SimpleNamespace(index=index, id=id_ or None, type="function",
                           function=SimpleNamespace(name=ad or None, arguments=arguman or None))


async def olaylari_chunka(olaylar: AsyncIterator[Any]) -> AsyncIterator[Any]:
    """Responses akış olayları → Chat Completions chunk'ları."""
    indeks: dict[str, int] = {}
    arac_var = False
    async for o in olaylar:
        tur = getattr(o, "type", "")
        if tur == "response.output_text.delta":
            if o.delta:
                yield _chunk(icerik=o.delta)
        elif tur == "response.output_item.added":
            oge = o.item
            if getattr(oge, "type", "") == "function_call":
                arac_var = True
                i = len(indeks)
                indeks[oge.id] = i
                yield _chunk(arac=[_arac_deltasi(i, getattr(oge, "call_id", "") or oge.id,
                                                 getattr(oge, "name", "") or "")])
        elif tur == "response.function_call_arguments.delta":
            i = indeks.get(o.item_id)
            if i is not None and o.delta:
                yield _chunk(arac=[_arac_deltasi(i, arguman=o.delta)])
        elif tur == "response.completed":
            u = getattr(o.response, "usage", None)
            usage = SimpleNamespace(prompt_tokens=getattr(u, "input_tokens", 0) or 0,
                                    completion_tokens=getattr(u, "output_tokens", 0) or 0,
                                    total_tokens=getattr(u, "total_tokens", 0) or 0) if u else None
            yield _chunk(bitis="tool_calls" if arac_var else "stop", usage=usage)
        elif tur in ("response.failed", "response.incomplete", "error"):
            ayrinti = getattr(getattr(o, "response", None), "error", None) or getattr(o, "message", "")
            raise RuntimeError(f"ChatGPT yanıtı tamamlanamadı ({tur}: {str(ayrinti)[:160]})")


class _Akis:
    """`async for` + `close()` — runner'ın beklediği akış yüzü."""

    def __init__(self, ham: Any, chunklar: AsyncIterator[Any]) -> None:
        self._ham, self._chunklar = ham, chunklar

    def __aiter__(self) -> "_Akis":
        return self

    async def __anext__(self) -> Any:
        return await self._chunklar.__anext__()

    async def close(self) -> None:
        kapat = getattr(self._ham, "close", None)
        if kapat:
            await kapat()


async def _topla(akis: AsyncIterator[Any]) -> Any:
    """Akışı tek bir Chat Completions cevabına topla (stream=False çağrıları)."""
    metin: list[str] = []
    araclar: dict[int, dict[str, str]] = {}
    usage = None
    async for c in akis:
        d = c.choices[0].delta
        if d.content:
            metin.append(d.content)
        for tc in d.tool_calls or []:
            a = araclar.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
            a["id"] = tc.id or a["id"]
            a["name"] += tc.function.name or ""
            a["arguments"] += tc.function.arguments or ""
        if c.usage:
            usage = c.usage
    arac_listesi = [SimpleNamespace(id=a["id"], type="function",
                                    function=SimpleNamespace(name=a["name"], arguments=a["arguments"]))
                    for _, a in sorted(araclar.items())] or None
    mesaj = SimpleNamespace(role="assistant", content="".join(metin) or None, tool_calls=arac_listesi)
    return SimpleNamespace(choices=[SimpleNamespace(message=mesaj, index=0,
                                                    finish_reason="tool_calls" if arac_listesi else "stop")],
                           usage=usage)


# ------------------------------------------------------------------ #
# İstemci
# ------------------------------------------------------------------ #


class _Completions:
    def __init__(self, ust: "ChatGPTAsyncClient") -> None:
        self._ust = ust

    async def create(self, *, model: str, messages: list[dict[str, Any]],
                     tools: list[dict[str, Any]] | None = None, stream: bool = False,
                     timeout: float | None = None, **_yoksay: Any) -> Any:
        # tool_choice / temperature / max_tokens bilerek iletilmez: akıl yürüten modeller
        # bunları reddedebilir; araç seçimi "auto" varsayılanıdır.
        talimat, girdi = mesajlari_cevir(messages)
        govde: dict[str, Any] = {"model": model, "input": girdi, "store": False, "stream": True}
        if talimat:
            govde["instructions"] = talimat
        arac = araclari_cevir(tools)
        if arac:
            govde["tools"] = arac
        ham = await self._ust._ac(govde, timeout)
        chunklar = olaylari_chunka(ham)
        if stream:
            return _Akis(ham, chunklar)
        try:
            return await _topla(chunklar)
        finally:
            kapat = getattr(ham, "close", None)
            if kapat:
                await kapat()


class ChatGPTAsyncClient:
    """`AsyncOpenAI` yüzünün dar bir alt kümesi: `chat.completions.create` + `modeller`."""

    def __init__(self, zaman_asimi: float = 60.0) -> None:
        self.base_url = kimlik.api_taban()
        self._zaman_asimi = zaman_asimi
        self._katalog: list[str] | None = None
        self._katalog_zamani = 0.0
        self.chat = SimpleNamespace(completions=_Completions(self))

    async def _token(self, zorla_tazele: bool = False) -> str:
        kayit = await asyncio.to_thread(kimlik.gecerli_kimlik, zorla_tazele)
        return kayit.access_token

    def _sdk(self, token: str, timeout: float | None) -> AsyncOpenAI:
        return AsyncOpenAI(api_key=token, base_url=kimlik.api_taban(),
                           default_headers={"User-Agent": USER_AGENT},
                           timeout=timeout or self._zaman_asimi, max_retries=0)

    async def _ac(self, govde: dict[str, Any], timeout: float | None) -> Any:
        """Responses akışını aç; 401 gelirse bir kez yenileyip tekrar dene."""
        for deneme in (0, 1):
            token = await self._token(zorla_tazele=bool(deneme))
            try:
                return await self._sdk(token, timeout).responses.create(**govde)
            except AuthenticationError:
                if deneme:
                    raise kimlik.PlanGirisGerekli("ChatGPT oturumu reddedildi — yeniden giriş") from None
                logger.info("chatgpt: erişim anahtarı reddedildi, yenileniyor")
        raise AssertionError("ulaşılmaz")  # pragma: no cover

    async def modeller(self, zorla: bool = False) -> list[str]:
        """Hesaba açık model listesi. Hata → [] (sır içermeyen tek satır log)."""
        if not zorla and self._katalog is not None and time.time() - self._katalog_zamani < KATALOG_OMRU_SN:
            return list(self._katalog)
        try:
            token = await self._token()
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.get(f"{kimlik.api_taban()}/models", headers={
                    "Authorization": f"Bearer {token}", "Accept": "application/json",
                    "User-Agent": USER_AGENT})
            if r.status_code != 200:
                logger.warning("chatgpt: model listesi HTTP %s", r.status_code)
                return []
            veri = r.json()
            liste = (veri.get("data") or veri.get("models")) if isinstance(veri, dict) else None
            self._katalog = sorted(str(m.get("id") or m.get("slug") or "") for m in (liste or [])
                                   if isinstance(m, dict) and (m.get("id") or m.get("slug")))
            self._katalog_zamani = time.time()
            return list(self._katalog)
        except (kimlik.PlanKimlikHatasi, httpx.HTTPError, ValueError) as e:
            logger.warning("chatgpt: model listesi alınamadı (%s)", type(e).__name__)
            return []

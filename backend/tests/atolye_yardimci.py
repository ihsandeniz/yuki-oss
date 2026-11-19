"""Atölye testleri için sahte akış/istemci kurucuları.

⚠️ MagicMock DEĞİL, SimpleNamespace: `mock.function.name` MagicMock'ta ayrılmış bir alandır
(mock'un kendi adı) ve sessizce yanlış değer verir.
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


def _icerik_akisi(text: str):
    """Araç çağrısı içermeyen, kelime kelime akan content stream'i."""
    async def _aiter():
        for word in text.split():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=word + " ", tool_calls=None))]
            )
    mock = MagicMock()
    mock.__aiter__ = lambda self: _aiter()
    mock.close = AsyncMock()          # gerçek AsyncStream.close() bir coroutine'dir
    return mock


def _arac_akisi(cagrilar: list[tuple[str, str, dict]]):
    """Araç çağrılarını `delta.tool_calls` parçaları hâlinde yayan stream.

    `cagrilar`: [(call_id, tool_name, arguments_dict), ...]
    Gerçek sağlayıcı gibi PARÇALI yayar — ad bir chunk'ta, argümanlar sonraki chunk'larda.
    """
    async def _aiter():
        for idx, (cid, ad, args) in enumerate(cagrilar):
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
                content=None,
                tool_calls=[SimpleNamespace(
                    index=idx, id=cid,
                    function=SimpleNamespace(name=ad, arguments=""),
                )],
            ))])
            arg_json = json.dumps(args)
            orta = len(arg_json) // 2 or len(arg_json)
            for parca in (arg_json[:orta], arg_json[orta:]):
                if not parca:
                    continue
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
                    content=None,
                    tool_calls=[SimpleNamespace(
                        index=idx, id="",
                        function=SimpleNamespace(name="", arguments=parca),
                    )],
                ))])
    mock = MagicMock()
    mock.__aiter__ = lambda self: _aiter()
    mock.close = AsyncMock()          # gerçek AsyncStream.close() bir coroutine'dir
    return mock


def _sahte_client(yanitlar: list):
    """`chat.completions.create` çağrılarına sırayla `yanitlar`ı döndüren client."""
    client = AsyncMock()
    client.base_url = "https://api.openai.com/v1"
    client.chat.completions.create = AsyncMock(side_effect=yanitlar)
    return client


def _sahte_router(client):
    router = MagicMock()
    router.get_client = AsyncMock(return_value=(client, "test/model"))
    router.record_success = MagicMock()
    router.record_failure = MagicMock()
    return router


def kota_hatasi():
    """Sağlayıcı kotası/oran sınırı (HTTP 429) — görev `durdu/kota` olur."""
    import httpx
    import openai
    return openai.RateLimitError(
        "429", response=httpx.Response(429, request=httpx.Request("POST", "https://sahte.invalid/v1")),
        body=None)


def dis_origin_izni(monkeypatch, origin: str) -> None:
    """Testte güvenilir dış https adresini hem yerel kapıya hem Atölye uçlarına tanıtır
    (gerçek kurulumda `ALLOWED_ORIGINS_EXTRA` ile gelir)."""
    from app import yerel_kapi
    from app.api import gorev as gorev_api
    asil = yerel_kapi.koken_izinli
    monkeypatch.setattr(yerel_kapi, "koken_izinli",
                        lambda k, h, s, izinli: asil(k, h, s, list(izinli) + [origin]))
    monkeypatch.setattr(gorev_api, "dis_originler", lambda: [origin])

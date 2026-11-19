"""Ekip işçisi (run_team / delegate_to_companion) kullanıcının seçtiği sağlayıcıyı izler.

2026-11-12 ölçümü: Anthropic seçili ve anahtarı girilmişken uzman ajanın
istemcisi `https://openrouter.ai/api/v1/`'e, model `google/gemma-…:free`'ye
gidiyordu — anahtarı Anthropic'te olan kullanıcıda ekip sessizce düşüyordu.
İki ayrı yol vardı: `llm._get_client(force_cloud=True)` (planlama/sentez) ve
işçinin `LLMRunner`'ının içindeki router (`BulutProvider._aktif`).

Karar: işçi seçili sağlayıcıyı izler. Anthropic'te Anthropic'in
resmî OpenAI-uyumlu ucu kullanılır, yan model ucuz Haiku. Anthropic anahtarı
yoksa eski yedek davranış (varsayılan sağlayıcıya düşme) korunur.
"""
import asyncio

import pytest

from app.services import llm, llm_router, llm_providers as lp


@pytest.fixture
def anthropic_secili(monkeypatch):
    monkeypatch.setattr(llm, "USE_LOCAL_LLM", False)
    monkeypatch.setattr(llm, "_runtime_provider", "anthropic")
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm, "_last_damga", None)
    monkeypatch.setattr(lp, "_anahtarlar", {"anthropic": "sk-ant-test"})
    monkeypatch.setattr(llm, "_yan_client", None)
    monkeypatch.setattr(llm_router, "_router", None, raising=False)
    yield


def _host(client) -> str:
    return str(client.base_url)


def test_planlama_istemcisi_anthropic(anthropic_secili, monkeypatch):
    monkeypatch.setattr(llm, "_yan_client", None)
    c = llm._yan_istemci()
    assert "api.anthropic.com" in _host(c), _host(c)
    assert c.api_key == "sk-ant-test"


def test_gorus_yolu_get_client_degismedi(anthropic_secili, monkeypatch):
    # VISION_MODEL OpenRouter kimliği; _get_client eski yedekte kalmalı
    monkeypatch.setattr(lp, "_anahtarlar", {"anthropic": "sk-ant-test", "openrouter": "sk-or-v1-x"})
    assert "openrouter.ai" in _host(llm._get_client())


def test_isci_runner_router_anthropic(anthropic_secili):
    c, _m = asyncio.run(llm_router.LLMRouter().get_client())
    assert "api.anthropic.com" in _host(c), _host(c)


def test_yan_model_ucuz_haiku(anthropic_secili):
    from app.config import LLM_MODEL_FAST, LLM_MODEL_STRONG
    assert llm._background_model(LLM_MODEL_FAST) == "claude-haiku-5-5"
    assert llm._background_model(LLM_MODEL_STRONG) == "claude-haiku-5-5"


def test_delegate_to_persona_anthropic_ve_haiku(anthropic_secili, monkeypatch, test_ekibi):
    from app.services import orchestrator, runner as runner_mod
    gorulen = {}

    class _Sahte:
        def __init__(self, client, model, tools, **kw):
            gorulen["host"], gorulen["model"] = _host(client), model

        async def run(self, messages):
            yield "tamam"

    monkeypatch.setattr(runner_mod, "LLMRunner", _Sahte)
    sonuc = asyncio.run(orchestrator.delegate_to_persona("uzman_a", "x"))
    assert sonuc == "tamam"
    assert "api.anthropic.com" in gorulen["host"]
    assert gorulen["model"] == "claude-haiku-5-5"


def test_anthropic_anahtari_yoksa_eski_yedek(anthropic_secili, monkeypatch):
    monkeypatch.setattr(lp, "_anahtarlar", {"openrouter": "sk-or-v1-x"})
    monkeypatch.setattr(llm, "_yan_client", None)
    c = llm._yan_istemci()
    assert "openrouter.ai" in _host(c)
    c2, _ = asyncio.run(llm_router.LLMRouter().get_client())
    assert "openrouter.ai" in _host(c2)
    from app.config import LLM_MODEL_FAST
    assert llm._background_model(LLM_MODEL_FAST) != "claude-haiku-5-5"


def test_openrouter_secili_degismedi(monkeypatch):
    monkeypatch.setattr(llm, "USE_LOCAL_LLM", False)
    monkeypatch.setattr(llm, "_runtime_provider", "openrouter")
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm, "_last_damga", None)
    monkeypatch.setattr(lp, "_anahtarlar", {"openrouter": "sk-or-v1-x"})
    monkeypatch.setattr(llm, "_yan_client", None)
    assert "openrouter.ai" in _host(llm._yan_istemci())
    c, _ = asyncio.run(llm_router.LLMRouter().get_client())
    assert "openrouter.ai" in _host(c)

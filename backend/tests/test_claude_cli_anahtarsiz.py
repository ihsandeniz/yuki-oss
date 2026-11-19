"""B4 (11-14, temiz kurulum denetimi): bilgisayardaki `claude` programıyla (claude_code) sohbet
anahtarsız çalışırken her yer "anahtar yok / kurulum gerekli" diyordu.

Kapılar: `/api/llm/key/status` claude_code'u yerel sayar (rozetler `set || yerel` okur) ve Sağlık
paneli KRİTİK "Anahtar girilmemiş" yerine "anahtar gerekmiyor" der. OpenRouter'da anahtarsız hâl
yine KRİTİK kalır (karşı örnek — kapı her şeyi yeşile boyamasın).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import self_check


@pytest.fixture
def anahtarsiz(monkeypatch):
    from app.services import llm, llm_providers as lp
    monkeypatch.setattr(llm, "USE_LOCAL_LLM", False, raising=False)
    monkeypatch.setattr(llm, "has_openrouter_key", lambda: False)
    monkeypatch.setattr(lp, "anahtar", lambda kimlik: "")
    monkeypatch.setattr("app.api.llm_config_api._persist_env", lambda k, v: None)
    return llm


def test_claude_cli_durum_yerel(anahtarsiz, monkeypatch):
    monkeypatch.setattr(anahtarsiz, "_runtime_provider", "claude_code")
    st = TestClient(app).get("/api/llm/key/status").json()
    assert st["provider"] == "claude_code"
    assert st["yerel"] is True and st["anahtar_gerekir"] is False


def test_openrouter_anahtarsiz_yerel_degil(anahtarsiz, monkeypatch):
    monkeypatch.setattr(anahtarsiz, "_runtime_provider", "openrouter")
    st = TestClient(app).get("/api/llm/key/status").json()
    assert st["yerel"] is False and st["anahtar_gerekir"] is True and st["set"] is False


def test_saglik_claude_cli_anahtar_gerekmiyor(anahtarsiz, monkeypatch):
    monkeypatch.setattr(anahtarsiz, "_runtime_provider", "claude_code")
    d = self_check._denetle_llm_anahtar()
    assert d["ok"] is True, d
    assert "Claude Code" in str(d)


def test_saglik_openrouter_anahtarsiz_kritik(anahtarsiz, monkeypatch):
    monkeypatch.setattr(anahtarsiz, "_runtime_provider", "openrouter")
    d = self_check._denetle_llm_anahtar()
    assert d["ok"] is False and d["seviye"] == self_check.KRITIK, d

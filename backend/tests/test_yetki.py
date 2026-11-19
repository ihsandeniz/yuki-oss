"""Yetki modülü — açık kaynakta kademe ve geliştirici araçları yok.

`services/yetki.py`: her araç, özellik ve karakter açık. Geliştirici araçları kümesi
(kabuk, paket kurma, süreç öldürme, fare/klavye) açık kaynak sürüme GİRMEZ
(karar: 2026-10-17 yuki-urun-acik-kaynak § Ek karar) — kayıtta da yoklar.
`GET /api/yetki` sözleşmesi: {tools[], features{...}, characters[], all_characters[]}.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.services import yetki
from app.services.tools import dispatcher

# Açık kaynağa girmeyen araçlar — kayıtta, LLM listesinde ve dispatcher'da YOK.
GIRMEYENLER = frozenset({
    "run_" + "shell", "execute_" + "command", "install_" + "package", "kill_" + "process",
    "type_" + "text", "mouse_" + "click", "mouse_" + "move", "mouse_" + "drag",
    "mouse_" + "scroll", "press_" + "keys", "control_" + "window", "list_" + "monitors",
    "get_active_" + "window", "screen_" + "target",
})


def _kayitli() -> set[str]:
    return {t["function"]["name"] for t in dispatcher.TOOLS}


def test_girmeyen_araclar_kayitta_YOK():
    sizan = GIRMEYENLER & _kayitli()
    assert not sizan, f"açık kaynağa girmeyen araç kayıtlı: {sorted(sizan)}"


def _bayrakli_araclar() -> set[str]:
    return set().union(*yetki.ARACLAR.values())


def test_tum_kayitli_araclar_LLM_listesinde():
    """Bayraklı özelliklerin (varsayılan kapalı) araçları ve — uzman persona yokken —
    ekip araçları dışında her kayıtlı araç LLM listesinde (ekip: test_tek_karakter.py)."""
    from app.services import orchestrator
    aktif = {t["function"]["name"] for t in dispatcher.get_active_tools()}
    ekipsiz = set() if orchestrator.ekip_var() else set(orchestrator.EKIP_ARACLARI)
    assert _kayitli() - _bayrakli_araclar() - ekipsiz == aktif


@pytest.mark.parametrize("ad", sorted(GIRMEYENLER))
def test_uydurma_cagri_gecersiz_arac_doner(ad):
    """Model aracı uydurup çağırırsa dispatcher hiçbir şey çalıştırmaz."""
    cevap = asyncio.run(dispatcher.call_tool(ad, {}))
    assert cevap == "Hata: Geçersiz araç.", cevap


def test_eski_ayar_api_si_yok():
    assert not hasattr(yetki, "dev_tools_enabled")
    assert not hasattr(yetki, "DEV_" + "TOOLS")


def test_api_yetki_sozlesmesi():
    r = TestClient(app_()).get("/api/yetki")
    assert r.status_code == 200
    d = r.json()
    assert set(d) == {"tools", "features", "characters", "all_characters"}
    assert "agent_command" not in d["features"]
    assert d["tools"] and not (set(d["tools"]) & GIRMEYENLER)
    assert set(d["tools"]) == _kayitli()


def test_api_yetki_ozellik_ve_karakterler_hep_acik():
    """Bayraklı özellikler dışında hepsi açık; bayraklılar: test_ozellik_bayrak.py."""
    d = TestClient(app_()).get("/api/yetki").json()
    bayrakli = set(yetki.BAYRAKLI)
    assert d["features"] and all(v is True for k, v in d["features"].items() if k not in bayrakli)
    assert set(d["characters"]) == set(d["all_characters"]) == set(yetki.CHARACTERS_ALL)


@pytest.mark.parametrize("ozellik", list(yetki.FEATURES) + ["uydurma_ozellik"])
def test_feature_hep_acik(ozellik):
    assert yetki.feature_allowed(ozellik) is True


@pytest.mark.parametrize("karakter", list(yetki.CHARACTERS_ALL))
def test_character_hep_acik(karakter):
    assert yetki.character_allowed(karakter) is True


def app_():
    from app.main import app
    return app

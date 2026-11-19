"""API şeması üretilebilir mi — `app.openapi()`, `/openapi.json` ve `/docs`.

Kök neden (2026-11-02): `app/api/map.py` `from __future__ import annotations` altında dönüş tipini
`"fastapi.responses.Response"` diye metin yazmıştı; modülde `fastapi` adı olmadığından FastAPI notu
çözemedi, onu response_model sandı ve şema üretimi pydantic `class-not-fully-defined` ile düştü
(bütün uygulamanın şeması — Atölye bayrağından bağımsız).
  · bütün uygulama şeması üretilir, `/openapi.json` 200 + geçerli JSON, `/docs` 200
  · uç uç tarama: şemadan gizli uçlar (ör. Atölye kapalıyken) dahil her APIRoute tek başına şemaya girer
    → düşen uç adıyla raporlanır
Lifespan koşmaz (`with` yok).
"""
from unittest.mock import patch

import pytest
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from starlette.testclient import TestClient

from app import main as main_mod

TOKEN = "test-openapi-anahtari"
YETKI = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def taze_sema():
    """`app.openapi()` sonucu önbelleğe alır; her test kendi üretimini ölçsün."""
    main_mod.app.openapi_schema = None
    yield
    main_mod.app.openapi_schema = None


@pytest.fixture
def istemci(taze_sema):
    with patch.object(main_mod, "AUTH_TOKEN", TOKEN):
        yield TestClient(main_mod.app, base_url="http://localhost:8001", client=("127.0.0.1", 50000))


def test_app_openapi_uretilir(taze_sema):
    sema = main_mod.app.openapi()
    assert sema["openapi"].startswith("3.")
    assert "/api/cctv/img" in sema["paths"]
    assert "/api/stream/proxy" in sema["paths"]


def test_openapi_json_200(istemci):
    r = istemci.get("/openapi.json", headers=YETKI)
    assert r.status_code == 200, r.text[:300]
    assert len(r.json()["paths"]) > 50


def test_docs_200(istemci):
    r = istemci.get("/docs", headers=YETKI)
    assert r.status_code == 200
    assert "openapi.json" in r.text


def test_her_uc_tek_basina_semaya_girer():
    """Şemadan gizli uçlar da (include_in_schema=False) — bayrak açılınca şemayı düşürmesinler."""
    dusen = []
    for r in main_mod.app.routes:
        if not isinstance(r, APIRoute):
            continue
        try:
            get_openapi(title="t", version="0", routes=[r])
        except Exception as e:  # noqa: BLE001 — hangi uç, hangi hata
            dusen.append(f"{sorted(r.methods)} {r.path} ({r.endpoint.__module__}): {type(e).__name__}")
    assert not dusen, "şemayı düşüren uçlar:\n" + "\n".join(dusen)


def test_vekil_uclari_response_model_tasimaz():
    """Response dönen vekil uçlarında response_model olmamalı (çözülmeyen not response_model'e dönüşüyordu)."""
    yollar = {"/api/cctv/img", "/api/stream/proxy"}
    bulunan = {r.path: r for r in main_mod.app.routes if isinstance(r, APIRoute) and r.path in yollar}
    assert set(bulunan) == yollar
    for r in bulunan.values():
        assert r.response_model is None, f"{r.path}: {r.response_model!r}"

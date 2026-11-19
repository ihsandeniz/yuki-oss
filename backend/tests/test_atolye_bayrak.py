"""Atölye bayrağı (`ATOLYE`) — genişletme sürümünde varsayılan AÇIK (g4, 2026-11-12; ilk sürümde kapalıydı).

  · ortamda `ATOLYE` yoksa AÇIK; tanımlıysa yalnız "true" açar (boş, "1", "false" → kapalı)
  · kapalıyken router'daki HER uç 404 — kayıtsız bir uçla aynı yanıt (var olduğu sızmaz)
  · kapalıyken OpenAPI şemasında `/api/gorev` yok
  · açıkken uçlar çalışır; bayrak istek anında okunur (kapat → yine 404)
Mevcut Atölye testleri bayrağı `atolye_acik` fikstürüyle (conftest) açar.
Lifespan koşmaz (`with` yok).
"""
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from app import config as cfg
from app import main as main_mod
from app.api import gorev as gorev_api
from app.services import gorev as gorev_mod
from app.services.gorev import GorevServisi

TOKEN = "atolye-bayrak-test-anahtari"
YETKI = {"Authorization": f"Bearer {TOKEN}"}
BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def istemci(tmp_path):
    s = GorevServisi(tmp_path / "atolye")
    with patch.object(gorev_mod, "_servis", s), patch.object(main_mod, "AUTH_TOKEN", TOKEN):
        yield TestClient(main_mod.app, base_url="http://localhost:8001", client=("127.0.0.1", 50000))


def _bayrak(env_degeri):
    """Temiz bir süreçte `app.config`'i yükleyip ATOLYE'yi okur (modül önbelleği bulaşmasın)."""
    env = {k: v for k, v in os.environ.items() if k != "ATOLYE"}
    if env_degeri is not None:
        env["ATOLYE"] = env_degeri
    cikti = subprocess.run(
        [sys.executable, "-c", "import app.config as c; print(c.ATOLYE)"],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=60,
    )
    assert cikti.returncode == 0, cikti.stderr
    return cikti.stdout.strip().splitlines()[-1]


def test_varsayilan_acik_tanimliysa_yalniz_true():
    assert _bayrak(None) == "True"         # g4: ürün varsayılanı açık
    assert _bayrak("false") == "False"
    assert _bayrak("") == "False"
    assert _bayrak("1") == "False"        # yalnız "true" açar (MASAUSTU_YUKI ile aynı kural)
    assert _bayrak("TRUE") == "True"


def _router_uclari():
    """gorev router'ındaki her (yöntem, yol) — yol parametreleri 'x' ile doldurulur."""
    uclar = []
    for r in gorev_api.router.routes:
        yol = re.sub(r"\{[^}]+\}", "x", r.path)
        assert "{" not in yol, f"doldurulmamış yol parametresi: {r.path}"
        for y in sorted(r.methods):
            uclar.append((y, yol))
    assert len(uclar) >= 10, uclar        # router boşalırsa test bir şey ölçmüyor demektir
    return uclar


def test_kapaliyken_her_uc_404(istemci, monkeypatch):
    monkeypatch.setattr(cfg, "ATOLYE", False)
    kayitsiz = istemci.get("/api/boyle-bir-uc-yok", headers=YETKI)
    assert kayitsiz.status_code == 404
    for yontem, yol in _router_uclari():
        r = istemci.request(yontem, yol, headers=YETKI, json={})
        assert r.status_code == 404, (yontem, yol, r.status_code, r.text)
        assert r.json() == kayitsiz.json(), (yontem, yol, r.text)   # kayıtsız uçtan ayırt edilmez


def test_kapaliyken_govde_dogrulamasi_da_kosmaz(istemci, monkeypatch):
    """Geçersiz gövde 422 vermemeli — 422 ucun var olduğunu ele verirdi."""
    monkeypatch.setattr(cfg, "ATOLYE", False)
    r = istemci.post("/api/gorev/baslat", headers=YETKI, json={"bilinmeyen": 1})
    assert r.status_code == 404, r.text


def test_acikken_uclar_calisir(istemci, monkeypatch):
    monkeypatch.setattr(cfg, "ATOLYE", True)
    r = istemci.get("/api/gorev", headers=YETKI)
    assert r.status_code == 200, r.text
    assert "gorevler" in r.json() or isinstance(r.json(), dict)
    r = istemci.post("/api/gorev/baslat", headers=YETKI, json={"bilinmeyen": 1})
    assert r.status_code == 422, r.text   # kapı açık → normal doğrulama


def test_bayrak_istek_aninda_okunur(istemci, monkeypatch):
    monkeypatch.setattr(cfg, "ATOLYE", True)
    assert istemci.get("/api/gorev", headers=YETKI).status_code == 200
    monkeypatch.setattr(cfg, "ATOLYE", False)
    assert istemci.get("/api/gorev", headers=YETKI).status_code == 404
    monkeypatch.setattr(cfg, "ATOLYE", True)
    assert istemci.get("/api/gorev", headers=YETKI).status_code == 200


def test_kapaliyken_semada_yok():
    """Test ortamında ATOLYE kapalı (conftest) → main yüklenirken router şemaya girmedi."""
    if os.environ.get("ATOLYE", "").lower() == "true":
        pytest.skip("ortamda ATOLYE=true — şema kapısı ölçülemez")
    # `app.openapi()` bütün uygulamada ayrı bir nedenle düşüyor (Response ileri referansı,
    # 2026-11-02 ölçüldü) → rotanın şema bayrağı doğrudan ölçülür; openapi() bu alana bakar.
    gorev = [r for r in main_mod.app.routes if getattr(r, "path", "").startswith("/api/gorev")]
    assert gorev, "main'de /api/gorev rotası yok — router bağlanmamış"
    assert not [r.path for r in gorev if r.include_in_schema]


def test_router_kapisi_bagli():
    """Kapı router düzeyinde: yeni eklenen uç da otomatik kapının arkasına girer."""
    assert any(d.dependency is gorev_api.atolye_kapisi for d in gorev_api.router.dependencies)

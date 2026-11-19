"""Fitnes (`FITNES`) bayrağı (Atölye'nin `ATOLYE` deseni → test_atolye_bayrak.py). g4 (2026-11-12):
Fitnes varsayılan KAPALI (HQ › Sistem anahtarıyla açılır). Komuta kanvasının bayrağı 11-13'te
özellikle birlikte kalktı → tests/test_komuta_paneli_yok.py.

  · tanımlıysa yalnız "true" açar (büyük/küçük harf fark etmez); tanımsızsa yukarıdaki varsayılan
  · kapalıyken `/api/fitness*` router'ındaki HER uç 404 — kayıtsız uçla aynı yanıt
  · kapalıyken OpenAPI şemasında yoklar; araçları LLM listesinde yok ve çağrılınca çalışmaz
  · `GET /api/yetki` features.fitnes bayrağı yansıtır
    — ön yüz kapısı `frontend/js/ozellik.js` bunu `=== true` ile okur
  · açıkken uçlar çalışır; bayrak istek anında okunur
Mevcut fitnes testleri bayrağı `fitnes_acik` fikstürüyle (conftest) açar.
"""
import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app import config as cfg
from app import main as main_mod
from app.api import fitness as fitness_api
from app.services import yetki
from app.services.tools import dispatcher

BACKEND = Path(__file__).resolve().parents[1]
BAYRAKLAR = {"fitnes": ("FITNES", fitness_api.router, "/api/fitness")}


@pytest.fixture
def istemci():
    return TestClient(main_mod.app, base_url="http://localhost:8001", client=("127.0.0.1", 50000))


def _bayrak(ad, env_degeri):
    """Temiz bir süreçte `app.config`'i yükleyip bayrağı okur (modül önbelleği bulaşmasın)."""
    env = {k: v for k, v in os.environ.items() if k != ad}
    if env_degeri is not None:
        env[ad] = env_degeri
    cikti = subprocess.run(
        [sys.executable, "-c", f"import app.config as c; print(c.{ad})"],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=60,
    )
    assert cikti.returncode == 0, cikti.stderr
    return cikti.stdout.strip().splitlines()[-1]


@pytest.mark.parametrize("ad,varsayilan", [("FITNES", "False")])
def test_varsayilan_ve_yalniz_true(ad, varsayilan):
    assert _bayrak(ad, None) == varsayilan     # g4 varsayılanları
    assert _bayrak(ad, "false") == "False"
    assert _bayrak(ad, "") == "False"
    assert _bayrak(ad, "1") == "False"
    assert _bayrak(ad, "TRUE") == "True"


def _router_uclari(router):
    uclar = []
    for r in router.routes:
        yol = re.sub(r"\{[^}]+\}", "x", r.path)
        for y in sorted(r.methods):
            uclar.append((y, yol))
    assert len(uclar) >= 4, uclar        # router boşalırsa test bir şey ölçmüyor demektir
    return uclar


@pytest.mark.parametrize("ozellik", sorted(BAYRAKLAR))
def test_kapaliyken_her_uc_404(istemci, monkeypatch, ozellik):
    ad, router, _ = BAYRAKLAR[ozellik]
    monkeypatch.setattr(cfg, ad, False)
    kayitsiz = istemci.get("/api/boyle-bir-uc-yok")
    assert kayitsiz.status_code == 404
    for yontem, yol in _router_uclari(router):
        r = istemci.request(yontem, yol, json={"bilinmeyen": 1})   # geçersiz gövde → 422 de sızmamalı
        assert r.status_code == 404, (yontem, yol, r.status_code, r.text)
        assert r.json() == kayitsiz.json(), (yontem, yol, r.text)


@pytest.mark.parametrize("ozellik", sorted(BAYRAKLAR))
def test_bayrak_istek_aninda_okunur(istemci, monkeypatch, tmp_path, ozellik):
    ad = BAYRAKLAR[ozellik][0]
    from app.services import fitness_store
    monkeypatch.setattr(fitness_store, "_STORE_FILE", tmp_path / "f.json")   # kullanıcı verisine yazmasın
    yol = "/api/fitness/config"
    monkeypatch.setattr(cfg, ad, True)
    assert istemci.get(yol).status_code != 404
    monkeypatch.setattr(cfg, ad, False)
    assert istemci.get(yol).status_code == 404
    monkeypatch.setattr(cfg, ad, True)
    assert istemci.get(yol).status_code != 404


@pytest.mark.parametrize("ozellik", sorted(BAYRAKLAR))
def test_kapaliyken_semada_yok(ozellik):
    ad, _, onek = BAYRAKLAR[ozellik]
    if os.environ.get(ad, "").lower() == "true":
        pytest.skip(f"ortamda {ad}=true — şema kapısı ölçülemez")
    rotalar = [r for r in main_mod.app.routes if getattr(r, "path", "").startswith(onek + "/")
               or getattr(r, "path", "") == onek]
    router_yollari = {r.path for r in BAYRAKLAR[ozellik][1].routes}
    bizim = [r for r in rotalar if r.path in router_yollari]
    assert bizim, f"main'de {onek} rotası yok — router bağlanmamış"
    assert not [r.path for r in bizim if r.include_in_schema]
    sema = set(main_mod.app.openapi()["paths"])
    assert not (sema & router_yollari), sorted(sema & router_yollari)


@pytest.mark.parametrize("ozellik", sorted(BAYRAKLAR))
def test_router_kapisi_bagli(ozellik):
    """Kapı router düzeyinde ve İLK sırada: eski kapının 403'ü varlığı ele vermesin."""
    router = BAYRAKLAR[ozellik][1]
    assert router.dependencies[0].dependency.__name__ == f"{ozellik}_kapisi"


@pytest.mark.parametrize("ozellik", sorted(BAYRAKLAR))
def test_araclar_kapaliyken_LLMde_yok_acikken_var(monkeypatch, ozellik):
    ad = BAYRAKLAR[ozellik][0]
    adlar = yetki.ARACLAR[ozellik]
    monkeypatch.setattr(cfg, ad, False)
    aktif = {t["function"]["name"] for t in dispatcher.get_active_tools()}
    assert not (aktif & adlar), sorted(aktif & adlar)
    monkeypatch.setattr(cfg, ad, True)
    aktif = {t["function"]["name"] for t in dispatcher.get_active_tools()}
    assert adlar <= aktif, sorted(adlar - aktif)


@pytest.mark.parametrize("ozellik,arac", [("fitnes", "get_fitness_summary")])
def test_kapaliyken_arac_cagrisi_calismaz(monkeypatch, ozellik, arac):
    monkeypatch.setattr(cfg, BAYRAKLAR[ozellik][0], False)
    cevap = asyncio.run(dispatcher.call_tool(arac, {"target": "example.com"}))
    assert "kapalı" in cevap, cevap


def test_arac_listeleri_kaynakla_esit():
    """yetki.ARACLAR elle tutulur → fitness_tools'taki her kayıtlı araç listede olmalı."""
    from app.services.tools import fitness_tools
    kayitli = {t["function"]["name"] for t in dispatcher.TOOLS}
    for ozellik, modul in (("fitnes", fitness_tools),):
        kaynak = {ad for ad in kayitli if callable(getattr(modul, ad, None))}
        assert kaynak == set(yetki.ARACLAR[ozellik]), (ozellik, sorted(kaynak ^ yetki.ARACLAR[ozellik]))


@pytest.mark.parametrize("acik", [False, True])
def test_api_yetki_features_bayragi_yansitir(istemci, monkeypatch, acik):
    monkeypatch.setattr(cfg, "FITNES", acik)
    f = istemci.get("/api/yetki").json()["features"]
    assert f["fitnes"] is acik
    assert f["planner"] is True          # fitnes kapalı olsa da PLAN açık


def test_bayrak_yalniz_tam_true_acar(monkeypatch):
    monkeypatch.setattr(cfg, "FITNES", "true")      # metin, bool değil → fail-closed
    assert yetki.bayrak_acik("fitnes") is False
    monkeypatch.delattr(cfg, "FITNES")
    assert yetki.bayrak_acik("fitnes") is False

"""Komuta Paneli YOK — arka uç tamamen kaldırıldı (2026-11-13).

Arayüz (PANEL sekmesi, panel-view.js/alice-canvas.js) 11-13'te kalktı; arka uç bir gün
`KOMUTA_KANVASI` bayrağı arkasında bekledi, sonra silindi. Bu dosya geri sızmayı tutar:

  · `/api/panel/*` diye bir rota yok (REST + köprü uçları: history/sites/result/state)
  · 14 panel aracı (open_panel … list_panel_shortcuts) LLM listesinde, onay kapısında,
    dış içerik listesinde, orkestratör listelerinde YOK; çağrılırsa "bilinmeyen araç"
  · `KOMUTA_KANVASI` bayrağı config'te yok; `.env`'de kalmış satır hiçbir şey açmaz
  · `GET /api/yetki` features'ta `komuta_kanvasi` / `command_panel` yok
  · panel modülleri (panel_api, panel_gecmis, panel_siteler, panel_tools) diskte yok
  · masaüstü kabuğu `<webview>` açmaz (`webviewTag: false`), panel-webview.js yok

Yuki'nin başka "panel" kavramları (HQ panelleri, pencere modu `panel`, Masaüstü Yuki
çapasındaki `panel` kutusu, ayar paneli) bu kapsamda DEĞİL ve kalır.
"""
from __future__ import annotations

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
from app.services import orchestrator, yetki
from app.services.security import dis_icerik
from app.services.tools import dispatcher
from app.services.tools.approval_gate import CRITICAL_TOOLS

BACKEND = Path(__file__).resolve().parents[1]
KOK = BACKEND.parent

PANEL_ARACLARI = frozenset({
    "open_panel", "open_split_panel", "panel_navigate", "close_panel", "close_all_panels",
    "list_panels", "list_panel_shortcuts", "panel_read", "panel_click", "panel_type",
    "panel_search", "panel_screenshot", "panel_split", "panel_unsplit",
})


def test_panel_rotasi_yok():
    yollar = [getattr(r, "path", "") for r in main_mod.app.routes]
    panel = [y for y in yollar if y == "/api/panel" or y.startswith("/api/panel/")]
    assert not panel, panel
    assert not [y for y in main_mod.app.openapi()["paths"] if y.startswith("/api/panel")]


@pytest.mark.parametrize("yontem,yol", [
    ("GET", "/api/panel/history"), ("GET", "/api/panel/sites"),
    ("POST", "/api/panel/result"), ("POST", "/api/panel/state"),
])
def test_panel_uclari_404(yontem, yol):
    istemci = TestClient(main_mod.app, base_url="http://localhost:8001", client=("127.0.0.1", 50000))
    r = istemci.request(yontem, yol, json={"req_id": "x", "panels": []})
    assert r.status_code == 404, (yol, r.status_code, r.text)


def test_panel_araclari_hicbir_listede_yok():
    kayitli = {t["function"]["name"] for t in dispatcher.TOOLS}
    assert not (kayitli & PANEL_ARACLARI), sorted(kayitli & PANEL_ARACLARI)
    assert not (CRITICAL_TOOLS & PANEL_ARACLARI)
    assert not (dis_icerik.DIS_ICERIK_ARACLARI & PANEL_ARACLARI)
    for ad, deger in vars(orchestrator).items():
        if isinstance(deger, (set, frozenset)) and all(isinstance(x, str) for x in deger):
            assert not (deger & PANEL_ARACLARI), (ad, sorted(deger & PANEL_ARACLARI))
    for ozellik, adlar in yetki.ARACLAR.items():
        assert not (adlar & PANEL_ARACLARI), ozellik


def test_panel_araci_cagrilirsa_calismaz():
    cevap = asyncio.run(dispatcher.call_tool("open_panel", {"target": "example.com"}))
    assert cevap == "Hata: Geçersiz araç.", cevap


def test_bayrak_ve_ozellik_adlari_yok(monkeypatch):
    assert not hasattr(cfg, "KOMUTA_KANVASI")
    assert "komuta_kanvasi" not in yetki.BAYRAKLI
    assert "command_panel" not in yetki.FEATURES
    assert "komuta_kanvasi" not in yetki.ARACLAR
    istemci = TestClient(main_mod.app, base_url="http://localhost:8001", client=("127.0.0.1", 50000))
    f = istemci.get("/api/yetki").json()["features"]
    assert "komuta_kanvasi" not in f and "command_panel" not in f, sorted(f)


def test_env_satiri_hicbir_sey_acmaz():
    """Eski kurulumun `.env`'inde `KOMUTA_KANVASI=true` kalsa da rota/araç geri gelmez."""
    env = {**os.environ, "KOMUTA_KANVASI": "true"}
    kod = ("from app.main import app; from app.services.tools import dispatcher as d;"
           "print(any(getattr(r,'path','').startswith('/api/panel') for r in app.routes),"
           " any(t['function']['name']=='open_panel' for t in d.get_active_tools()))")
    c = subprocess.run([sys.executable, "-c", kod], cwd=BACKEND, env=env,
                       capture_output=True, text=True, timeout=120)
    assert c.returncode == 0, c.stderr[-2000:]
    assert c.stdout.strip().splitlines()[-1] == "False False", c.stdout


@pytest.mark.parametrize("yol", [
    "app/api/panel_api.py", "app/services/panel_gecmis.py",
    "app/services/panel_siteler.py", "app/services/tools/panel_tools.py",
])
def test_panel_modulu_diskte_yok(yol):
    assert not (BACKEND / yol).exists(), yol


def test_masaustu_kabugu_webview_acmaz():
    elektron = KOK / "electron"
    assert not (elektron / "panel-webview.js").exists()
    src = (elektron / "uygulama.js").read_text(encoding="utf-8")
    assert re.search(r"webviewTag:\s*false\b", src), "BrowserWindow webviewTag açıkça false olmalı"
    assert "panel-webview" not in src and "kanvasBayragi" not in src
    pre = (elektron / "preload.js").read_text(encoding="utf-8")
    assert "yukiPanel" not in pre, "Komuta Paneli köprüsü preload'dan kalkmalı"


def test_kaynakta_bayrak_izi_yok():
    """Backend/electron kaynağında (testler hariç) `KOMUTA_KANVASI` / `komuta_kanvasi` geçmez."""
    izler = []
    for kok in (BACKEND / "app", KOK / "electron"):
        for p in kok.rglob("*"):
            if p.suffix not in {".py", ".js"} or "node_modules" in p.parts or p.name.endswith(".test.js"):
                continue
            s = p.read_text(encoding="utf-8", errors="ignore")
            if "KOMUTA_KANVASI" in s or "komuta_kanvasi" in s:
                izler.append(str(p.relative_to(KOK)))
    assert not izler, izler

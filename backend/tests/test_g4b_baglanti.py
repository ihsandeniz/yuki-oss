"""G4b entegrasyonu (2026-11-12) — kamera görüşü, ses kimliği ve güvenli dosyanın ana uygulamaya bağlantısı.

  · varsayılan: GORUS, SES_KIMLIK kapalı (temiz süreçte ölçülür), güvenli dosya kendi ayarıyla kapalı
  · main.py: üç router bağlı; biyometrik ikisi kapalıyken 404 ve şemada yok
  · `kameraya_bak` aracı: bayrak kapalıyken LLM'e sunulmaz, çağrılsa da kareye dokunmaz
  · ses hattı (`/ws/realtime`): ses kimliği reddederse komut STT'ye hiç girmez; None ise geçer;
    onay bekleyen araç varken sıkı eşik istenir
  · dolgu sesi bağlantı açılışında ısınır (açıksa)
"""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app import config as cfg
from app.main import app
from app.services import yetki

BACKEND = Path(__file__).resolve().parents[1]
c = TestClient(app, base_url="http://localhost:8001", client=("127.0.0.1", 50000))


def test_temiz_surecte_biyometrik_kapali_ve_semada_yok():
    env = {k: v for k, v in os.environ.items() if k not in ("GORUS", "SES_KIMLIK")}
    env["YUKI_ANAHTARLIK"] = "0"
    kod = ("import json, app.main as m, app.config as cfg\n"
           "def s(o): return any(r.include_in_schema for r in m.app.routes if getattr(r,'path','').startswith(o))\n"
           "def v(o): return any(getattr(r,'path','').startswith(o) for r in m.app.routes)\n"
           "print(json.dumps({'GORUS': cfg.GORUS, 'SES_KIMLIK': cfg.SES_KIMLIK,"
           " 'gorus_var': v('/api/gorus'), 'gorus_sema': s('/api/gorus'),"
           " 'ses_var': v('/api/ses-kimlik'), 'ses_sema': s('/api/ses-kimlik'),"
           " 'dosya_var': v('/api/guvenli-dosya'), 'ws_gorus': v('/ws/gorus')}))\n")
    r = subprocess.run([sys.executable, "-c", kod], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-1500:]
    d = json.loads(r.stdout.strip().splitlines()[-1])
    assert d == {"GORUS": False, "SES_KIMLIK": False, "gorus_var": True, "gorus_sema": False,
                 "ses_var": True, "ses_sema": False, "dosya_var": True, "ws_gorus": True}, d


@pytest.mark.parametrize("yol", ["/api/gorus/durum", "/api/ses-kimlik/durum"])
def test_kapaliyken_404(monkeypatch, yol):
    monkeypatch.setattr(cfg, "GORUS", False)
    monkeypatch.setattr(cfg, "SES_KIMLIK", False)
    assert c.get(yol).status_code == 404


@pytest.mark.parametrize("yol,bayrak", [("/api/gorus/durum", "GORUS"), ("/api/ses-kimlik/durum", "SES_KIMLIK")])
def test_acikken_bagli(monkeypatch, yol, bayrak):
    monkeypatch.setattr(cfg, bayrak, True)
    assert c.get(yol).status_code == 200


def test_guvenli_dosya_bagli_ve_kapali_gelir():
    r = c.get("/api/guvenli-dosya/durum")
    assert r.status_code == 200, r.text
    assert c.post("/api/guvenli-dosya/hazirla", json={}).status_code in (404, 422)


def test_kameraya_bak_bayrakla_sunulur(monkeypatch):
    from app.services.tools import dispatcher
    assert "kameraya_bak" in {t["function"]["name"] for t in dispatcher.TOOLS}
    monkeypatch.setattr(cfg, "GORUS", False)
    assert yetki.tool_allowed("kameraya_bak") is False
    assert yetki.ozet()["features"]["gorus"] is False
    monkeypatch.setattr(cfg, "GORUS", True)
    assert yetki.tool_allowed("kameraya_bak") is True


def test_kameraya_bak_kapaliyken_kareye_dokunmaz(monkeypatch):
    from app.services import gorus_bak
    from app.services.tools import dispatcher
    monkeypatch.setattr(cfg, "GORUS", False)

    async def patla(*a, **k):
        raise AssertionError("kapalıyken kareye bakıldı")
    monkeypatch.setattr(gorus_bak, "bak", patla)
    sonuc = asyncio.run(dispatcher.call_tool("kameraya_bak", {}))
    assert "bakam" in sonuc.lower() or "kapal" in sonuc.lower() or "not" in sonuc.lower(), sonuc


def test_kamera_alani_mesajla_acilir():
    from app.services.tools import alan_secici
    assert "kamera" in alan_secici.alanlari_esle("Yuki bak, elimde ne var?")
    assert "kamera" not in alan_secici.alanlari_esle("bugün hava nasıl")
    from app.services.tools import dispatcher
    assert "kameraya_bak" in alan_secici._alan_araclari({"kamera"}, dispatcher.TOOLS)


# ── ses hattı ────────────────────────────────────────────────────────────────

@pytest.fixture
def ses_hatti(monkeypatch):
    from fastapi import FastAPI

    import app.config as config
    from app.api import websocket as W
    from app.services import ag_ayari
    monkeypatch.setattr(config, "AUTH_TOKEN", "")
    monkeypatch.setattr(ag_ayari, "ws_izinli", lambda *a, **k: True)
    monkeypatch.setattr(W, "ensure_wav", lambda b: b)
    monkeypatch.setattr(W, "detect_speech", lambda b: True)
    monkeypatch.setattr(W, "analyze_voice_emotion", lambda b: {"emotion": "neutral", "energy": 0.0})
    monkeypatch.setattr(W, "check_wake_word", lambda t: True)
    stt = []

    async def _transcribe(b):
        stt.append(b)
        return ""          # boş transkript → tur hemen biter (voice_hint empty_transcript)
    monkeypatch.setattr(W, "transcribe", _transcribe)
    app_ = FastAPI()
    app_.include_router(W.router)
    with TestClient(app_) as istemci:
        yield W, istemci, stt


def _ilk_ipucu(ws):
    for _ in range(20):
        m = ws.receive_json()
        if m.get("type") == "voice_hint":
            return m
    raise AssertionError("voice_hint gelmedi")


def test_ses_kimligi_reddederse_stt_yok(ses_hatti, monkeypatch):
    W, istemci, stt = ses_hatti
    from app.services import ses_kimlik
    monkeypatch.setattr(ses_kimlik, "dogrula", lambda b: ses_kimlik.Sonuc(skor=0.05, sure_sn=3.0))
    with istemci.websocket_connect("/ws/realtime") as ws:
        ws.send_bytes(b"SES")
        m = _ilk_ipucu(ws)
    assert m["reason"] == "speaker_mismatch" and stt == []


def test_ses_kimligi_none_ise_gecer(ses_hatti, monkeypatch):
    W, istemci, stt = ses_hatti
    from app.services import ses_kimlik
    monkeypatch.setattr(ses_kimlik, "dogrula", lambda b: None)
    with istemci.websocket_connect("/ws/realtime") as ws:
        ws.send_bytes(b"SES")
        m = _ilk_ipucu(ws)
    assert m["reason"] == "empty_transcript" and stt == [b"SES"]


def test_onay_beklerken_sikı_esik(ses_hatti, monkeypatch):
    W, istemci, stt = ses_hatti
    from app.services import ses_kimlik
    istenen = []

    class S(ses_kimlik.Sonuc):
        def kabul(self, onay=False):
            istenen.append(onay)
            return True
    monkeypatch.setattr(ses_kimlik, "dogrula", lambda b: S(skor=0.9, sure_sn=3.0))
    monkeypatch.setattr(W, "onay_bekliyor", lambda: True)
    with istemci.websocket_connect("/ws/realtime") as ws:
        ws.send_bytes(b"SES")
        _ilk_ipucu(ws)
    assert istenen == [True] and stt == [b"SES"]


@pytest.mark.parametrize("acik", [False, True])
def test_dolgu_baglanti_acilisinda_isinir(ses_hatti, monkeypatch, acik):
    W, istemci, _ = ses_hatti
    from app.services import dolgu_sesi
    monkeypatch.setattr(cfg, "DOLGU_SESI", acik)
    dolgu_sesi._onbellek.clear()
    cagri = []
    monkeypatch.setattr(dolgu_sesi, "_isit", lambda s: cagri.append(1))
    with istemci.websocket_connect("/ws/realtime") as ws:
        ws.send_text(json.dumps({"type": "ping"}))
    assert cagri == ([1] if acik else [])


def test_on_yuz_gorus_paneli_bagli():
    kok = BACKEND.parent / "frontend"
    idx = (kok / "index.html").read_text(encoding="utf-8")
    for d in ("/ui/css/gorus.css?v=", "/ui/js/gorus.js?v=", "/ui/js/ses-kimlik.js?v=", "/ui/js/gorus-panel.js?v="):
        assert d in idx, d
    # panel betiği bağımlılıklarından sonra yüklenir
    assert idx.index("/ui/js/gorus.js") < idx.index("/ui/js/ses-kimlik.js") < idx.index("/ui/js/gorus-panel.js")
    hq = (kok / "js/intro-sequences.js").read_text(encoding="utf-8")
    blok = hq[hq.index("if(cat.extra==='gorus' && window.YukiGorusPanel)"):][:400]
    assert "data-gorus-panel" in blok and "YukiGorusPanel.kur(_gp)" in blok and "_gp.hidden=true" in blok


def test_onay_bekliyor_bekleyen_pencereyi_gorur(monkeypatch):
    from app.services.tools import approval_gate as ag
    monkeypatch.setattr(ag, "_pending", {})
    assert ag.onay_bekliyor() is False
    monkeypatch.setattr(ag, "_pending", {"x": (asyncio.Event(), [])})
    assert ag.onay_bekliyor() is True


def test_backend_opencv_olmadan_acilir():
    """Boş Linux'ta OpenCV yüklenemeyebilir (libxcb yok): kamera görüşü kapalıyken backend yine açılmalı
    (G4b temiz kurulum sınavı bunu yakaladı). cv2 yalnız kare işlenirken yüklenir."""
    kod = ("import sys; sys.modules['cv2'] = None\n"
           "import app.main\n"
           "from app.services import gorus_kare\n"
           "print('ok')\n")
    env = {**os.environ, "YUKI_ANAHTARLIK": "0"}
    r = subprocess.run([sys.executable, "-c", kod], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and r.stdout.strip().endswith("ok"), r.stderr[-1500:]


def test_kameraya_bak_ekip_iscisine_kapali():
    from app.services import orchestrator as orch
    assert "kameraya_bak" in orch.WORKER_MUTATING_TOOLS
    assert "kameraya_bak" not in orch.WORKER_READONLY_TOOLS


def test_sistem_odasi_gorus_panelini_ilan_eder():
    from app.api import settings_api
    oda = next(c for c in settings_api.CATEGORIES if c["id"] == "gelistirici")
    assert oda.get("extra") == settings_api.EXTRA_GORUS == "gorus"

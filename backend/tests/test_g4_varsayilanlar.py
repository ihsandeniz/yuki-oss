"""G4 entegrasyonu (2026-11-12) — genişletme özelliklerinin varsayılanları ve bağlantıları.

Karar (g4): Atölye varsayılan AÇIK, Fitnes ayarlardan açılır (kapalı), dolgu sesi kapalı.
Komuta kanvası 11-13'te tamamen kalktı (tests/test_komuta_paneli_yok.py); burada yalnız yokluğu görünür. Bu dosya üç şeyi ölçer:
  · ürün varsayılanı — test sürecinin ortamı (conftest ATOLYE=false) OLMADAN,
    temiz bir süreçte `app.main` yüklenince hangi router şemada, `/api/yetki` ne diyor
  · zamanlayıcı bağlantısı — `scheduler.startup` Atölye öneri turunu yalnız ATOLYE açıkken,
    Fitnes bildirim işlerini her zaman kaydeder; Fitnes işi koşarken bayrağa bakar
  · ayar anahtarları — FITNES ve DOLGU_SESI HQ'dan canlı açılır; ATOLYE ayar ucundan
    yazılamaz (yalnız `.env`)
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
from app import config_manager
from app.api import settings_api
from app.main import app
from app.services import dolgu_sesi, fitnes_bildirim, scheduler

BACKEND = Path(__file__).resolve().parents[1]
BAYRAKLAR = ("ATOLYE", "KOMUTA_KANVASI", "FITNES", "DOLGU_SESI")  # eski bayrak da ortamdan silinir

c = TestClient(app, base_url="http://localhost:8001", client=("127.0.0.1", 50000))


def _temiz_surec(kod: str, ek_env: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in BAYRAKLAR}
    env.update(ek_env or {})
    env["YUKI_ANAHTARLIK"] = "0"
    r = subprocess.run([sys.executable, "-c", kod], cwd=BACKEND, env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


_SEMA_KODU = (
    "import json, app.main as m, app.config as cfg\n"
    "from app.services import yetki\n"
    "def s(o): return any(r.include_in_schema for r in m.app.routes if getattr(r,'path','').startswith(o))\n"
    "f = yetki.ozet()['features']\n"
    "print(json.dumps({'gorev': s('/api/gorev'), 'panel': s('/api/panel'), 'fitness': s('/api/fitness'),\n"
    "  'f_kanvas': 'komuta_kanvasi' in f, 'f_fitnes': f['fitnes'], 'dolgu': cfg.DOLGU_SESI}))\n"
)


def test_urun_varsayilani_atolye_acik_kanvas_yok_fitnes_dolgu_kapali():
    d = _temiz_surec(_SEMA_KODU)
    # 11-13: Komuta kanvası tamamen kalktı — panel rotası da özellik adı da yok.
    assert d == {"gorev": True, "panel": False, "fitness": False,
                 "f_kanvas": False, "f_fitnes": False, "dolgu": False}, d


def test_env_false_ikisini_de_kapatir_fitnes_true_acar():
    d = _temiz_surec(_SEMA_KODU, {"ATOLYE": "false", "FITNES": "true"})
    assert d["gorev"] is False and d["panel"] is False and d["f_kanvas"] is False
    assert d["fitness"] is True and d["f_fitnes"] is True


# ── zamanlayıcı ──────────────────────────────────────────────────────────────

class SahteZamanlayici:
    def __init__(self):
        self.isler: dict[str, dict] = {}
        self.basladi = False

    def get_job(self, id_):
        return self.isler.get(id_)

    def add_job(self, fn, trigger=None, id=None, **kw):  # noqa: A002 — APScheduler imzası
        self.isler[id] = {"fn": fn, "trigger": trigger, **kw}

    def remove_job(self, id_):
        self.isler.pop(id_, None)

    def start(self):
        self.basladi = True


@pytest.fixture
def sahte_sched(monkeypatch):
    s = SahteZamanlayici()
    monkeypatch.setattr(scheduler, "SCHEDULER_ENABLED", True)
    monkeypatch.setattr(scheduler, "get_scheduler", lambda: s)
    monkeypatch.setattr(scheduler, "register_reminders", lambda: None)
    monkeypatch.setattr(scheduler, "yedekleme_isini_kur", lambda: None)
    return s


def test_startup_atolye_acikken_oneri_turu_kayitli(sahte_sched, monkeypatch):
    monkeypatch.setattr(cfg, "ATOLYE", True)
    scheduler.startup()
    assert sahte_sched.basladi
    assert "atolye_oneri_turu" in sahte_sched.isler
    assert sahte_sched.isler["atolye_oneri_turu"]["trigger"] == "interval"
    assert "atolye_oneri_acilis" in sahte_sched.isler


def test_startup_atolye_kapaliyken_oneri_turu_yok(sahte_sched, monkeypatch):
    monkeypatch.setattr(cfg, "ATOLYE", False)
    scheduler.startup()
    assert not [k for k in sahte_sched.isler if k.startswith("atolye_")]


@pytest.mark.parametrize("fitnes", [False, True])
def test_startup_fitnes_isleri_her_zaman_kayitli(sahte_sched, monkeypatch, fitnes):
    """FITNES ayardan canlı açılabildiği için işler bayraktan bağımsız kaydedilir."""
    monkeypatch.setattr(cfg, "FITNES", fitnes)
    scheduler.startup()
    for ad in ("fitnes_hatirlatma", "fitnes_lig", "fitnes_haftalik", "fitnes_haftalik_telafi"):
        assert ad in sahte_sched.isler, ad
    assert sahte_sched.isler["fitnes_hatirlatma"]["hour"] == 21


@pytest.mark.parametrize("acik", [False, True])
def test_fitnes_isi_kosarken_bayraga_bakar(monkeypatch, acik):
    monkeypatch.setattr(cfg, "FITNES", acik)
    cagri = []

    async def is_():
        cagri.append(1)

    asyncio.run(fitnes_bildirim._is("deneme", is_))
    assert cagri == ([1] if acik else [])


# ── ayar anahtarları ─────────────────────────────────────────────────────────

def test_ayar_semasi_ve_izinler():
    sema = {s["key"]: s for s in settings_api.SETTINGS_SCHEMA}
    assert sema["FITNES"]["type"] == "toggle" and sema["FITNES"]["cat"] == "gelistirici"
    assert sema["DOLGU_SESI"]["type"] == "toggle" and sema["DOLGU_SESI"]["cat"] == "ses"
    for k in ("FITNES", "DOLGU_SESI"):
        assert config_manager.ALLOWED_KEYS[k] is bool
        assert k in settings_api.CANLI_UYGULANAN
    for k in ("ATOLYE",):
        assert k not in config_manager.ALLOWED_KEYS
        assert k not in sema


@pytest.fixture
def bayrak_geri():
    eski = {k: getattr(cfg, k) for k in ("FITNES", "DOLGU_SESI")}
    yield
    for k, v in eski.items():
        setattr(cfg, k, v)


def test_fitnes_anahtari_canli_acar_ve_depoyu_kurar(bayrak_geri, monkeypatch):
    from app.api import fitness as fitness_api
    kuruldu = []

    async def sahte_kur():
        kuruldu.append(1)
        return False

    monkeypatch.setattr(fitness_api, "init_fitness_db", sahte_kur)
    cfg.FITNES = False
    assert c.get("/api/yetki").json()["features"]["fitnes"] is False
    r = c.post("/api/settings/FITNES", json={"value": True})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["value"] is True and d["needs_restart"] is False
    assert cfg.FITNES is True and kuruldu == [1]
    assert c.get("/api/yetki").json()["features"]["fitnes"] is True
    assert c.get("/api/fitness/config").status_code != 404
    # kapatmak kurulum çağırmaz, kapı hemen kapanır
    r = c.post("/api/settings/FITNES", json={"value": False})
    assert r.status_code == 200 and cfg.FITNES is False and kuruldu == [1]
    assert c.get("/api/fitness/config").status_code == 404


def test_dolgu_anahtari_canli(bayrak_geri):
    cfg.DOLGU_SESI = False
    assert dolgu_sesi.acik() is False
    r = c.post("/api/settings/DOLGU_SESI", json={"value": True})
    assert r.status_code == 200 and r.json()["needs_restart"] is False
    assert dolgu_sesi.acik() is True


@pytest.mark.parametrize("anahtar", ["ATOLYE", "KOMUTA_KANVASI"])   # eski bayrak da bilinmeyen anahtar → 400
def test_atolye_kanvas_ayar_ucundan_yazilamaz(anahtar):
    assert c.post(f"/api/settings/{anahtar}", json={"value": False}).status_code == 400


# ── metinler (i18n) ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("dil,beklenen_bitti,beklenen_baslik", [
    ("tr", "Site görevi bitti — sonucu Atölye'de.", "Yuki · Atölye"),
    ("en", "Site task finished — see the result in Workshop.", "Yuki · Workshop"),
])
def test_atolye_bitis_bildirimi_arayuz_dilinde(monkeypatch, dil, beklenen_bitti, beklenen_baslik):
    import app.mesajlar as mesajlar
    from app.services import gorev_bildirim as gb
    monkeypatch.setattr(mesajlar, "mevcut_dil", lambda: dil)
    assert gb.bitis_metni({"durum": "bitti", "tur": "site"}) == beklenen_bitti
    assert gb.baslik() == beklenen_baslik
    assert gb.bitis_metni({"durum": "durdu", "neden": "durdur", "tur": "site"}) is None
    for durum in ("yarim", "hata", "durdu"):
        m = gb.bitis_metni({"durum": durum, "tur": "bilinmeyen"})
        assert m and "{" not in m and not m.startswith("atolye."), m


def test_hq_kaydi_ozellik_kapisini_tazeler():
    """FITNES kaydedilince ana sayfa + açık iframe'lerdeki ozellik.js kapısı yeniden sorulur
    (tarayıcı ölçümü: reports/…/g4-entegre/hq_fitnes.py)."""
    src = (BACKEND.parent / "frontend/js/intro-sequences.js").read_text(encoding="utf-8")
    govde = src[src.index("window.hqSet=async function"):]
    govde = govde[:govde.index("return false;")]
    assert "if(key==='FITNES') _ozellikTazele();" in govde
    tazele = src[src.index("function _ozellikTazele(){"):]
    tazele = tazele[:tazele.index("\n  }\n")]
    assert "window.YukiOzellik.tazele()" in tazele and "querySelectorAll('iframe')" in tazele

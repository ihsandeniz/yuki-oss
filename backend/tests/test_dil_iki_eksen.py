"""İki dil ekseni — arayüz (tr/en) ≠ konuşma (tr/en/ja) (2026-10-04, geliştirici).

Bağlam: tek eksende (09-18) Japonca konuşmayı seçen kullanıcının arayüzü
İngilizce'ye düşüyordu (`ja` sözlüğü yok → yedek zinciri `ja → en`).

Ölçülenler:
  ① konuşma kapısı arayüze, arayüz kapısı (ayrı seçilmiş) konuşmaya dokunmaz
  ② varsayılan konuşma = arayüz dili (birlikteyken birlikte taşınır)
  ③ Japonca arayüz YOK (kapı reddeder, API listesinde yok)
  ④ göç: kayıtlı `ja` → konuşma ja + arayüz en (bugün gördüğü), sessiz kayıp yok
  ⑤ restart'ı ikisi de aşar (GERÇEK ikinci süreç)
  ⑥ backend ekran metni (`M()`) arayüzden, LLM çıktı dili konuşmadan
  ⑦ tek kapı: genel ayar ucu `ARAYUZ_DILI`'yi yazamaz; WS olayı iki ekseni taşır
  ⑧ frontend: WS/açılış konuşma kodunu arayüze uygulamıyor
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND_DIR.parent / "frontend"


@pytest.fixture
def eksenler(tmp_path, monkeypatch):
    """Kendi config.user.json'ı + iki eksenin süreç içi durumunu geri yükle."""
    from app import config, config_manager

    hedef = tmp_path / "config.user.json"
    monkeypatch.setattr(config_manager, "CONFIG_USER_PATH", hedef)
    monkeypatch.setattr(config_manager, "_cache", None)
    onceki = (config._current_language, config.ASSISTANT_LANGUAGE,
              config._arayuz_dili, config.ARAYUZ_DILI)
    config.set_language("tr", persist=False)
    config._arayuz_dili = config.ARAYUZ_DILI = "tr"
    yield hedef
    (config._current_language, config.ASSISTANT_LANGUAGE,
     config._arayuz_dili, config.ARAYUZ_DILI) = onceki
    config._prompt_cache.clear()


def _kayit(hedef: Path) -> dict:
    return json.loads(hedef.read_text(encoding="utf-8")) if hedef.exists() else {}


# ① ─────────────────────────────────────────────────────────────────────────

def test_konusma_ja_arayuzu_degistirmez(eksenler):
    from app import config

    assert config.set_language("ja") is True
    assert config.get_language() == "ja"
    assert config.get_arayuz_dili() == "tr", "Japonca konuşma arayüzü sürüklüyor (09-18 arızası)"
    assert _kayit(eksenler).get("ARAYUZ_DILI") == "tr"


def test_ayri_secilmis_konusma_arayuz_degisiminde_kalir(eksenler):
    from app import config

    config.set_language("ja")
    assert config.set_arayuz_dili("en") is True
    assert config.get_arayuz_dili() == "en"
    assert config.get_language() == "ja", "arayüz değişimi ayrı seçilmiş konuşmayı ezdi"
    config.set_arayuz_dili("tr")
    assert config.get_language() == "ja"
    assert _kayit(eksenler) == {"ARAYUZ_DILI": "tr", "ASSISTANT_LANGUAGE": "ja"}


# ② ─────────────────────────────────────────────────────────────────────────

def test_varsayilan_konusma_arayuzle_birlikte_tasinir(eksenler):
    from app import config

    assert config.get_language() == config.get_arayuz_dili() == "tr"
    config.set_arayuz_dili("en")
    assert config.get_language() == "en", "ayrı seçilmemiş konuşma arayüzü izlemedi"
    assert _kayit(eksenler) == {"ARAYUZ_DILI": "en", "ASSISTANT_LANGUAGE": "en"}


# ③ ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("deger", ["ja", "japonca", "日本語", "de", ""])
def test_japonca_ve_bilinmeyen_arayuz_reddedilir(eksenler, deger):
    from app import config

    assert config.set_arayuz_dili(deger) is False
    assert config.get_arayuz_dili() == "tr"
    assert "ARAYUZ_DILI" not in _kayit(eksenler)


def test_arayuz_dilleri_sozluklerle_ayni():
    """Arayüz dili listesi = frontend'de TAM sözlüğü olan diller. `ja.js` kısmi."""
    from app.config import ARAYUZ_DILLERI, LANGUAGES

    assert ARAYUZ_DILLERI == ("tr", "en")
    assert set(ARAYUZ_DILLERI) <= set(LANGUAGES)
    for kod in ARAYUZ_DILLERI:
        assert (FRONTEND / "js" / "diller" / f"{kod}.js").exists()


# ④ + ⑤ — gerçek süreçlerle ──────────────────────────────────────────────────

def _kos(ortam: dict, kod: str) -> str:
    r = subprocess.run([sys.executable, "-c", kod], cwd=BACKEND_DIR, env=ortam,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _ortam(ayar: Path) -> dict:
    o = {**os.environ, "CONFIG_USER_PATH": str(ayar), "ASSISTANT_LANGUAGE": "tr"}
    o.pop("ARAYUZ_DILI", None)
    return o


OKU = "from app import config as c; print(c.get_language(), c.get_arayuz_dili())"


def test_goc_kayitli_ja_kurulum_arayuz_en_konusma_ja(tmp_path):
    """İki eksenden önceki kurulum: yalnız `ASSISTANT_LANGUAGE=ja` kayıtlı.
    Bugün İngilizce arayüz görüyor → ayrıldıktan sonra da görmeli; konuşma ja kalmalı.
    Ardından konuşmayı TR yapınca arayüz EN'de KALMALI (göç diske sabitlenir)."""
    ayar = tmp_path / "config.user.json"
    ayar.write_text(json.dumps({"ASSISTANT_LANGUAGE": "ja", "PERSONA_VOICES": ""}))
    ortam = _ortam(ayar)

    assert _kos(ortam, OKU) == "ja en"
    assert "ARAYUZ_DILI" not in _kayit(ayar), "açılış/içe aktarma diske yazmamalı"

    _kos(ortam, "from app import config as c; c.set_language('tr')")
    kayit = _kayit(ayar)
    assert kayit["ARAYUZ_DILI"] == "en" and kayit["ASSISTANT_LANGUAGE"] == "tr"
    assert kayit.get("PERSONA_VOICES") == "", "göç başka kaydı sildi"
    assert _kos(ortam, OKU) == "tr en", "konuşma değişince arayüz istemeden döndü"


@pytest.mark.parametrize("eski, beklenen", [("tr", "tr tr"), ("en", "en en")])
def test_goc_tr_en_kurulumu_aynen_kalir(tmp_path, eski, beklenen):
    ayar = tmp_path / "config.user.json"
    ayar.write_text(json.dumps({"ASSISTANT_LANGUAGE": eski}))
    assert _kos(_ortam(ayar), OKU) == beklenen


def test_iki_eksen_gercek_restarti_asar(tmp_path):
    ayar = tmp_path / "config.user.json"
    ortam = _ortam(ayar)
    _kos(ortam, "from app import config as c; c.set_arayuz_dili('en'); c.set_language('ja')")
    assert _kos(ortam, OKU) == "ja en"
    _kos(ortam, "from app import config as c; c.set_arayuz_dili('tr')")
    assert _kos(ortam, OKU) == "ja tr"


# ⑥ ─────────────────────────────────────────────────────────────────────────

def test_ekran_metni_arayuzden_llm_cikti_dili_konusmadan(eksenler):
    from app import config
    from app.mesajlar import KATALOG, M

    config.set_language("ja")
    assert M("llm.ulasilamadi") == KATALOG["tr"]["llm.ulasilamadi"], \
        "Japonca konuşan TR arayüzlü kullanıcıya ekran metni İngilizce gitti"
    assert config.yanit_dili() == "日本語"
    assert "日本語" in config.get_lang_config()["prompt_rule"]


# ⑦ ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_iki_ekseni_ayri_yazar_ve_olay_ikisini_tasir(eksenler, mocker):
    import httpx
    from httpx import ASGITransport
    from app.main import app
    from app.services.event_bus import bus

    yayin = mocker.patch.object(bus, "publish", new=mocker.AsyncMock())
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as c:
        d = (await c.get("/api/language")).json()
        assert d["language"] == "tr" and d["arayuz"] == "tr"
        assert [o["code"] for o in d["arayuz_available"]] == ["tr", "en"], "menüde JA arayüz seçeneği var"
        assert {o["code"] for o in d["available"]} == {"tr", "ja", "en"}

        d = (await c.post("/api/language", json={"language": "ja"})).json()
        assert d["ok"] and d["language"] == "ja" and d["arayuz"] == "tr"
        yayin.assert_awaited_with("language_changed", {"language": "ja", "arayuz": "tr"})

        d = (await c.post("/api/language", json={"arayuz": "en"})).json()
        assert d["ok"] and d["language"] == "ja" and d["arayuz"] == "en"
        yayin.assert_awaited_with("language_changed", {"language": "ja", "arayuz": "en"})

        d = (await c.post("/api/language", json={"arayuz": "ja"})).json()
        assert d["ok"] is False

        r = await c.post("/api/settings/ARAYUZ_DILI", json={"value": "en"})
        assert r.status_code == 400, "genel ayar ucu arayüz dilini kapıyı atlayarak yazıyor"


def test_sesli_komut_araci_yalniz_konusmayi_degistirir(eksenler):
    import asyncio
    from app import config
    from app.services.tools import dispatcher

    async def kos():
        return await dispatcher._call_tool_impl("set_language", {"language": "japonca"})

    asyncio.run(kos())
    assert config.get_language() == "ja"
    assert config.get_arayuz_dili() == "tr"


# ⑧ — frontend statik kapılar ────────────────────────────────────────────────

def test_frontend_ws_ve_acilis_konusma_kodunu_arayuze_uygulamiyor():
    core = (FRONTEND / "js" / "core.js").read_text(encoding="utf-8")
    assert not re.search(r"sunucudan\(\s*d\.language", core), \
        "core.js konuşma dilini (d.language) arayüze uyguluyor — 09-18 tek ekseni geri geldi"
    dil = (FRONTEND / "js" / "dil.js").read_text(encoding="utf-8")
    assert re.search(r"YALNIZ_KONUSMA\s*=\s*\{\s*ja:\s*'en'\s*\}", dil)
    assert "!YALNIZ_KONUSMA[kod]" in dil, "gecerliMi Japonca'yı arayüz dili sayıyor"


def test_menude_iki_ayri_secim_var():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert 'id="lang-toggle-btn"' in html and 'onclick="toggleLanguage()"' in html
    assert 'id="arayuz-toggle-btn"' in html and 'onclick="toggleArayuzDili()"' in html
    assert re.search(r'<span id="arayuz-label" data-i18n-yok>', html)


@pytest.mark.asyncio
async def test_language_changed_ws_aboneligine_ulasir():
    """WS forwarder `subscribe_all()` kullanır; olay o listede yoksa istemci hiç görmez.
    2026-10-04'e kadar yoktu — sesli komutla dil değişimi ekrana ulaşmıyordu."""
    from app.services.event_bus import EventBus

    b = EventBus()
    q = b.subscribe_all()
    await b.publish("language_changed", {"language": "ja", "arayuz": "tr"})
    assert q.get_nowait() == {"type": "language_changed", "language": "ja", "arayuz": "tr"}

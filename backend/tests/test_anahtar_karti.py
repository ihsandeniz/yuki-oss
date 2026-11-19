"""HQ › ANAHTAR · BAĞLANTI KARTI — panel bekçileri (2026-09-27 panel 8).

geliştirici taslak A'yı seçti: anahtar kayıtlıyken durum (servis · anahtar · model), yokken üç adım.
Kapanan kusurlar:
  ① Model değişikliği kalıcı değildi: panelden seçilecek model için tek yol `/api/llm/config`'di ve o
     yalnız çalışan süreci değiştiriyor (`.env`'e yazmıyor) → yeniden başlatınca eski model geri geliyordu.
     Yeni `/api/llm/sec`: kayıtlı anahtarla ÖNCE dener, geçerse `.env`'e yazar (anahtar yolunun kuralı).
  ② Anahtarı zaten kayıtlı servise geçmek için anahtarı yeniden yapıştırmak gerekiyordu.
  ③ Panel yalnız ilk açılışta yükleniyordu (`_loaded.key`) → sohbetten değişen model bayat kalıyordu.
  ④ Sabit yedek model listesi HTML'deydi (08-01 dersi: sabit liste ürünü öldürür; yedek sunucuda).
Testler ağa ÇIKMAZ.
"""
import re
from pathlib import Path

import pytest

from app.api import llm_config_api as api
from app.services import llm as _llm
from app.services import llm_providers as _lp

KOK = Path(__file__).resolve().parents[2]
INTRO = (KOK / "frontend" / "js" / "intro-sequences.js").read_text(encoding="utf-8")
BLOK = INTRO[INTRO.index("// ════════ ANAHTAR · BAĞLANTI"):INTRO.index("// ════════ SAĞLIK")]
INDEX = (KOK / "frontend" / "index.html").read_text(encoding="utf-8")


class _SahteIstek:
    class _C:
        host = "127.0.0.1"
    client = _C()
    headers: dict = {}
    scope: dict = {"type": "http"}


@pytest.fixture(autouse=True)
def _temiz(monkeypatch):
    monkeypatch.setattr(_lp, "_anahtarlar", {}, raising=False)
    monkeypatch.setattr(_llm, "_runtime_provider", "openrouter", raising=False)
    monkeypatch.setattr(_llm, "_runtime_model", "google/gemma-4-26b-a4b-it:free", raising=False)
    yazilan: list = []
    monkeypatch.setattr(api, "_persist_env", lambda k, v: yazilan.append((k, v)))
    yield yazilan


async def _sec(provider, model=None):
    return await api.set_secim.__wrapped__(_SahteIstek(), api.SecimBody(provider=provider, model=model))


@pytest.mark.asyncio
async def test_anahtarsiz_servise_gecilmez_ve_denenmez(monkeypatch, _temiz):
    monkeypatch.setattr(api, "_anahtari_dene", lambda *a: (_ for _ in ()).throw(AssertionError("denenmemeli")))
    d = await _sec("google")
    assert d["ok"] is False and d["hata_tipi"] == "anahtar_yok"
    assert _temiz == []


@pytest.mark.asyncio
async def test_denenemeyen_secim_hicbir_sey_yazmaz(monkeypatch, _temiz):
    _lp.anahtar_ayarla("openrouter", "sk-or-v1-kayitli")

    async def _patla(sag, key, model):
        raise RuntimeError("404 No endpoints found")
    monkeypatch.setattr(api, "_anahtari_dene", _patla)
    d = await _sec("openrouter", "yok/boyle-bir-model")
    assert d["ok"] is False and d["hata_tipi"] == "test"
    assert _temiz == []
    assert _llm.get_runtime_config()["model"] == "google/gemma-4-26b-a4b-it:free"


@pytest.mark.asyncio
async def test_model_degisikligi_KALICI_yazilir(monkeypatch, _temiz):
    _lp.anahtar_ayarla("openrouter", "sk-or-v1-kayitli")
    denenen = []

    async def _gecti(sag, key, model):
        denenen.append((sag.kimlik, key, model))
    monkeypatch.setattr(api, "_anahtari_dene", _gecti)
    d = await _sec("openrouter", "openai/gpt-4.1-mini")
    assert d["ok"] is True
    assert denenen == [("openrouter", "sk-or-v1-kayitli", "openai/gpt-4.1-mini")], "kayıtlı anahtarla denenmeli"
    assert ("LLM_MODEL", "openai/gpt-4.1-mini") in _temiz and ("LLM_PROVIDER", "openrouter") in _temiz
    assert _llm.get_runtime_config()["model"] == "openai/gpt-4.1-mini"


@pytest.mark.asyncio
async def test_kayitli_anahtarli_servise_gecis_eski_modeli_tasimaz(monkeypatch, _temiz):
    _lp.anahtar_ayarla("google", "AIzaKayitli")

    async def _gecti(sag, key, model):
        return None
    monkeypatch.setattr(api, "_anahtari_dene", _gecti)
    d = await _sec("google")
    assert d["ok"] is True and d["provider"] == "google"
    assert d["model"] == _lp.kayit("google").varsayilan_model and ":free" not in d["model"]


@pytest.mark.asyncio
async def test_yerel_servis_sec_ucundan_gitmez(_temiz):
    d = await _sec("ollama")
    assert d["ok"] is False and d["hata_tipi"] == "yerel"


def test_panel_model_degisikligini_kalici_uca_yollar():
    assert "'/api/llm/sec'" in BLOK
    assert "/api/llm/config" not in BLOK, "model /config'e giderse yeniden başlatınca geri döner"


def test_panel_her_acilista_tazelenir():
    assert "if(name==='key'){ keyInit(); }" in INTRO and "_loaded.key=true" not in INTRO


def test_sabit_model_listesi_ve_diyalog_yok():
    panel = INDEX[INDEX.index('id="hq-panel-key"'):INDEX.index("SÜRÜM PANELİ")]
    assert "<option" not in panel, "sabit yedek model listesi geri gelmiş (08-01 dersi)"
    assert "onclick=" not in panel
    kod = re.sub(r"/\*.*?\*/", "", BLOK, flags=re.S)
    assert "confirm(" not in kod and "alert(" not in kod and "prompt(" not in kod


def test_kaydetme_cift_tiki_engeller():
    m = re.search(r"async function _anGonder\(yol, govde\)\{(.*?)\n  \}", BLOK, re.S)
    assert m and m.group(1).index("if(_anMesgul) return;") < m.group(1).index("af(yol")


@pytest.mark.asyncio
async def test_ilk_kurulumda_red_mesaji_korunan_anahtardan_bahsetmez(monkeypatch, _temiz):
    """Ekranda "henüz bağlı değil" yazarken "mevcut anahtarın korundu" demek kendini yalanlıyordu."""
    async def _patla(sag, key, model):
        raise RuntimeError("401")
    monkeypatch.setattr(api, "_anahtari_dene", _patla)
    ilk = await api.set_api_key.__wrapped__(_SahteIstek(), api.ApiKeyBody(key="sk-or-v1-yanlis", provider="openrouter"))
    assert ilk["ok"] is False and ilk["error"] == api.M("llm.anahtar-reddedildi-ilk", ad="OpenRouter", sebep="401")
    _lp.anahtar_ayarla("openrouter", "sk-or-v1-calisan")
    var = await api.set_api_key.__wrapped__(_SahteIstek(), api.ApiKeyBody(key="sk-or-v1-yanlis", provider="openrouter"))
    assert var["error"] == api.M("llm.anahtar-reddedildi", ad="OpenRouter", sebep="401")

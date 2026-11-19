"""Yerel sağlayıcı (Ollama) — Lite dâhil her kademede açık (2026-08-08).

**Neden bu dosya var.** Threads'te iki ayrı okuyucu vitrindeki *"makinende
kalıyor"* cümlesini *"dil modeli de yerelde çalışıyor"* diye anladı. Gerçekte
Yuki varsayılan olarak BYOK ile buluta gidiyor; yerelde kalan şey veri/hafıza.
Geliştiricinin kararı (2026-07-30) iki parçalıydı: metni düzelt **ve** gerçekten
yerelde koşturmak isteyene ücretli kademe gösterme — Ollama bedava (Lite)
sürümde de sunulsun.

⚠️ Ölçülen gerçek: **Ollama'nın ürün kodunda hiçbir zaman bir kademe kapısı
olmadı.** `FEATURE_MIN_TIER`de girdisi yok, `STEP_TOOLS`ta yok, uçlarda
`feature_allowed` çağrısı yok. Yani "kapıyı açmak" diye bir iş çıkmadı; çıkan iş
**erişilebilir kılmak**tı (BYOK sihirbazında hiç görünmüyordu) ve bu dosyanın
asıl görevi kapının **ileride sessizce eklenmesini** engellemek.

Bu testler ağa ÇIKMAZ — yerel uçlar sahte istemciyle karşılanır.
"""

import pytest

from app.api import llm_config_api as api
from app.services import llm as _llm
from app.services import llm_providers as _lp


class _SahteIstek:
    """slowapi `limiter` bir Request bekler; testte sahtesi yeterli."""
    class _C:
        host = "127.0.0.1"
    client = _C()
    headers: dict = {}
    scope: dict = {"type": "http"}


@pytest.fixture(autouse=True)
def _temiz(monkeypatch):
    """Her test kendi durumuyla başlasın **ve bıraktığını temizlesin**.

    🔴 2026-08-08'de bu dosya `test_llm_models.py`yi kirletiyordu (6 test
    kırmızı). Sebep: `set_llm_config`/`set_yerel` uçları GERÇEK
    `llm.set_runtime_config()`'i çağırıyor — bu bir modül global'ini kalıcı
    değiştirir ve `monkeypatch` onu geri almaz (monkeypatch yalnız kendi
    yaptığı atamaları geri alır). Aktif sağlayıcı "ollama"da kalınca
    `list_models` sonraki dosyada yerel dala giriyordu.

    ⚠️ Tam suite bunu GİZLEDİ: alfabetik sırada `test_llm_models` bu dosyadan
    ÖNCE koşuyor, yani 373/4 yeşili şans eseriydi. Kirlilik ancak dosyalar tek
    tek / ikili koşulunca görünür. Bu yüzden temizlik fixture'a yazıldı, testin
    içine değil — unutulabilecek bir adım olmasın.
    """
    from app.api import llm_config_api as _api

    monkeypatch.setattr(_lp, "_anahtarlar", {}, raising=False)
    onceki = (_llm._runtime_provider, _llm._runtime_model, _llm._model_explicitly_set)
    yield
    _llm._runtime_provider, _llm._runtime_model, _llm._model_explicitly_set = onceki
    _llm._client = None          # damga değiştiği için istemci de tazelensin
    _llm._last_damga = None
    _api._models_cache.update({"at": 0.0, "groups": None})
    _api._saglayici_cache.clear()


# ── ① Yerel sağlayıcı seçilebilir ─────────────────────────────────────────

def test_yerel_saglayici_secilebilir():
    """Yerel sağlayıcı listede ve seçilebilir (kademe yok)."""
    assert _lp.yerel_mi("ollama") is True
    assert "ollama" in [s.kimlik for s in _lp.tumu()]


def test_yerel_kayit_bulut_listesini_kirletmez():
    """`hepsi()` bulut kalır; `ENV_ADLARI`ya `OLLAMA_MODEL` sızmaz.

    Sızsaydı `_env_yukle` model adını bir API anahtarı sanıp depoya yazardı ve
    "anahtarı var mı" sorusu her kurulumda True dönerdi.
    """
    bulut = [s.kimlik for s in _lp.hepsi()]
    assert "ollama" not in bulut
    assert "OLLAMA_MODEL" not in _lp.ENV_ADLARI
    assert _lp.anahtar("ollama") == ""
    assert _lp.anahtarli_kimlikler() == []
    # ama kayıt çözülebiliyor ve listede
    assert _lp.kayit("ollama") is not None
    assert len(_lp.tumu()) == len(_lp.hepsi()) + len(_lp.yereller())


def test_yerel_kok_sonek_olarak_kesilir():
    """`rstrip('/v1')` tuzağı: karakter kümesi siler, sonek değil."""
    class _S:
        base_url = "http://127.0.0.1:11434/v1"
    assert api._yerel_kok(_S()) == "http://127.0.0.1:11434"

    class _S2:
        base_url = "http://sunucu/ollama/v1/"
    # naif rstrip("/v1") burada "ollama"nın sonundaki harfleri de yerdi
    assert api._yerel_kok(_S2()) == "http://sunucu/ollama"


# ── ③ Anahtar akışı: yerelde anahtar İSTENMEZ ────────────────────────────

@pytest.mark.asyncio
async def test_key_ucu_yerelde_anahtari_reddeder():
    d = await api.set_api_key.__wrapped__(_SahteIstek(), api.ApiKeyBody(key="sk-bir-sey", provider="ollama"))
    assert d["ok"] is False
    assert d["hata_tipi"] == "yerel"
    assert "anahtar istemez" in d["error"]


@pytest.mark.asyncio
async def test_config_ucu_yerelde_anahtar_aramaz():
    """`POST /api/llm/config` yerelde anahtar yokluğundan şikâyet etmemeli."""
    d = await api.set_llm_config.__wrapped__(
        _SahteIstek(), api.ProviderConfig(provider="ollama", model="llama3.1")
    )
    assert d["ok"] is True
    assert d["provider"] == "ollama"


@pytest.mark.asyncio
async def test_key_status_yerelde_anahtar_eksik_demez(monkeypatch):
    monkeypatch.setattr(_llm, "_runtime_provider", "ollama", raising=False)
    monkeypatch.setattr(_llm, "_runtime_model", "llama3.1", raising=False)
    d = await api.get_key_status.__wrapped__(_SahteIstek())
    assert d["provider"] == "ollama"
    assert d["yerel"] is True
    assert d["anahtar_gerekir"] is False


# ── ④ Model listesi: yerelde KURULU modeller ─────────────────────────────

class _SahteYanit:
    def __init__(self, govde):
        self._govde = govde

    def raise_for_status(self):
        return None

    def json(self):
        return self._govde


def _sahte_httpx(monkeypatch, govde):
    """`httpx.AsyncClient` yerine yereli taklit eden istemci koy."""
    import httpx

    class _Istemci:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            assert "127.0.0.1" in url or "localhost" in url, url
            assert url.endswith("/api/tags")
            return _SahteYanit(govde)

    monkeypatch.setattr(httpx, "AsyncClient", _Istemci)


@pytest.mark.asyncio
async def test_yerel_model_listesi_kurulu_modelleri_verir(monkeypatch):
    _sahte_httpx(monkeypatch, {"models": [
        {"name": "llama3.1:latest", "size": 4_920_000_000},
        {"name": "nomic-embed-text:latest", "size": 274_000_000},
        {"name": "bge-m3:latest", "size": 1_200_000_000},
    ]})
    d = await api.list_models.__wrapped__(_SahteIstek(), provider="ollama")
    assert d["ok"] and d["provider"] == "ollama" and d["yerel"] is True
    kimlikler = [o["id"] for g in d["groups"] for o in g["options"]]
    assert kimlikler == ["llama3.1:latest"]          # gömme modelleri elenir
    assert "4.9 GB" in d["groups"][0]["options"][0]["label"]
    assert d["cached"] is False                       # yerel liste önbelleklenmez


@pytest.mark.asyncio
async def test_yerel_listede_openrouter_e_dusmez(monkeypatch):
    """Ollama seçiliyken panel sessizce OpenRouter listesini göstermemeli.

    2026-08-08 öncesi kodda `if kimlik == "ollama": kimlik = VARSAYILAN` vardı —
    kullanıcı yerel modeli seçtiğini sanırken bulut modeli seçiyordu.
    """
    import httpx

    class _Patlar:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            raise ConnectionError("All connection attempts failed")

    monkeypatch.setattr(httpx, "AsyncClient", _Patlar)
    d = await api.list_models.__wrapped__(_SahteIstek(), provider="ollama")
    assert d["provider"] == "ollama"
    assert d["source"] == "fallback"
    kimlikler = [o["id"] for g in d["groups"] for o in g["options"]]
    assert all(":free" not in k and "/" not in k for k in kimlikler), kimlikler
    # Hata metni TÜRKÇE ve eylem içermeli — ham httpx metni panele düşmemeli
    # (2026-08-08'de tarayıcıda "All connection attempts failed" görüldü).
    assert "ulaşılamadı" in d["error"] and "ollama.com/download" in d["error"]
    assert not d["error"].startswith("All connection")


@pytest.mark.asyncio
async def test_model_kurulu_degilse_kaydetmez(monkeypatch):
    """"Kaydetmeden önce dene" kuralı yerelde de geçerli."""
    _sahte_httpx(monkeypatch, {"models": [{"name": "llama3.1:latest"}]})
    onceki = _llm.get_runtime_config()
    d = await api.set_yerel.__wrapped__(_SahteIstek(), api.YerelBody(model="yok-boyle-model"))
    assert d["ok"] is False
    assert d["hata_tipi"] == "model_yok"
    assert "ollama pull yok-boyle-model" in d["error"]
    assert _llm.get_runtime_config()["model"] == onceki["model"]   # dokunulmadı


@pytest.mark.asyncio
async def test_ollama_kapaliysa_anlasilir_hata(monkeypatch):
    import httpx

    class _Patlar:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            raise RuntimeError("Connection refused")

    monkeypatch.setattr(httpx, "AsyncClient", _Patlar)
    d = await api.set_yerel.__wrapped__(_SahteIstek(), api.YerelBody(model="llama3.1"))
    assert d["ok"] is False
    assert d["hata_tipi"] == "baglanti"
    assert "ollama.com/download" in d["error"]


# ── ⑤ Model yönlendirme: FAST/STRONG yalnız OpenRouter'da ────────────────

def test_fast_strong_yalniz_openrouter_da_uygulanir(monkeypatch):
    """🔴 Ölçülerek bulunan kusur (2026-08-08).

    `LLM_MODEL_FAST` varsayılanı `openai/gpt-4o-mini` — bir **OpenRouter** ID'si.
    Kullanıcı başka sağlayıcı seçip uygulamayı yeniden başlattığında
    `_kullanici_model_secti()` False'a düşüyor (BYOK paneli seçilen modeli
    `.env`'e de yazdığı için `_runtime_model == LLM_MODEL` oluyor) ve yönlendirme
    o ID'yi gönderiyordu → sağlayıcı 404. Sohbet ilk mesajda ölürdü.
    """
    monkeypatch.setattr(_llm, "_model_explicitly_set", False, raising=False)

    # OpenRouter: ESKİ davranış birebir korunur (kısa mesaj → FAST).
    # ⚠️ Ücretli bir varsayılan seçiliyor: aktif model `:free` olsaydı
    # "ücretsizden ücretliye kaydırma" koruması zaten devreye girer ve bu dal
    # hiç ölçülmemiş olurdu.
    monkeypatch.setattr(_llm, "LLM_MODEL", "openai/gpt-4.1", raising=False)
    monkeypatch.setattr(_llm, "_runtime_model", "openai/gpt-4.1", raising=False)
    monkeypatch.setattr(_llm, "_runtime_provider", "openrouter", raising=False)
    assert _llm._route_model("selam") == _llm.LLM_MODEL_FAST
    assert _llm._background_model(_llm.LLM_MODEL_FAST) == _llm.LLM_MODEL_FAST

    # Yerel: aktif model olduğu gibi kalır (restart sonrası hâli taklit ediliyor —
    # `.env`'e yazıldığı için LLM_MODEL de aynı, yani "seçim" sinyali kayıp)
    monkeypatch.setattr(_llm, "LLM_MODEL", "llama3.1", raising=False)
    monkeypatch.setattr(_llm, "_runtime_model", "llama3.1", raising=False)
    monkeypatch.setattr(_llm, "_runtime_provider", "ollama", raising=False)
    assert _llm._route_model("selam") == "llama3.1"
    assert _llm._route_model("uzun ve karmaşık bir istek " * 10) == "llama3.1"
    assert _llm._background_model(_llm.LLM_MODEL_FAST) == "llama3.1"

    # Başka bir bulut sağlayıcısı da aynı korumayı alır
    monkeypatch.setattr(_llm, "LLM_MODEL", "gemini-2.5-flash", raising=False)
    monkeypatch.setattr(_llm, "_runtime_model", "gemini-2.5-flash", raising=False)
    monkeypatch.setattr(_llm, "_runtime_provider", "google", raising=False)
    assert _llm._route_model("selam") == "gemini-2.5-flash"


# ── ⑥ İstek zaman aşımı sağlayıcıya duyarlı ──────────────────────────────

def test_yerel_istege_bulut_zaman_asimi_dayatilmaz():
    """🔴 Canlı ölçümle bulunan kusur (2026-08-08).

    `runner.py`de zaman aşımı üç yerde de sabit `30.0`du. Yerel modelde yalnız
    prompt işleme 14–17 sn sürüyor (4.100 token, ~60-70 tok/s); üretimle birlikte
    30 sn aşılıyordu. Ölçüm: **4 turun 4'ünde de** ilk istek 30,03 sn'de düştü
    (`| 500 | 30.02s`), SDK sessizce yeniden denedi → her mesaj ~30 sn fazladan
    sürdü. Düzeltmeden sonra aynı üç turda 500 sayısı **0**.
    """
    from app.services import runner as _runner

    class _Bulut:
        base_url = "https://openrouter.ai/api/v1"

    class _Yerel:
        base_url = "http://127.0.0.1:11434/v1"

    assert _runner._llm_zaman_asimi(_Bulut()) == _runner.LLM_TIMEOUT == 30.0
    assert _runner._llm_zaman_asimi(_Yerel()) == _runner.LLM_TIMEOUT_YEREL
    assert _runner.LLM_TIMEOUT_YEREL > _runner.LLM_TIMEOUT

    # Sabit 30.0 geri sızmasın — üç çağrı yerinin hepsi helper'dan geçmeli
    import inspect
    kaynak = inspect.getsource(_runner)
    assert "timeout=30.0" not in kaynak


# ── ⑦ Sağlık paneli yerelde yanlış KRİTİK üretmez ────────────────────────

def test_saglik_yerelde_anahtar_istemez(monkeypatch):
    from app.services import self_check
    monkeypatch.setattr(_llm, "_runtime_provider", "ollama", raising=False)
    d = self_check._denetle_llm_anahtar()
    assert d["ok"] is True
    assert d["seviye"] != "kritik"
    assert "gerekmiyor" in d["detay"]

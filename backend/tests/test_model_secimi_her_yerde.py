"""Kullanıcının seçtiği model HER yolda geçerli mi?

🔴 2026-08-01 dersi: BYOK panelinden ücretsiz model seçen müşteride sohbet çalışıyordu
ama arka plan işleri (özet · olgu çıkarımı · ekip çağrısı) ve hatta ana sohbetin ARAÇ
ADIMLARI config varsayılanı `LLM_MODEL_FAST`/`LLM_MODEL_STRONG`/`LLM_MODEL`'e gidiyordu —
üçü de ÜCRETLİ. Kredisiz anahtarda bunlar sessizce ölüyor; geliştiricinin anahtarında
kredi olduğu için hiç görünmüyordu.

Buradaki testler "kullanıcı model seçti" durumunu kurup her yolun ona uyduğunu ölçer.
"""

import pytest

from app.services import llm as llm_mod

SECILEN = "google/gemma-4-26b-a4b-it:free"


UCRETLI = "openai/gpt-4.1-mini"


@pytest.fixture
def kullanici_model_secti(monkeypatch):
    """BYOK panelinden model seçilmiş durumu kur."""
    monkeypatch.setattr(llm_mod, "_runtime_model", SECILEN)
    monkeypatch.setattr(llm_mod, "_model_explicitly_set", True)
    return SECILEN


@pytest.fixture
def kullanici_secim_yapmadi(monkeypatch):
    """Hiç seçim yapılmamış + config varsayılanı ÜCRETLİ (klasik kurulum)."""
    monkeypatch.setattr(llm_mod, "LLM_MODEL", UCRETLI)
    monkeypatch.setattr(llm_mod, "_runtime_model", UCRETLI)
    monkeypatch.setattr(llm_mod, "_model_explicitly_set", False)


def test_secilen_model_arka_plani_ele_gecirir(kullanici_model_secti):
    assert llm_mod._background_model("openai/gpt-4o-mini") == SECILEN
    assert llm_mod._background_model("openai/gpt-4.1-mini") == SECILEN


def test_secim_yoksa_config_tercihi_korunur(kullanici_secim_yapmadi):
    """Hız/güç ayrımı seçim yapılmadığında kaybolmamalı."""
    assert llm_mod._background_model("openai/gpt-4o-mini") == "openai/gpt-4o-mini"
    assert llm_mod._background_model("") == UCRETLI


def test_restart_sonrasi_secim_sinyali_kaybolmuyor(monkeypatch):
    """🔴 Asıl tuzak: BYOK paneli seçilen modeli `.env`'e de yazar.

    Restart'ta `LLM_MODEL` ile `_runtime_model` eşitlenir; eski kod bunu
    "kullanıcı seçim yapmamış" sanıp ÜCRETLİ varsayılana dönüyordu.
    """
    monkeypatch.setattr(llm_mod, "LLM_MODEL", SECILEN)       # .env'e yazılmış hali
    monkeypatch.setattr(llm_mod, "_runtime_model", SECILEN)
    monkeypatch.setattr(llm_mod, "_model_explicitly_set", False)  # taze süreç

    assert llm_mod._background_model("openai/gpt-4o-mini") == SECILEN
    assert llm_mod._route_model("merhaba") == SECILEN         # kısa mesaj → FAST'e kaçmamalı


def test_set_runtime_config_secim_bayragini_kaldirir(monkeypatch):
    monkeypatch.setattr(llm_mod, "_model_explicitly_set", False)
    monkeypatch.setattr(llm_mod, "_runtime_model", llm_mod.LLM_MODEL)
    llm_mod.set_runtime_config("openrouter", SECILEN)
    try:
        assert llm_mod._kullanici_model_secti() is True
        assert llm_mod._background_model("openai/gpt-4o-mini") == SECILEN
    finally:
        llm_mod._model_explicitly_set = False
        llm_mod._runtime_model = llm_mod.LLM_MODEL


def test_ozetleme_ve_olgu_cikarimi_ucretli_modele_sabitlenmemis():
    """Kaynak seviyesinde: iki arka plan çağrısı da `_background_model`'den geçmeli."""
    import inspect

    kaynak = inspect.getsource(llm_mod)
    ozet = kaynak.split("def _maybe_summarize")[1][:2000] if "_maybe_summarize" in kaynak else ""
    assert "_background_model(" in kaynak

    # Doğrudan `model=LLM_MODEL_FAST` / `model=strong` kalıntısı olmamalı
    assert "model=LLM_MODEL_FAST," not in kaynak
    assert "strong = LLM_MODEL_STRONG or LLM_MODEL\n    try:" not in kaynak


def test_orchestrator_uc_yolun_ucu_de_gecer():
    import inspect
    from app.services import orchestrator

    kaynak = inspect.getsource(orchestrator)
    assert kaynak.count("_background_model(") == 3, "ekip/uzman/sentez üçü de geçmeli"
    assert "model = LLM_MODEL_FAST or LLM_MODEL" not in kaynak
    assert "model = LLM_MODEL_STRONG or LLM_MODEL" not in kaynak


@pytest.mark.asyncio
async def test_runner_arac_adimlari_secilen_modeli_kullanir(kullanici_model_secti, mocker):
    """Ana sohbetin ARAÇ adımı, router'ın config modelini değil kullanıcınınkini kullanmalı.

    Eski davranış: aynı turda araç adımı gpt-4.1-mini'ye, final yanıt kullanıcının
    modeline gidiyordu — tek sohbet, iki model.
    """
    from app.services.runner import LLMRunner

    kullanilan = {}

    class _Stream:
        def __aiter__(self):
            async def gen():
                return
                yield
            return gen()

        async def close(self):
            return None

    class _Completions:
        async def create(self, **kw):
            kullanilan["model"] = kw["model"]
            return _Stream()

    class _Chat:
        completions = _Completions()

    class _Client:
        base_url = "https://openrouter.ai/api/v1"
        chat = _Chat()

    class _Router:
        async def get_client(self):
            # Router config varsayılanını döner — ÜCRETLİ model
            return _Client(), "openai/gpt-4.1-mini"

        def record_failure(self, *a):
            return None

        def record_success(self, *a):
            return None

    mocker.patch("app.services.llm_router.get_router", return_value=_Router())

    runner = LLMRunner(_Client(), SECILEN, tools=[], max_steps=1)
    async for _ in runner.run([{"role": "user", "content": "merhaba"}]):
        pass

    assert kullanilan.get("model") == SECILEN, (
        f"araç adımı {kullanilan.get('model')} kullandı, kullanıcı {SECILEN} seçmişti"
    )


@pytest.mark.asyncio
async def test_runner_yerel_saglayiciya_dusunce_onun_modelini_kullanir(kullanici_model_secti, mocker):
    """Router ollama'ya düştüyse OpenRouter model adı gönderilmemeli (fallback korunur)."""
    from app.services.runner import LLMRunner

    kullanilan = {}

    class _Stream:
        def __aiter__(self):
            async def gen():
                return
                yield
            return gen()

        async def close(self):
            return None

    class _Completions:
        async def create(self, **kw):
            kullanilan["model"] = kw["model"]
            return _Stream()

    class _Chat:
        completions = _Completions()

    class _LocalClient:
        base_url = "http://127.0.0.1:11434/v1"
        chat = _Chat()

    class _Router:
        async def get_client(self):
            return _LocalClient(), "llama3.1"

        def record_failure(self, *a):
            return None

        def record_success(self, *a):
            return None

    mocker.patch("app.services.llm_router.get_router", return_value=_Router())

    runner = LLMRunner(_LocalClient(), SECILEN, tools=[], max_steps=1)
    async for _ in runner.run([{"role": "user", "content": "merhaba"}]):
        pass

    assert kullanilan.get("model") == "llama3.1"


def test_olgu_cikarim_hatasi_artik_normal_diye_gizlenmiyor():
    import inspect

    kaynak = inspect.getsource(llm_mod)
    assert 'logger.debug("Fact çıkarım hatası (normal)' not in kaynak
    assert "Fact çıkarımı başarısız" in kaynak

"""Çok sağlayıcılı BYOK + ücretsiz kota bildirimi (2026-08-05).

İki iş bir arada test ediliyor çünkü aynı kök nedene bakıyorlar: **ürün, LLM
tarafındaki kısıtları kullanıcıya söylemiyordu.**

① Ücretsiz kota. OpenRouter'da kredisiz hesap `:free` modelleri günde 50 istek
   kullanabilir (doküman, 2026-08-05). Ürün bu rakamı hiçbir yerde yazmıyordu;
   kota dolunca gelen 429'a *"biraz bekleyip tekrar dene"* diyordu — beklemekle
   geçmediği için bu **yanlış tavsiye**. Müşteri bunu "Yuki bozuldu" diye okur.

② Tek sağlayıcı. Elinde OpenAI/Google/Anthropic anahtarı olan müşteri ürünü
   kullanamıyor, OpenRouter'a ayrıca kaydolmak zorunda kalıyordu.

Bu testler ağa ÇIKMAZ.
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
def _temiz_anahtarlar(monkeypatch):
    """Her test kendi anahtar deposuyla başlasın — testler birbirini kirletmesin."""
    monkeypatch.setattr(_lp, "_anahtarlar", {}, raising=False)
    yield


# ── Kayıt tutarlılığı ────────────────────────────────────────────────

def test_kimlik_ve_env_tekil():
    kimlikler = [s.kimlik for s in _lp.hepsi()]
    envler = [s.env for s in _lp.hepsi()]
    assert len(kimlikler) == len(set(kimlikler))
    assert len(envler) == len(set(envler))


def test_her_saglayicinin_zorunlu_alanlari_dolu():
    for s in _lp.hepsi():
        assert s.base_url.startswith("https://"), s.kimlik
        assert s.anahtar_url.startswith("https://"), s.kimlik
        assert s.varsayilan_model, s.kimlik
        assert s.sdk in ("openai", "anthropic"), s.kimlik


def test_yalniz_olculen_saglayici_dogrulandi_sayilir():
    """`dogrulandi=True` gerçek anahtarla uçtan uca denenmiş olana yazılır.

    2026-08-01'de ölçülmemiş üç model ID'si listede durduğu için ürün yeni
    müşteride sessizce ölmüştü. Aynı hatayı sağlayıcı ölçeğinde tekrarlamamak
    için bu alan gevşetilemez: bugün yalnız OpenRouter denenmiştir.
    """
    dogrulanan = {s.kimlik for s in _lp.hepsi() if s.dogrulandi}
    assert dogrulanan == {"openrouter"}


def test_bicim_denetimi_yalniz_on_ek_taniminda_calisir():
    google = _lp.kayit("google")
    assert not _lp.bicim_uygun(google, "sk-or-v1-yanlis")   # Google anahtarı AIza… ile başlar
    assert _lp.bicim_uygun(google, "AIzaSyOrnekAnahtar")
    # Ön eki tanımlı OLMAYAN sağlayıcıda uydurma kalıp dayatılmaz
    together = _lp.kayit("together")
    assert together.on_ek == ()
    assert _lp.bicim_uygun(together, "her-turlu-deger")


# ── Anahtar deposu: biri öbürünü silmez ──────────────────────────────

def test_saglayici_anahtarlari_birbirini_ezmiyor():
    _lp.anahtar_ayarla("openrouter", "sk-or-v1-aaa")
    _lp.anahtar_ayarla("google", "AIzaBBB")
    assert _lp.anahtar("openrouter") == "sk-or-v1-aaa"
    assert _lp.anahtar("google") == "AIzaBBB"
    assert set(_lp.anahtarli_kimlikler()) == {"openrouter", "google"}


# ── Uç davranışı ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bilinmeyen_saglayici_reddediliyor():
    sonuc = await api.set_api_key.__wrapped__(
        _SahteIstek(), api.ApiKeyBody(key="abc", provider="yok-boyle-bir-firma")
    )
    assert sonuc["ok"] is False and sonuc["hata_tipi"] == "saglayici"


@pytest.mark.asyncio
async def test_yanlis_on_ek_saglayiciya_gore_reddediliyor(monkeypatch):
    """OpenRouter anahtarını Google kutusuna yapıştırmak ağa hiç çıkmadan durur."""
    denendi = []
    monkeypatch.setattr(api, "_anahtari_dene",
                        lambda *a: denendi.append(a))   # çağrılırsa test düşer
    yazilan = []
    monkeypatch.setattr(api, "_persist_env", lambda k, v: yazilan.append((k, v)))

    sonuc = await api.set_api_key.__wrapped__(
        _SahteIstek(), api.ApiKeyBody(key="sk-or-v1-openrouter-anahtari", provider="google")
    )
    assert sonuc["ok"] is False and sonuc["hata_tipi"] == "bicim"
    assert "AIza" in sonuc["error"]
    assert denendi == [] and yazilan == []      # ne test edildi ne yazıldı


@pytest.mark.asyncio
async def test_basarisiz_test_mevcut_anahtari_korur(monkeypatch):
    """2026-08-02 saha raporunun kuralı sağlayıcı başına da geçerli."""
    _lp.anahtar_ayarla("openai", "sk-calisan-eski-anahtar")
    yazilan = []
    monkeypatch.setattr(api, "_persist_env", lambda k, v: yazilan.append((k, v)))

    async def _patla(sag, key, model):
        raise RuntimeError("401 invalid api key")
    monkeypatch.setattr(api, "_anahtari_dene", _patla)

    sonuc = await api.set_api_key.__wrapped__(
        _SahteIstek(), api.ApiKeyBody(key="sk-yeni-bozuk-anahtar", provider="openai")
    )
    assert sonuc["ok"] is False and sonuc["hata_tipi"] == "test"
    assert yazilan == []
    assert _lp.anahtar("openai") == "sk-calisan-eski-anahtar"   # ezilmedi


@pytest.mark.asyncio
async def test_google_anahtari_dogru_env_degiskenine_yaziliyor(monkeypatch):
    _lp.anahtar_ayarla("openrouter", "sk-or-v1-eskiden-girilmis")
    yazilan = []
    monkeypatch.setattr(api, "_persist_env", lambda k, v: yazilan.append((k, v)))

    async def _gecti(sag, key, model):
        return None
    monkeypatch.setattr(api, "_anahtari_dene", _gecti)

    sonuc = await api.set_api_key.__wrapped__(
        _SahteIstek(), api.ApiKeyBody(key="AIzaSyOrnekGoogleAnahtari", provider="google")
    )
    assert sonuc["ok"] is True and sonuc["provider"] == "google"
    assert ("GOOGLE_API_KEY", "AIzaSyOrnekGoogleAnahtari") in yazilan
    assert ("LLM_PROVIDER", "google") in yazilan
    # Model verilmedi → sağlayıcının varsayılanı; OpenRouter model ID'si TAŞINMAZ
    assert sonuc["model"] == _lp.kayit("google").varsayilan_model
    assert ":free" not in sonuc["model"]
    # Eski OpenRouter anahtarı yerinde
    assert _lp.anahtar("openrouter") == "sk-or-v1-eskiden-girilmis"


@pytest.mark.asyncio
async def test_provider_verilmezse_openrouter_varsayilir(monkeypatch):
    """Eski istemciler `provider` göndermiyor — davranış aynı kalmalı."""
    yazilan = []
    monkeypatch.setattr(api, "_persist_env", lambda k, v: yazilan.append((k, v)))

    async def _gecti(sag, key, model):
        assert sag.kimlik == "openrouter"
    monkeypatch.setattr(api, "_anahtari_dene", _gecti)

    sonuc = await api.set_api_key.__wrapped__(
        _SahteIstek(), api.ApiKeyBody(key="sk-or-v1-gercek-gibi")
    )
    assert sonuc["ok"] is True and sonuc["provider"] == "openrouter"
    assert ("OPENROUTER_API_KEY", "sk-or-v1-gercek-gibi") in yazilan


@pytest.mark.asyncio
async def test_saglayici_listesi_ucretsiz_notunu_tasiyor():
    d = await api.list_providers.__wrapped__(_SahteIstek())
    assert d["ok"] is True
    orouter = [s for s in d["saglayicilar"] if s["kimlik"] == "openrouter"][0]
    assert "50" in orouter["ucretsiz"]          # günlük istek sınırı yazılı
    assert orouter["dogrulandi"] is True


# ── Kota mesajı: GÜNLÜK mü DAKİKALIK mı ──────────────────────────────

class _SahteHata(Exception):
    def __init__(self, mesaj):
        super().__init__(mesaj)
        self.body = {"error": {"message": mesaj}}


def test_gunluk_kota_beklemekle_gecmez_diyor(monkeypatch):
    monkeypatch.setattr(_llm, "_runtime_model", "google/gemma-4-26b-a4b-it:free")
    m = _llm._kota_mesaji(
        _SahteHata("Rate limit exceeded: free-models-per-day"), _lp.kayit("openrouter")
    )
    assert "ertesi gün" in m
    assert "50" in m and "1.000" in m
    # 🔴 Eski metnin yanlış tavsiyesi geri gelmesin
    assert "biraz bekleyip" not in m


def test_dakikalik_sinir_beklemeyi_oneriyor(monkeypatch):
    monkeypatch.setattr(_llm, "_runtime_model", "google/gemma-4-26b-a4b-it:free")
    m = _llm._kota_mesaji(_SahteHata("Rate limit exceeded"), _lp.kayit("openrouter"))
    assert "birkaç saniye" in m
    assert "ertesi gün" not in m


# ── İstemci kurulumu: sağlayıcı/anahtar değişimi yakalanıyor mu ──────

def test_istemci_saglayici_degisince_yeniden_kuruluyor(monkeypatch):
    monkeypatch.setattr(_llm, "_client", None, raising=False)
    monkeypatch.setattr(_llm, "_last_damga", None, raising=False)
    monkeypatch.setattr(_llm, "USE_LOCAL_LLM", False, raising=False)

    _lp.anahtar_ayarla("openrouter", "sk-or-v1-a")
    monkeypatch.setattr(_llm, "_runtime_provider", "openrouter", raising=False)
    c1 = _llm._get_client()
    assert "openrouter.ai" in str(c1.base_url)

    _lp.anahtar_ayarla("groq", "gsk_test")
    monkeypatch.setattr(_llm, "_runtime_provider", "groq", raising=False)
    c2 = _llm._get_client()
    assert "groq.com" in str(c2.base_url)
    assert c1 is not c2


def test_istemci_anahtar_degisince_yeniden_kuruluyor(monkeypatch):
    """🔴 Bu, sahada gizli kalmış bir hatanın testi.

    Anahtar değişimi eskiden yalnız `_last_mode = None` ile işaretleniyordu;
    aynı sağlayıcıda anahtar güncellenince (ör. kotası biten anahtarın yerine
    yenisi) istemcinin yeniden kurulacağının garantisi yoktu.
    """
    monkeypatch.setattr(_llm, "_client", None, raising=False)
    monkeypatch.setattr(_llm, "_last_damga", None, raising=False)
    monkeypatch.setattr(_llm, "USE_LOCAL_LLM", False, raising=False)
    monkeypatch.setattr(_llm, "_runtime_provider", "openrouter", raising=False)

    _lp.anahtar_ayarla("openrouter", "sk-or-v1-eski")
    c1 = _llm._get_client()
    _lp.anahtar_ayarla("openrouter", "sk-or-v1-yeni")
    c2 = _llm._get_client()
    assert c1 is not c2


def test_router_bulut_istemcisi_anahtari_gec_okur(monkeypatch):
    """Sohbetin GERÇEK yolu router'dan geçer — anahtar oraya da ulaşmalı.

    🔴 Eski `OpenRouterProvider.__init__` istemciyi modül import edilirken,
    yani anahtar çoğu zaman BOŞken kuruyordu. BYOK panelinden anahtar girip
    restart etmeden sohbet eden kullanıcı anahtarsız istemciyi kullanıyordu.
    """
    from app.services.llm_router import BulutProvider
    monkeypatch.setattr(_llm, "USE_LOCAL_LLM", False, raising=False)
    monkeypatch.setattr(_llm, "_runtime_provider", "openrouter", raising=False)

    p = BulutProvider()
    _lp.anahtar_ayarla("openrouter", "sk-or-v1-once")
    c1 = p.get_client()
    assert c1.api_key == "sk-or-v1-once"

    _lp.anahtar_ayarla("openrouter", "sk-or-v1-sonra")
    c2 = p.get_client()
    assert c2.api_key == "sk-or-v1-sonra"


# ── Sağlık paneli ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_openrouter_disi_saglayicida_model_denetimi_yanlis_alarm_vermez(monkeypatch):
    """Gemini modelini OpenRouter listesine karşı ölçmek her seferinde
    "model sağlayıcıda yok" derdi — denetleyemediğimiz yerde hüküm vermiyoruz."""
    from app.services import self_check
    monkeypatch.setattr(_llm, "_runtime_provider", "google", raising=False)
    monkeypatch.setattr(_llm, "_runtime_model", "gemini-2.5-flash", raising=False)
    monkeypatch.setattr(_llm, "USE_LOCAL_LLM", False, raising=False)

    async def _patlasin():
        raise AssertionError("OpenRouter listesine hiç gidilmemeliydi")
    monkeypatch.setattr(api, "_fetch_live_groups", _patlasin)

    d = await self_check._denetle_llm_model()
    # Yanlış alarm yok (ok=True, kritik değil) — ama 09-28'den beri "yolunda" da değil:
    # denetlenemeyen yer ÖLÇÜLEMEDİ olarak çizilir. Metin sağlayıcının adını taşır
    # (eskiden ham kimlik "google", şimdi müşteri adı "Google Gemini").
    assert d["ok"] is True and d["seviye"] != "kritik"
    assert d["durum"] == "olculemedi" and "Google" in d["detay"]


def test_saglik_paneli_ucretsiz_kotayi_gosteriyor(monkeypatch):
    from app.services import self_check
    monkeypatch.setattr(_llm, "_runtime_provider", "openrouter", raising=False)
    monkeypatch.setattr(_llm, "_runtime_model", "google/gemma-4-26b-a4b-it:free", raising=False)
    monkeypatch.setattr(_llm, "USE_LOCAL_LLM", False, raising=False)
    d = self_check._denetle_ucretsiz_kota()
    assert d["ok"] is True and "50" in d["detay"]


def test_herhangi_bir_saglayici_anahtari_yeterli(monkeypatch):
    """`has_openrouter_key` adı tarihsel — soru "sohbet edebilir miyiz".

    Google anahtarı girmiş kullanıcıya SAĞLIK panelinde "anahtar girilmemiş"
    demek yanlış kritik olurdu.
    """
    from app.services import self_check
    assert _llm.has_openrouter_key() is False
    _lp.anahtar_ayarla("google", "AIzaX")
    assert _llm.has_openrouter_key() is True
    assert self_check._denetle_llm_anahtar()["ok"] is True


# ── .env.example tuzağı ──────────────────────────────────────────────

def test_env_example_satir_sonu_yorumu_icermiyor():
    """🔴 Ölçüldü (2026-08-05): python-dotenv `KEY=  # açıklama` satırında
    açıklamanın TAMAMINI değer sayıyor. Yeni sağlayıcı anahtarları ilk yazımda
    tam bu biçimdeydi → hepsi "dolu" görünüyor, ürün "anahtar ayarlı" diyor ve
    çöp anahtarla isteğe çıkıyordu. Yorum satır ÜSTÜNDE durur.
    """
    from pathlib import Path
    from dotenv import dotenv_values

    yol = Path(__file__).resolve().parents[2] / ".env.example"
    # ⚠️ `.env.example` bilerek `.gitignore`'da (bkz. .gitignore §.env.example —
    # dosyanın tamamı görülmediği için tedbiren yoksayılmış, kaldırma kararı
    # geliştiricide). Taze klonda dosya YOKTUR; testi kırmızı yakmak yerine atlıyoruz.
    if not yol.exists():
        pytest.skip(".env.example bu çalışma kopyasında yok (gitignore'da)")
    degerler = dotenv_values(yol)
    sizanlar = {k: v for k, v in degerler.items() if v and v.strip().startswith("#")}
    assert not sizanlar, f"satır-sonu yorumu değer olarak sızıyor: {sizanlar}"


def test_env_example_tum_saglayici_degiskenlerini_taniyor():
    """Kayda sağlayıcı eklenip .env.example unutulursa kullanıcı anahtarını
    nereye yazacağını bilemez."""
    from pathlib import Path
    yol = Path(__file__).resolve().parents[2] / ".env.example"
    if not yol.exists():
        pytest.skip(".env.example bu çalışma kopyasında yok (gitignore'da)")
    metin = yol.read_text(encoding="utf-8")
    eksik = [s.env for s in _lp.hepsi() if f"\n{s.env}=" not in metin]
    assert not eksik, f".env.example'da tanımsız: {eksik}"

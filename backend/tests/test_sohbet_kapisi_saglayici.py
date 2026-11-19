"""Sohbet kapısı SEÇİLİ sağlayıcıya bakar — hepsine değil.

🔴 NEDEN VAR: `_llm_key_missing()` 15 sağlayıcının **2'sini** biliyordu
(`OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `USE_LOCAL_LLM`). Sağlayıcı seçimi
2026-08-05'ten beri `LLM_PROVIDER` ile yapılıyor; kapı güncellenmedi.

Ölçüldü 2026-08-28 (geliştiricinin makinesi, `LLM_PROVIDER=ollama`): seçili sağlayıcı
yerel, anahtar istemiyor — kapı yine de "anahtar yok" deyip `/api/chat`i 503'e
düşürüyor ve *"OpenRouter anahtarını gir"* diyordu. Etki yalnız Ollama değildi:
google · openai · groq · cerebras · deepseek · mistral · xai · together ·
fireworks · deepinfra · nebius · chutes — **13 sağlayıcı** kapının arkasında
ölüydü. Satılan bir özellik (çok sağlayıcılı BYOK) hiç çalışmıyordu.

🪤 Sınıf: YANLIŞ TEŞHİS — bu depoda üçüncü kez (ElevenLabs 401=kota,
OpenRouter 429=günlük/dakikalık). Mesaj kullanıcıyı OLMAYAN bir soruna yollar.

Bu dosya kapıyı **her sağlayıcı için** sınar ve mesajın doğru sağlayıcıyı
adlandırdığını doğrular. Ağa çıkmaz.
"""

import pytest

from app.api import chat as chat_api
from app.services import llm_providers as lp


@pytest.fixture(autouse=True)
def temiz_anahtarlar(monkeypatch):
    """Her test kendi anahtar durumunu kursun — makinedeki .env sızmasın.

    ⚠️ Bu fixture olmadan testler geliştirme makinesinin ayarını ölçer;
    bugün aynı tuzağa iki testte düşüldü.
    """
    monkeypatch.setattr(lp, "_anahtarlar", {}, raising=False)
    monkeypatch.setattr("app.config.USE_LOCAL_LLM", False, raising=False)
    monkeypatch.setattr("app.config.OPENROUTER_API_KEY", "", raising=False)
    monkeypatch.setattr("app.config.ANTHROPIC_API_KEY", "", raising=False)


def _sec(monkeypatch, kimlik):
    monkeypatch.setattr("app.config.LLM_PROVIDER", kimlik, raising=False)


# ── Asıl kusur: yerel sağlayıcı anahtar istemez ─────────────────────────────

def test_yerel_saglayici_anahtar_istemez(monkeypatch):
    """🔴 'nin ta kendisi: Ollama seçiliyken sohbet AÇIK olmalı."""
    _sec(monkeypatch, "ollama")
    assert chat_api._llm_key_missing() is False, (
        "Ollama seçili ve anahtar gerektirmiyor, kapı yine de kapalı — "
        "kullanıcı yerel modeli seçmişken bulut anahtarı almaya yollanıyor"
    )


def test_yerel_secilince_mesaj_anahtar_istemez(monkeypatch):
    """Yerel sağlayıcıda sorun 'anahtar' değil 'motor çalışmıyor'dur."""
    _sec(monkeypatch, "ollama")
    m = chat_api._no_key_msg()
    assert "anahtarını gir" not in m, f"yerelde anahtar isteniyor: {m}"


# ── Bulut sağlayıcılar: KENDİ anahtarına bakılmalı ──────────────────────────

def test_bulut_saglayici_kendi_anahtariyla_acilir(monkeypatch):
    _sec(monkeypatch, "groq")
    lp.anahtar_ayarla("groq", "gsk_deneme")
    assert chat_api._llm_key_missing() is False


def test_bulut_saglayici_anahtarsiz_kapali(monkeypatch):
    _sec(monkeypatch, "groq")
    assert chat_api._llm_key_missing() is True


def test_baska_saglayicinin_anahtari_kapiyi_ACMAZ(monkeypatch):
    """🔴 EN ÖNEMLİ REGRESYON TESTİ.

    Eski kapı "herhangi bir anahtar var mı" diye soruyordu. Kullanıcı Groq'u
    seçip anahtarını GİRMEMİŞ ama eskiden OpenRouter anahtarı girmişse, kapı
    açılır ve istek Groq'a anahtarsız giderdi → sohbet 'çalışıyor' görünüp
    sağlayıcıdan anlaşılmaz bir hata dönerdi.
    """
    _sec(monkeypatch, "groq")
    lp.anahtar_ayarla("openrouter", "sk-or-v1-baska")
    assert chat_api._llm_key_missing() is True, (
        "başka sağlayıcının anahtarı seçili sağlayıcının kapısını açıyor"
    )


# ── Mesaj SEÇİLİ sağlayıcıyı adlandırmalı ───────────────────────────────────

def test_mesaj_secili_saglayiciyi_adlandirir(monkeypatch):
    """Eski mesaj her sağlayıcıda 'OpenRouter anahtarını gir' diyordu."""
    _sec(monkeypatch, "groq")
    m = chat_api._no_key_msg()
    sag = lp.kayit("groq")
    assert sag.ad in m, f"mesaj sağlayıcıyı adlandırmıyor: {m}"
    assert "openrouter.ai" not in m.lower(), (
        f"Groq seçiliyken kullanıcı OpenRouter'a yollanıyor: {m}"
    )


def test_mesaj_dogru_anahtar_adresini_verir(monkeypatch):
    _sec(monkeypatch, "google")
    sag = lp.kayit("google")
    if sag.anahtar_url:
        assert sag.anahtar_url in chat_api._no_key_msg()


# ── Kapsam: KAYITTAKİ HER sağlayıcı ─────────────────────────────────────────

@pytest.mark.parametrize("sag", lp.tumu(), ids=lambda s: s.kimlik)
def test_her_saglayici_icin_kapi_dogru_karar_veriyor(monkeypatch, sag):
    """15 sağlayıcının hepsi tek tek sınanır — 'iki tanesini biliyordu' bir
    daha olmasın diye kapsam kaydın kendisinden türetiliyor: kayda yeni
    sağlayıcı eklenince bu test kendiliğinden onu da sınar."""
    _sec(monkeypatch, sag.kimlik)

    if not lp.anahtar_gerekir(sag.kimlik):        # yerel
        assert chat_api._llm_key_missing() is False
        return

    assert chat_api._llm_key_missing() is True    # anahtarsız → kapalı
    lp.anahtar_ayarla(sag.kimlik, "deneme-anahtar")
    assert chat_api._llm_key_missing() is False   # anahtarla → açık


# ── Kenar durumlar ──────────────────────────────────────────────────────────

def test_bilinmeyen_saglayici_calisan_kurulumu_susturmaz(monkeypatch):
    """Kayıtta olmayan bir kimlikte kapı ESKİ davranışa düşer.

    Bilmediğimiz bir ada dayanarak kapıyı KAPATMAK, çalışan bir kurulumu
    susturmak olurdu — yanlış teşhisin bir başka biçimi.
    """
    _sec(monkeypatch, "hic-olmayan-saglayici")
    assert chat_api._llm_key_missing() is True          # hiç anahtar yok
    monkeypatch.setattr("app.config.OPENROUTER_API_KEY", "sk-or-v1-x", raising=False)
    assert chat_api._llm_key_missing() is False         # eski yol hâlâ çalışıyor


def test_use_local_llm_bayragi_kapiyi_acar(monkeypatch):
    """Elle zorlanmış yerel mod — sağlayıcı ne olursa olsun anahtar istemez."""
    _sec(monkeypatch, "openrouter")
    monkeypatch.setattr("app.config.USE_LOCAL_LLM", True, raising=False)
    assert chat_api._llm_key_missing() is False


def test_bos_saglayici_openroutera_duser(monkeypatch):
    """`LLM_PROVIDER` boşsa varsayılan openrouter — eski kurulumlar bozulmasın."""
    _sec(monkeypatch, "")
    assert chat_api._llm_key_missing() is True
    lp.anahtar_ayarla("openrouter", "sk-or-v1-x")
    assert chat_api._llm_key_missing() is False

"""ElevenLabs hata teşhisi — "401" her zaman "anahtarın geçersiz" demek DEĞİL.

🔴 2026-08-02 (kişisel Alice'te ölçüldü, üründe aynı kusur bulundu): log her cevapta
`Client error '401 Unauthorized'` basıyordu ve anahtar geçersiz sanılıyordu. Ölçüm
bunu çürüttü:
  · GET  /v1/voices        → HTTP 200, 21 ses erişilebilir, hedef ses ID'si listede
  · POST /v1/.../stream    → HTTP 401, GÖVDEDE {"code":"quota_exceeded",
                             "message":"You have 0 credits remaining"}

ElevenLabs kota aşımına **429 değil 401** döndürüyor. Kod `raise_for_status()` ile
yalnız durum satırını yakalayıp gövdeyi attığı için 2 hafta yanlış teşhis edildi.

BYOK ürününde bu doğrudan yanlış destek yanıtı: müşterinin kotası bitince ona
"anahtarın geçersiz" demek onu anahtarını boşuna değiştirmeye yönlendirir.

Bu testler ağa ÇIKMAZ — sahte httpx.Response ile ölçer.
"""

import httpx
import pytest

from app.services import tts


@pytest.fixture(autouse=True)
def _katman_durumunu_geri_al():
    """Kalıcı hata bayrağı modül düzeyinde — bir test öbürünü sahte yeşile boyamasın.

    (Kişiselde tam bu sınıftan bir kirlilik yaşandı: bir test toplu koşuda yeşil,
    tek başına kırmızıydı.)
    """
    onceki = tts._elevenlabs_kapali_sebep
    tts._elevenlabs_kapali_sebep = None
    yield
    tts._elevenlabs_kapali_sebep = onceki


def _yanit(status: int, govde) -> httpx.Response:
    istek = httpx.Request("POST", "https://api.elevenlabs.io/v1/text-to-speech/x/stream")
    if isinstance(govde, (bytes, str)):
        return httpx.Response(status, content=govde, request=istek)
    return httpx.Response(status, json=govde, request=istek)


# ── Gövde ayrıştırma ────────────────────────────────────────────────

def test_kota_asimi_401_govdesinden_okunuyor():
    """Gerçek ElevenLabs kota yanıtının biçimi."""
    resp = _yanit(401, {"detail": {"status": "quota_exceeded",
                                   "message": "You have 0 credits remaining"}})
    kod, mesaj = tts._elevenlabs_hata_ayikla(resp)
    assert kod == "quota_exceeded"
    assert "0 credits" in mesaj


def test_code_alani_da_destekleniyor():
    """Bazı uçlar `status` yerine `code` döndürüyor."""
    resp = _yanit(401, {"detail": {"code": "invalid_api_key", "message": "bad key"}})
    kod, _ = tts._elevenlabs_hata_ayikla(resp)
    assert kod == "invalid_api_key"


def test_json_olmayan_govde_cokmuyor():
    """Ağ katmanı HTML hata sayfası döndürebilir — ayrıştırıcı patlamamalı."""
    resp = _yanit(502, b"<html>Bad Gateway</html>")
    kod, mesaj = tts._elevenlabs_hata_ayikla(resp)
    assert kod == ""
    assert "Bad Gateway" in mesaj


# ── Durum doğrulama + katman kapatma ────────────────────────────────

@pytest.mark.asyncio
async def test_kota_bitince_katman_o_oturum_icin_kapaniyor():
    """Kalıcı hatada her cevap boşa bir ağ turu ödememeli."""
    assert tts._elevenlabs_kullanilabilir() or True  # bayrak temiz (fixture)
    resp = _yanit(401, {"detail": {"status": "quota_exceeded", "message": "0 credits"}})

    with pytest.raises(tts._ElevenLabsKaliciHata) as hata:
        await tts._elevenlabs_durum_dogrula(resp)

    # Gerçek sebep mesajda görünmeli — "401" tek başına yanlış yönlendirir.
    assert "quota_exceeded" in str(hata.value)
    assert tts._elevenlabs_kapali_sebep is not None
    assert tts._elevenlabs_kullanilabilir() is False


@pytest.mark.asyncio
async def test_gecici_hata_katmani_kapatmiyor():
    """5xx geçicidir — bir sonraki cevapta tekrar denenmeli."""
    resp = _yanit(503, {"detail": {"status": "service_unavailable", "message": "try later"}})

    with pytest.raises(RuntimeError) as hata:
        await tts._elevenlabs_durum_dogrula(resp)

    assert not isinstance(hata.value, tts._ElevenLabsKaliciHata)
    assert tts._elevenlabs_kapali_sebep is None


@pytest.mark.asyncio
async def test_basarili_yanit_gecirilir():
    await tts._elevenlabs_durum_dogrula(_yanit(200, b"audio"))  # istisna atmamalı
    assert tts._elevenlabs_kapali_sebep is None


def test_sifirlama_katmani_geri_aciyor():
    """Kullanıcı yeni anahtar/kota girince katman yeniden denenebilmeli."""
    tts._elevenlabs_kapali_sebep = "HTTP 401 [quota_exceeded]"
    tts.elevenlabs_durumu_sifirla()
    assert tts._elevenlabs_kapali_sebep is None


# ── Zincir davranışı ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_kalici_hatadan_sonra_zincir_elevenlabs_denemiyor(monkeypatch):
    """Yuki susmaz: Edge TTS devralır, ama ElevenLabs'e boşa gidilmez."""
    monkeypatch.setattr(tts, "USE_ELEVENLABS_TTS", True)
    monkeypatch.setattr(tts, "ELEVENLABS_API_KEY", "sk-test")
    monkeypatch.setattr(tts, "USE_FISH_TTS", False)

    assert tts._elevenlabs_kullanilabilir() is True   # önce açık

    tts._elevenlabs_kapali_sebep = "HTTP 401 [quota_exceeded] 0 credits"
    assert tts._elevenlabs_kullanilabilir() is False  # sonra kapalı

    cagrildi = []

    async def _sahte_el(text):
        cagrildi.append(text)
        return b"el"

    async def _sahte_edge(text):
        return b"edge"

    monkeypatch.setattr(tts, "_synthesize_elevenlabs", _sahte_el)
    monkeypatch.setattr(tts, "_synthesize_edge", _sahte_edge)

    assert await tts.synthesize("merhaba") == b"edge"
    assert cagrildi == []          # ElevenLabs'e hiç gidilmedi

"""Anahtar sihirbazı, geçersiz bir anahtar yüzünden ÇALIŞAN kurulumu bozmamalı.

🔴 SAHA RAPORU — 2026-08-02, gerçek Windows 10 makinesi (müşteri):
kullanıcı çalışan bir OpenRouter anahtarı girmişti; sonra **Ultra LİSANS
anahtarını** aynı kutuya yapıştırdı → sohbet tamamen öldü, ekranda yalnız
`LLM sağlayıcısı isteği reddetti (HTTP 400)` yazıyordu.

Eski akış YIKICIYDI:
    .env'e yaz → runtime'a uygula → SONRA test et → başarısız olsa bile ok:True
`fmt_ok = key.startswith("sk-or-")` zaten hesaplanıyordu ama **hiçbir şeyi
engellemiyordu**; yalnız yanıtta raporlanıyordu.

Ayrıca ölçüldü: OpenRouter, `sk-or-` biçiminde OLMAYAN anahtara
`{"error":{"message":"Missing Authentication header","code":401}}` döndürüyor —
07-31'den beri kaynağı bulunamayan `401 Missing Authentication header` buydu.
(Daha önce OpenRouter "elendi" sanılmıştı çünkü **başlıksız** test edilmişti;
yanlış arıza biçimi test edilmişti.)

Bu testler ağa ÇIKMAZ.
"""

import pytest

from app.api import llm_config_api as api


# ── Yanlış kutu tespiti ─────────────────────────────────────────────

@pytest.mark.parametrize("anahtar", [
    # Gerçek lisans biçimi: <b64url gövde>.<b64url imza>
    "eyJ0aWVyIjoidWx0cmEiLCJlbWFpbCI6ImFAYi5jb20ifQ.c2lnbmF0dXJlX2Jhc2U2NF91cmxfZW5jb2RlZF9oZXJl",
    "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo.YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0",
])
def test_lisans_anahtari_taniniyor(anahtar):
    assert api._lisans_anahtarina_benziyor(anahtar)


@pytest.mark.parametrize("anahtar", [
    "sk-or-v1-1234567890abcdef",        # gerçek OpenRouter anahtarı
    "sk-or-v1-abc.def",                 # sk- ile başlıyorsa lisans değildir
    "kisa.kisa",                        # parçalar çok kısa
    "noktasiz-anahtar",                 # nokta yok
    "a.b.c",                            # üç parça
    "",
])
def test_normal_anahtar_lisans_sanilmiyor(anahtar):
    assert not api._lisans_anahtarina_benziyor(anahtar)


# ── Uç davranışı: ÖNCE doğrula, SONRA kaydet ────────────────────────

class _SahteIstek:
    """slowapi `limiter` bir Request bekler; testte sahtesi yeterli."""
    class _C:
        host = "127.0.0.1"
    client = _C()
    headers: dict = {}
    scope: dict = {"type": "http"}


@pytest.mark.asyncio
async def test_lisans_anahtari_girilince_HICBIR_SEY_yazilmiyor(monkeypatch):
    """Asıl regresyon: çalışan anahtar korunmalı."""
    yazilanlar = []
    monkeypatch.setattr(api, "_persist_env", lambda k, v: yazilanlar.append((k, v)))

    lisans = ("eyJ0aWVyIjoidWx0cmEiLCJlbWFpbCI6ImFAYi5jb20ifQ."
              "c2lnbmF0dXJlX2Jhc2U2NF91cmxfZW5jb2RlZF9oZXJl")
    sonuc = await api.set_api_key.__wrapped__(
        _SahteIstek(), api.ApiKeyBody(key=lisans)
    )

    assert sonuc["ok"] is False
    assert sonuc["applied"] is False
    assert sonuc["hata_tipi"] == "lisans_anahtari"
    assert "LİSANS" in sonuc["error"]
    assert yazilanlar == [], f".env'e yazılmamalıydı: {yazilanlar}"


@pytest.mark.asyncio
async def test_bicimsiz_anahtar_yazilmiyor(monkeypatch):
    yazilanlar = []
    monkeypatch.setattr(api, "_persist_env", lambda k, v: yazilanlar.append((k, v)))

    sonuc = await api.set_api_key.__wrapped__(
        _SahteIstek(), api.ApiKeyBody(key="tamamen-alakasiz-bir-metin")
    )
    assert sonuc["ok"] is False and sonuc["applied"] is False
    assert sonuc["hata_tipi"] == "bicim"
    assert yazilanlar == []


@pytest.mark.asyncio
async def test_test_basarisiz_olursa_eski_anahtar_korunur(monkeypatch):
    """Biçim doğru ama sağlayıcı reddederse de hiçbir şey yazılmamalı.

    "korundu" metni yalnız MEVCUT bir anahtar varken basılır (`llm_config_api` adım 3).
    Mevcut anahtar test içinde sabitlenir; yoksa test yalnız `.env`'inde anahtar olan
    makinede geçiyordu (CI'da "hiçbir şey kaydedilmedi" metni döner).
    """
    yazilanlar = []
    monkeypatch.setattr(api, "_persist_env", lambda k, v: yazilanlar.append((k, v)))
    monkeypatch.setattr(api._lp, "anahtar", lambda kimlik: "mevcut-sahte-anahtar")

    class _Patlayan:
        def __init__(self, **kw): pass
        @property
        def chat(self): return self
        @property
        def completions(self): return self
        async def create(self, **kw): raise RuntimeError("401 Missing Authentication header")

    import openai
    monkeypatch.setattr(openai, "AsyncOpenAI", _Patlayan)

    sonuc = await api.set_api_key.__wrapped__(
        _SahteIstek(), api.ApiKeyBody(key="sk-or-v1-gecersiz-ama-bicimi-dogru")
    )
    assert sonuc["ok"] is False and sonuc["applied"] is False
    assert sonuc["hata_tipi"] == "test"
    assert "korundu" in sonuc["error"]
    assert yazilanlar == [], f"test başarısızken .env'e yazıldı: {yazilanlar}"


@pytest.mark.asyncio
async def test_gecerli_anahtar_kaydediliyor(monkeypatch):
    """Mutlu yol bozulmadı — test geçince yazılır ve uygulanır."""
    yazilanlar = []
    monkeypatch.setattr(api, "_persist_env", lambda k, v: yazilanlar.append((k, v)))

    class _Calisan:
        def __init__(self, **kw): pass
        @property
        def chat(self): return self
        @property
        def completions(self): return self
        async def create(self, **kw): return object()

    import openai
    monkeypatch.setattr(openai, "AsyncOpenAI", _Calisan)

    from app.services import llm as _llm
    monkeypatch.setattr(_llm, "set_openrouter_key", lambda k: None)

    sonuc = await api.set_api_key.__wrapped__(
        _SahteIstek(), api.ApiKeyBody(key="sk-or-v1-gercek-gibi-anahtar")
    )
    assert sonuc["ok"] is True and sonuc["applied"] is True and sonuc["tested"] is True
    assert ("OPENROUTER_API_KEY", "sk-or-v1-gercek-gibi-anahtar") in yazilanlar

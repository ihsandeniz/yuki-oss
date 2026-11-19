"""BYOK model listesi — canlı OpenRouter listesi + çevrimdışı yedek.

🔴 Bu testlerin var olma sebebi (2026-08-01): model listesi `frontend/index.html`de
SABİTTİ. OpenRouter üç ücretsiz modeli birden kaldırınca ürün yeni müşteride sessizce
öldü (`404 No endpoints found`) — ve hatayı ancak müşteri fark etti. Buradaki testler
"sağlayıcı modeli kaldırdı" senaryosunu simüle eder.
"""

import pytest

from app.api import llm_config_api as mod


@pytest.fixture(autouse=True)
def _cache_temizle():
    mod._models_cache["groups"] = None
    mod._models_cache["at"] = 0.0
    yield
    mod._models_cache["groups"] = None
    mod._models_cache["at"] = 0.0


def _sahte_httpx(mocker, models=None, hata: Exception | None = None):
    """`httpx.AsyncClient` yerine sahte istemci koy — gerçek ağa çıkılmaz."""

    class _Resp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": self._data}

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            if hata:
                raise hata
            return _Resp(models or [])

    mocker.patch("httpx.AsyncClient", _Client)


def _m(mid, name=None, tools=True):
    return {
        "id": mid,
        "name": name or mid,
        "supported_parameters": ["tools"] if tools else ["temperature"],
    }


def _ids(payload):
    return [o["id"] for g in payload["groups"] for o in g["options"]]


def _grup(payload, baslik_parcasi):
    for g in payload["groups"]:
        if baslik_parcasi in g["title"]:
            return [o["id"] for o in g["options"]]
    return []


@pytest.mark.asyncio
async def test_canli_liste_dogrulanmis_modeli_one_alir(client, mocker):
    _sahte_httpx(mocker, [
        _m("google/gemma-4-26b-a4b-it:free", "Google: Gemma 4 26B  (free)"),
        _m("openai/gpt-oss-20b:free", "OpenAI: gpt-oss-20b (free)"),
        _m("cohere/north-mini-code:free", "Cohere: North Mini Code (free)"),
        _m("openai/gpt-4.1", "GPT-4.1"),  # ücretsiz değil → elenmeli
    ])
    d = (await client.get("/api/llm/models")).json()

    assert d["ok"] is True and d["source"] == "live"
    assert d["recommended"] == mod.DEFAULT_FREE_MODEL
    assert d["free_available"] is True
    assert _grup(d, "doğrulandı") == [
        "google/gemma-4-26b-a4b-it:free",
        "openai/gpt-oss-20b:free",
    ]
    assert "cohere/north-mini-code:free" in _grup(d, "denenmedi")
    assert "openai/gpt-4.1" not in _ids(d)  # ücretli ön-seçim listesi ayrı


@pytest.mark.asyncio
async def test_arac_desteklemeyen_ve_kara_listedeki_model_elenir(client, mocker):
    _sahte_httpx(mocker, [
        _m("google/gemma-4-26b-a4b-it:free"),
        _m("nvidia/nemotron-3.5-content-safety:free", tools=False),   # tools yok
        _m("nvidia/nemotron-3-nano-30b-a3b:free"),                    # ilan var, ölçümde çağırmadı
    ])
    d = (await client.get("/api/llm/models")).json()

    assert "nvidia/nemotron-3.5-content-safety:free" not in _ids(d)
    assert "nvidia/nemotron-3-nano-30b-a3b:free" not in _ids(d)


@pytest.mark.asyncio
async def test_dogrulanmis_model_kalkinca_listeden_dusuyor(client, mocker):
    """07-31'de tam olarak bu oldu: önerilen model sağlayıcıdan kalktı.

    Artık 'doğrulandı' rozeti canlı listeye bağlı — kalkan model gösterilmez ve
    öneri canlı olan bir ücretsiz modele kayar.
    """
    _sahte_httpx(mocker, [_m("cohere/north-mini-code:free", "Cohere: North Mini Code (free)")])
    d = (await client.get("/api/llm/models")).json()

    assert mod.DEFAULT_FREE_MODEL not in _ids(d)
    assert d["recommended"] == "cohere/north-mini-code:free"
    assert _grup(d, "doğrulandı") == []


@pytest.mark.asyncio
async def test_hic_ucretsiz_model_kalmazsa_durust_davranir(client, mocker):
    _sahte_httpx(mocker, [_m("openai/gpt-4.1")])
    d = (await client.get("/api/llm/models")).json()

    assert d["free_available"] is False
    assert d["recommended"] == mod.PAID_PICKS[0]["id"]
    assert _grup(d, "Ücretli") == [mod.PAID_PICKS[0]["id"]]


@pytest.mark.asyncio
async def test_ag_yoksa_yedek_listeye_duser(client, mocker):
    _sahte_httpx(mocker, hata=RuntimeError("bağlantı yok"))
    d = (await client.get("/api/llm/models")).json()

    assert d["source"] == "fallback"
    assert d["recommended"] == mod.DEFAULT_FREE_MODEL
    assert _grup(d, "doğrulandı") == [v["id"] for v in mod.VERIFIED_FREE]
    assert "bağlantı yok" in d.get("error", "")


@pytest.mark.asyncio
async def test_basarisiz_cevap_onbellege_alinmaz(client, mocker):
    """Yedek cevap 30 dk cache'lenirse ağ geri gelse bile liste bayat kalırdı."""
    _sahte_httpx(mocker, hata=RuntimeError("geçici kesinti"))
    assert (await client.get("/api/llm/models")).json()["source"] == "fallback"

    _sahte_httpx(mocker, [_m("google/gemma-4-26b-a4b-it:free")])
    d = (await client.get("/api/llm/models")).json()
    assert d["source"] == "live" and d["cached"] is False


@pytest.mark.asyncio
async def test_basarili_cevap_onbellege_alinir(client, mocker):
    _sahte_httpx(mocker, [_m("google/gemma-4-26b-a4b-it:free")])
    assert (await client.get("/api/llm/models")).json()["cached"] is False

    _sahte_httpx(mocker, hata=RuntimeError("ikinci çağrı ağa çıkmamalı"))
    d = (await client.get("/api/llm/models")).json()
    assert d["cached"] is True and d["source"] == "live"


def test_olu_model_kimligi_kodda_kalmadi():
    """OpenRouter'dan kalkmış üç model hiçbir varsayılanda/listede kalmamalı."""
    olu = {
        "google/gemini-2.0-flash-exp:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "deepseek/deepseek-chat-v3.1:free",
    }
    kayitli = {v["id"] for v in mod.VERIFIED_FREE} | {p["id"] for p in mod.PAID_PICKS}
    assert not (kayitli & olu)
    assert mod.DEFAULT_FREE_MODEL not in olu

    from pathlib import Path
    kok = Path(__file__).resolve().parents[2]
    for rel in ("frontend/index.html", "backend/app/api/llm_config_api.py"):
        metin = (kok / rel).read_text(encoding="utf-8")
        for mid in olu:
            assert mid not in metin, f"{rel} hâlâ ölü model içeriyor: {mid}"

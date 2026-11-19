"""ChatGPT ile resmî giriş ("Continue with ChatGPT") — ağsız testler.

Gerçek OpenAI hesabı ve ağ KULLANILMAZ: kimlik sunucusu çağrıları (`_form_post`) ve
Responses akışı taklit edilir.
"""
import asyncio
import json
import os
import re
import stat
import time
from pathlib import Path
from types import SimpleNamespace as NS
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.services.chatgpt_plan import giris as _giris
from app.services.chatgpt_plan import istemci as ist
from app.services.chatgpt_plan import kimlik as kim

PAKET = Path(kim.__file__).parent
FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
TOKEN_AT = "AT-gizli-erisim-123"
TOKEN_RT = "RT-gizli-yenileme-456"
TOKEN_ID = "ID-gizli-kimlik-789"


@pytest.fixture(autouse=True)
def dizin(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_CHATGPT_DIZIN", str(tmp_path / "cg"))
    return tmp_path / "cg"


def _yanit(kod=200, govde=None):
    return httpx.Response(kod, json=govde or {}, request=httpx.Request("POST", "http://x"))


def _token_cevabi(kapsam="openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"):
    return {"access_token": TOKEN_AT, "refresh_token": TOKEN_RT, "id_token": TOKEN_ID,
            "expires_in": 3600, "token_type": "Bearer", "scope": kapsam}


def _giris_yap(monkeypatch, kapsam=None, mevcut=None):
    """Tarayıcı + kimlik sunucusu taklidi ile bir giriş turu; (kayıt, url, istekler)."""
    istekler = []

    def sahte_post(url, veri, zaman_asimi=20.0):
        istekler.append((url, dict(veri)))
        return _yanit(200, _token_cevabi(kapsam) if kapsam else _token_cevabi())

    monkeypatch.setattr(kim, "_form_post", sahte_post)
    monkeypatch.setattr(kim, "id_token_dogrula",
                        lambda tok, cid, nonce, bulucu=None: {"sub": "kullanici-1", "email": "a@b.test"})
    deneme = kim.deneme_baslat("http://127.0.0.1:1455/auth/callback", mevcut)
    url = kim.yetki_url(deneme, mevcut)
    cid = "oaiapp_test123" if deneme.yeni_kayit else deneme.client_id
    kayit = kim.kod_degistir(deneme, {"state": deneme.state, "code": "KOD", "client_id": cid}, mevcut)
    return kayit, url, istekler


# ---------------------------------------------------------------- kimlik

def test_ilk_kayit_dynamic_agent_client_ve_yuki_adi(monkeypatch):
    _, url, _ = _giris_yap(monkeypatch)
    q = parse_qs(urlparse(url).query)
    assert q["client_id"] == ["dynamic_agent_client"]
    assert q["agent_name_hint"] == ["Yuki"]
    assert q["code_challenge_method"] == ["S256"]
    assert q["ext_agent_host_id"][0].startswith("urn:uuid:")
    assert "chatgpt.tokens.use.direct" in q["scope"][0]
    assert urlparse(url).netloc == "auth.openai.com"


def test_dynamic_client_id_kaydedilmez_oaiapp_saklanir(monkeypatch):
    kayit, _, _ = _giris_yap(monkeypatch)
    assert kayit.client_id == "oaiapp_test123"
    assert json.loads(kim.kimlik_dosyasi().read_text())["client_id"] == "oaiapp_test123"
    with pytest.raises(kim.PlanKimlikHatasi):
        kim.kaydet(kim.Kayit(client_id="dynamic_agent_client"))


def test_yeniden_giriste_kayitli_client_id_ve_agent_name_yok(monkeypatch):
    kayit, _, _ = _giris_yap(monkeypatch)
    _, url, _ = _giris_yap(monkeypatch, mevcut=kayit)
    q = parse_qs(urlparse(url).query)
    assert q["client_id"] == ["oaiapp_test123"]
    assert "agent_name_hint" not in q


def test_token_dosyasi_0600_dizin_0700(monkeypatch):
    _giris_yap(monkeypatch)
    assert stat.S_IMODE(os.stat(kim.kimlik_dosyasi()).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(kim.dizin()).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(kim.host_dosyasi()).st_mode) == 0o600
    assert kim.kimlik_dosyasi().name == "chatgpt_token.json"


def test_host_kimligi_kalici():
    assert kim.host_kimligi() == kim.host_kimligi()


def test_state_uyusmazligi_reddedilir():
    d = kim.deneme_baslat("http://127.0.0.1:1455/auth/callback")
    with pytest.raises(kim.GeriDonusHatasi):
        kim.kod_degistir(d, {"state": "baska", "code": "K", "client_id": "oaiapp_x"})


def test_kod_degisiminde_resource_pkce_ve_dynamic_yok(monkeypatch):
    _, _, istekler = _giris_yap(monkeypatch)
    url, veri = istekler[0]
    assert url.endswith("/api/accounts/oauth/token")
    assert veri["grant_type"] == "authorization_code"
    assert veri["client_id"] == "oaiapp_test123"
    assert veri["resource"] == "https://api.openai.com/v1"
    assert veri["code_verifier"]


def test_plan_kapsami_yoksa_cikarim_kapali(monkeypatch):
    _giris_yap(monkeypatch, kapsam="openid profile email")
    with pytest.raises(kim.PlanKullanimiKapali):
        kim.gecerli_kimlik()
    assert kim.durum()["plan_acik"] is False


def test_gecerli_kimlik_yoksa_giris_yok():
    with pytest.raises(kim.PlanGirisYok):
        kim.gecerli_kimlik()
    assert kim.durum()["giris"] is False


def test_yenileme_kayitli_client_id_scope_yok_yeni_refresh_saklanir(monkeypatch):
    kayit, _, _ = _giris_yap(monkeypatch)
    kayit.expires_at = int(time.time()) - 10
    kim.kaydet(kayit)
    istekler = []

    def post(url, veri, zaman_asimi=20.0):
        istekler.append(veri)
        return _yanit(200, {**_token_cevabi(), "access_token": "AT2", "refresh_token": "RT2"})

    monkeypatch.setattr(kim, "_form_post", post)
    yeni = kim.gecerli_kimlik()
    assert yeni.access_token == "AT2" and yeni.refresh_token == "RT2"
    assert istekler[0]["grant_type"] == "refresh_token"
    assert istekler[0]["client_id"] == "oaiapp_test123"
    assert "scope" not in istekler[0]
    assert json.loads(kim.kimlik_dosyasi().read_text())["refresh_token"] == "RT2"


def test_olu_refresh_token_yeniden_giris_ister_client_id_kalir(monkeypatch):
    kayit, _, _ = _giris_yap(monkeypatch)
    monkeypatch.setattr(kim, "_form_post",
                        lambda *a, **k: _yanit(400, {"error": {"code": "refresh_token_expired"}}))
    with pytest.raises(kim.PlanGirisGerekli):
        kim.tazele(kayit)
    kalan = kim.oku()
    assert kalan.client_id == "oaiapp_test123" and not kalan.refresh_token


def test_gecici_hata_kimligi_silmez(monkeypatch):
    kayit, _, _ = _giris_yap(monkeypatch)
    monkeypatch.setattr(kim, "_form_post", lambda *a, **k: _yanit(503, {}))
    with pytest.raises(kim.PlanGeciciHata):
        kim.tazele(kayit)
    assert kim.oku().refresh_token == TOKEN_RT


def test_cikis_refresh_iptal_eder_tokenlari_siler(monkeypatch):
    _giris_yap(monkeypatch)
    cagrilar = []

    def post(url, veri, zaman_asimi=20.0):
        cagrilar.append((url, veri))
        return _yanit(200, {})

    monkeypatch.setattr(kim, "_form_post", post)
    assert kim.cikis() == {"cikis": True, "uzak_iptal": True}
    assert cagrilar[0][0].endswith("/oauth/revoke")
    k = kim.oku()
    assert not k.access_token and not k.refresh_token and not k.id_token
    assert k.client_id == "oaiapp_test123"


def test_durum_ve_repr_sir_icermez(monkeypatch):
    kayit, _, _ = _giris_yap(monkeypatch)
    metin = json.dumps(kim.durum()) + repr(kayit)
    for sir in (TOKEN_AT, TOKEN_RT, TOKEN_ID):
        assert sir not in metin


def test_log_token_icermez(monkeypatch, caplog):
    caplog.set_level("DEBUG")
    kayit, _, _ = _giris_yap(monkeypatch)
    kayit.expires_at = 1
    kim.kaydet(kayit)
    monkeypatch.setattr(kim, "_form_post", lambda *a, **k: _yanit(200, _token_cevabi()))
    kim.gecerli_kimlik()
    kim.cikis()
    for sir in (TOKEN_AT, TOKEN_RT, TOKEN_ID):
        assert sir not in caplog.text


def test_dinleyici_yalniz_127_0_0_1_ve_auth_callback():
    d = _giris._Dinleyici(0)
    try:
        assert d.redirect_uri.startswith("http://127.0.0.1:")
        assert d.redirect_uri.endswith("/auth/callback")
        r = httpx.get(f"http://127.0.0.1:{d.port}/auth/callback?code=K&state=S")
        assert r.status_code == 200
        assert d.bekle(1) == {"code": "K", "state": "S"}
    finally:
        d.kapat()


def test_giris_tarayici_donusu_ile_kaydeder(monkeypatch):
    monkeypatch.setattr(kim, "_form_post", lambda *a, **k: _yanit(200, _token_cevabi()))
    monkeypatch.setattr(kim, "id_token_dogrula", lambda *a, **k: {"sub": "s", "email": ""})

    def tarayici(url):
        q = parse_qs(urlparse(url).query)
        httpx.get(q["redirect_uri"][0], params={"code": "K", "state": q["state"][0],
                                                "client_id": "oaiapp_zz"})
        return True

    kayit = _giris.giris(ac=tarayici, port=0, zaman_asimi=5)
    assert kayit.plan_acik and kayit.client_id == "oaiapp_zz"


# ---------------------------------------------------------------- istemci (biçim çevirme)

def test_mesaj_cevirme_sistem_arac_cagrisi_ve_sonucu():
    talimat, girdi = ist.mesajlari_cevir([
        {"role": "system", "content": "Sen Yuki'sin."},
        {"role": "user", "content": "saat kaç"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "saat", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "12:00"},
        {"role": "assistant", "content": "Saat 12:00"},
    ])
    assert talimat == "Sen Yuki'sin."
    assert girdi[0] == {"role": "user", "content": "saat kaç"}
    assert girdi[1] == {"type": "function_call", "call_id": "c1", "name": "saat", "arguments": "{}"}
    assert girdi[2] == {"type": "function_call_output", "call_id": "c1", "output": "12:00"}
    assert girdi[3] == {"role": "assistant", "content": "Saat 12:00"}


def test_gorselli_kullanici_icerigi():
    _, girdi = ist.mesajlari_cevir([{"role": "user", "content": [
        {"type": "text", "text": "bu ne"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}}]}])
    assert girdi[0]["content"] == [{"type": "input_text", "text": "bu ne"},
                                   {"type": "input_image", "image_url": "data:image/png;base64,AAA"}]


def test_arac_cevirme_duz_function():
    t = ist.araclari_cevir([{"type": "function", "function": {
        "name": "saat", "description": "d", "parameters": {"type": "object", "properties": {}}}}])
    assert t == [{"type": "function", "name": "saat", "description": "d",
                  "parameters": {"type": "object", "properties": {}}}]
    assert ist.araclari_cevir(None) == []


async def _akis(olaylar):
    for o in olaylar:
        yield o


def _olaylar_metin():
    return [NS(type="response.output_text.delta", delta="Mer"),
            NS(type="response.output_text.delta", delta="haba"),
            NS(type="response.completed", response=NS(usage=NS(input_tokens=5, output_tokens=2, total_tokens=7)))]


def _olaylar_arac():
    return [NS(type="response.output_item.added", item=NS(type="function_call", id="fc_1", call_id="call_1", name="saat")),
            NS(type="response.function_call_arguments.delta", item_id="fc_1", delta='{"a":'),
            NS(type="response.function_call_arguments.delta", item_id="fc_1", delta='1}'),
            NS(type="response.completed", response=NS(usage=None))]


def test_olaylar_chunka_metin_ve_arac():
    async def calis():
        metin = [c async for c in ist.olaylari_chunka(_akis(_olaylar_metin()))]
        arac = [c async for c in ist.olaylari_chunka(_akis(_olaylar_arac()))]
        return metin, arac

    metin, arac = asyncio.run(calis())
    assert "".join(c.choices[0].delta.content or "" for c in metin) == "Merhaba"
    assert metin[-1].choices[0].finish_reason == "stop" and metin[-1].usage.completion_tokens == 2
    tc = [t for c in arac for t in (c.choices[0].delta.tool_calls or [])]
    assert tc[0].id == "call_1" and tc[0].function.name == "saat" and tc[0].index == 0
    assert "".join(t.function.arguments or "" for t in tc) == '{"a":1}'
    assert arac[-1].choices[0].finish_reason == "tool_calls"


def test_topla_stream_olmayan_cevap():
    async def calis():
        return await ist._topla(ist.olaylari_chunka(_akis(_olaylar_arac())))

    tc = asyncio.run(calis()).choices[0].message.tool_calls[0]
    assert (tc.id, tc.function.name, tc.function.arguments) == ("call_1", "saat", '{"a":1}')


def test_basarisiz_yanit_hata_firlatir():
    async def calis():
        return [c async for c in ist.olaylari_chunka(_akis([NS(type="response.failed", response=NS(error="x"))]))]

    with pytest.raises(RuntimeError):
        asyncio.run(calis())


def test_create_responses_govdesi_ve_akis(monkeypatch):
    """Uçtan uca (taklit): Chat Completions çağrısı → Responses gövdesi → chunk akışı."""
    gorulen = {}
    c = ist.ChatGPTAsyncClient()

    async def ac(govde, timeout):
        gorulen.update(govde)
        return _akis(_olaylar_metin())

    monkeypatch.setattr(c, "_ac", ac)

    async def calis():
        akis = await c.chat.completions.create(
            model="gpt-x", stream=True, tool_choice="auto", temperature=0.2,
            messages=[{"role": "system", "content": "S"}, {"role": "user", "content": "U"}],
            tools=[{"type": "function", "function": {"name": "t", "parameters": {}}}])
        return "".join([ch.choices[0].delta.content or "" async for ch in akis])

    assert asyncio.run(calis()) == "Merhaba"
    assert gorulen["model"] == "gpt-x" and gorulen["store"] is False and gorulen["stream"] is True
    assert gorulen["instructions"] == "S" and gorulen["input"] == [{"role": "user", "content": "U"}]
    assert "temperature" not in gorulen and "tool_choice" not in gorulen
    assert gorulen["tools"][0]["name"] == "t"


def test_ac_401de_yenileyip_bir_kez_dener(monkeypatch):
    from openai import AuthenticationError
    c = ist.ChatGPTAsyncClient()
    tokenlar = []

    async def token(zorla_tazele=False):
        tokenlar.append(zorla_tazele)
        return "t"

    class R:
        async def create(self, **k):
            if len(tokenlar) < 2:
                raise AuthenticationError(
                    "no", response=httpx.Response(401, request=httpx.Request("POST", "http://x")), body=None)
            return "AKIS"

    monkeypatch.setattr(c, "_token", token)
    monkeypatch.setattr(c, "_sdk", lambda t, to: NS(responses=R()))
    assert asyncio.run(c._ac({}, None)) == "AKIS"
    assert tokenlar == [False, True]


# ---------------------------------------------------------------- API

@pytest.fixture
def api(monkeypatch):
    from app.services import llm
    monkeypatch.setattr(llm, "_runtime_provider", "openrouter")
    monkeypatch.setattr(llm, "_runtime_model", "m")
    monkeypatch.setattr("app.api.llm_config_api._persist_env", lambda k, v: None)
    return TestClient(app)


def test_api_durum_girissiz(api):
    d = api.get("/api/chatgpt/durum").json()
    assert d["ok"] and d["giris"] is False and d["aktif"] is False


def test_api_sec_giris_yoksa_reddeder(api):
    assert api.post("/api/chatgpt/sec", json={}).json()["ok"] is False


def test_api_sec_ve_cikis(api, monkeypatch):
    from app.services import llm
    _giris_yap(monkeypatch)
    d = api.post("/api/chatgpt/sec", json={"model": "gpt-x"}).json()
    assert d["ok"] and d["provider"] == "chatgpt"
    assert llm.aktif_saglayici() == "chatgpt"
    st = api.get("/api/llm/key/status").json()
    assert st["set"] is True and st["provider"] == "chatgpt" and st["anahtar_gerekir"] is False
    assert TOKEN_AT not in json.dumps(st)
    monkeypatch.setattr(kim, "_form_post", lambda *a, **k: _yanit(200, {}))
    assert api.post("/api/chatgpt/cikis").json()["ok"]
    assert llm.aktif_saglayici() == "openrouter"
    assert api.get("/api/chatgpt/durum").json()["giris"] is False


def test_api_sec_plan_kapaliysa_reddeder(api, monkeypatch):
    _giris_yap(monkeypatch, kapsam="openid profile email")
    assert api.post("/api/chatgpt/sec", json={}).json()["ok"] is False


def test_api_giris_arka_planda_baslar(api, monkeypatch):
    import app.api.chatgpt_api as ca
    cagrildi = []
    monkeypatch.setattr(ca, "_giris_isi", lambda: cagrildi.append(1))
    monkeypatch.setitem(ca._giris, "durum", "bos")
    assert api.post("/api/chatgpt/giris").json()["giris_durumu"] == "bekliyor"
    time.sleep(0.3)
    assert cagrildi == [1]


def test_llm_istemcisi_chatgpt_secilince_kendi_istemcisi(monkeypatch):
    from app.services import llm
    monkeypatch.setattr(llm, "_runtime_provider", "chatgpt")
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm, "_last_damga", None)
    assert isinstance(llm._get_client(force_cloud=True), ist.ChatGPTAsyncClient)


def test_byok_yolu_acik_kalir():
    from app.services import llm_providers as lp
    assert lp.kayit("openrouter") is not None and lp.anahtar_gerekir("openai")


# ---------------------------------------------------------------- kurallar

def test_pakette_baska_istemci_kimligi_ve_ozel_uc_yok():
    # Desen parçalı yazıldı: temizlik kapısı bu dosyayı da taradığı için kendini yakalamasın.
    yasak = re.compile("co" + "dex|origin" + "ator|chat" + "gpt\\.com|backend" + "-api|ali" + "ce", re.I)
    for p in PAKET.glob("*.py"):
        assert not yasak.findall(p.read_text(encoding="utf-8")), p.name


def test_gitignore_token_dosyalarini_tutar():
    satirlar = (FRONTEND.parent / ".gitignore").read_text(encoding="utf-8").splitlines()
    for g in ("/chatgpt_plan/", "chatgpt_token.json", "chatgpt_host.json"):
        assert g in satirlar


def test_uc_noktalari_resmi():
    assert kim.auth_taban() == "https://auth.openai.com"
    assert kim.api_taban() == "https://api.openai.com/v1"


def test_arayuzde_dugme_metni_continue_with_chatgpt():
    for dil in ("en", "tr"):
        js = (FRONTEND / "js" / "diller" / f"{dil}.js").read_text(encoding="utf-8")
        assert "'hq.anahtar.chatgpt-giris': 'Continue with ChatGPT'" in js

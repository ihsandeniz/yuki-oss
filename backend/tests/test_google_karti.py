"""GOOGLE · BAĞLANTI KARTI ( panel 11, 2026-09-28 — geliştirici taslak A'yı seçti).

Kapatılan kusurlar ve kapıları:

① **Yalan yeşil.** Panel `connected = bool(token)` ile "Bağlı" diyordu — token dosyası, Google
   izni aylar önce kaldırmış olsa bile diskte durur. Artık her yenileme sonucunu ve zamanını
   token'ın yanına yazar; `durum` bu kayıttan: yok · hazir · denenmedi · bagli · kopuk.
② **`invalid_client`/`invalid_grant`/`unauthorized_client` → kopuk**, token SİLİNMEZ ama "bağlı"
   da denmez; kimlik `Değiştir` ile değişince eski bağlantı kopuk sayılır.
③ **PLAN yanlış teşhis.** Bizim 401 (oturum kilidi) ile Google'ın reddi aynı kodla geliyordu ve
   ekranda her şeye "Google cevap vermedi" deniyordu. Google tarafı artık 409/502 + `X-Google-Durum`.
④ **Çift tık.** "Şimdi dene"ye hızlı üç tık = Google'a TEK istek (hem panelde hem uçta).
⑤ Callback çıplak 500 · yan etkili GET disconnect · `/api/planner/status` yer tutucuyu sayması ·
   sohbet aracının sabit Türkçe "Planner sayfasından bağlan" cümlesi.

Hiçbir test Google'a çıkmaz: `httpx.AsyncClient` sahtesi yanıtları verir ve istekleri sayar.
Panelin davranışı `node` ile gerçek dosya üzerinde koşturulur (DOM sahtesi); node yoksa atlanır.
"""
from __future__ import annotations

import asyncio
import glob
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from yardim import FRONTEND, sozluk, yorumsuz

_CID = "1234-abc.apps.googleusercontent.com"
_CID2 = "9999-yeni.apps.googleusercontent.com"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


@pytest.fixture(autouse=True)
def ortam(tmp_path, monkeypatch):
    """Token GEÇİCİ dizinde; kimlik geçerli. geliştiricinin gerçek token dosyasına dokunulmaz."""
    monkeypatch.setenv("YUKI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOOGLE_CLIENT_ID", _CID)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "GOCSPX-gizli")
    import app.api.llm_config_api as llm_api
    monkeypatch.setattr(llm_api, "_persist_env", lambda k, v: None)
    return tmp_path


def _yanit(kod: int, govde=None, url: str = _TOKEN_URL) -> httpx.Response:
    return httpx.Response(kod, json=govde if govde is not None else {}, request=httpx.Request("POST", url))


class _Google:
    """`httpx.AsyncClient` sahtesi — url → yanıt (ya da istisna). Her isteği kaydeder."""

    def __init__(self, yanitlar: dict, gecikme: float = 0.0):
        self.yanitlar, self.gecikme, self.cagri = yanitlar, gecikme, []

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def _gonder(self, yontem, url, **k):
        self.cagri.append((yontem, url, k))
        if self.gecikme:
            await asyncio.sleep(self.gecikme)
        y = self.yanitlar[(yontem, url)] if (yontem, url) in self.yanitlar else self.yanitlar[url]
        if callable(y):
            y = y()
        if isinstance(y, Exception):
            raise y
        return y

    async def post(self, url, **k):
        return await self._gonder("POST", url, **k)

    async def get(self, url, **k):
        return await self._gonder("GET", url, **k)


def _google(monkeypatch, yanitlar, gecikme=0.0) -> _Google:
    g = _Google(yanitlar, gecikme)
    monkeypatch.setattr(httpx, "AsyncClient", g)
    return g


def _tok(**ek) -> dict:
    tok = {"access_token": "eski", "refresh_token": "r",
           "scope": "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/drive.file",
           "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()}
    tok.update(ek)
    return tok


def _yaz(tok):
    from app.services import google_token_store as depo
    depo.google_yaz(tok)


def _durum() -> dict:
    from app.api import planner
    return asyncio.run(planner.google_status.__wrapped__(None))


# ── ① yalan yeşil ────────────────────────────────────────────────────────────

def test_token_var_ama_hic_denenmemis_BAGLI_DENMEZ():
    """Dosyanın varlığı bağlantının sağlığı değildir: denenmemiş token 'denenmedi'dir."""
    _yaz(_tok())
    d = _durum()
    assert d["connected"] is True, "geriye uyum alanı (dosya var) korunmalı"
    assert d["durum"] == "denenmedi", f"denenmemiş bağlantıya '{d['durum']}' dendi — yalan yeşil"
    assert d["son_deneme"] is None


def test_basarili_yenileme_BAGLI_ve_zamani_yazar(monkeypatch):
    from app.services import google_client as g
    _yaz(_tok())
    _google(monkeypatch, {_TOKEN_URL: _yanit(200, {"access_token": "yeni", "expires_in": 3600})})
    asyncio.run(g.erisim_tokeni())
    d = _durum()
    assert d["durum"] == "bagli" and d["son_deneme"]["ok"] is True
    zaman = datetime.fromisoformat(d["son_deneme"]["zaman"])
    assert abs((datetime.now(timezone.utc) - zaman).total_seconds()) < 30
    from app.services import google_token_store as depo
    assert depo.google_al()["kimlik_izi"] == g.kimlik_izi(_CID), "token kimliğe bağlanmadı"


# ── ② Google'ın reddi → kopuk, token durur ───────────────────────────────────

@pytest.mark.parametrize("kod,hata", [(401, "invalid_client"), (400, "invalid_grant"), (400, "unauthorized_client")])
def test_red_KOPUK_der_token_SILINMEZ_bagli_DENMEZ(monkeypatch, kod, hata):
    from app.services import google_client as g
    from app.services import google_token_store as depo
    _yaz(_tok(deneme={"ok": True, "zaman": datetime.now(timezone.utc).isoformat(), "sebep": None}))
    _google(monkeypatch, {_TOKEN_URL: _yanit(kod, {"error": hata})})
    with pytest.raises(g.GoogleYetkiDustu):
        asyncio.run(g.yenile(depo.google_al()))
    d = _durum()
    assert d["durum"] == "kopuk" and d["sebep"] == hata, d
    assert depo.google_al().get("refresh_token") == "r", "token silindi — sebebi gösterecek kayıt kalmadı"


def test_gecici_hata_KOPUK_DEMEZ_kayit_degismez(monkeypatch):
    """5xx/ağ geçicidir: kullanıcıyı yeniden bağlanmaya yollamaz."""
    from app.services import google_client as g
    from app.services import google_token_store as depo
    _yaz(_tok(deneme={"ok": True, "zaman": "2026-09-28T10:00:00+00:00", "sebep": None}))
    _google(monkeypatch, {_TOKEN_URL: _yanit(503, {"error": "backendError"})})
    with pytest.raises(RuntimeError):
        asyncio.run(g.yenile(depo.google_al()))
    assert _durum()["durum"] == "bagli"


def test_kopuk_baglanti_Googlea_TEKRAR_SORULMAZ(monkeypatch):
    """Yedekleme zamanlayıcısı ve sohbet reddedilen yenilemeyi her çağrıda tekrarlamasın."""
    from app.services import google_client as g
    _yaz(_tok(deneme={"ok": False, "zaman": "2026-09-28T10:00:00+00:00", "sebep": "invalid_grant"}))
    sahte = _google(monkeypatch, {_TOKEN_URL: _yanit(200, {"access_token": "x"})})
    with pytest.raises(g.GoogleYetkiDustu):
        asyncio.run(g.erisim_tokeni())
    assert sahte.cagri == [], "kopuk bilinen bağlantı için Google'a istek atıldı"


def test_yetki_dustu_metni_TEK_SEBEBE_yuklenmez():
    """ledger `oauth/invalid-grant-testing-modunun-tekelinde-degil`: Testing tek sebep değil."""
    from app.mesajlar import M
    for dil in ("tr", "en"):
        metin = M("google.yetki-dustu", dil=dil)
        assert "myaccount.google.com/permissions" in metin, "izni hesaptan kaldırma sebebi yok"
        assert ("parola" in metin) if dil == "tr" else ("password" in metin), "parola değişimi sebebi yok"
        assert "Testing" in metin and "7" in metin


# ── kimlik değişimi ──────────────────────────────────────────────────────────

def test_kimlik_DEGISINCE_eski_baglanti_kopuk_AYNI_kimlikte_degil():
    from app.api import planner
    _yaz(_tok(deneme={"ok": True, "zaman": datetime.now(timezone.utc).isoformat(), "sebep": None}))
    cevap = asyncio.run(planner.google_kimlik_kaydet.__wrapped__(
        None, planner.GoogleKimlikBody(client_id=_CID, client_secret="GOCSPX-yeni")))
    assert cevap["ayni_kimlik"] is True
    assert _durum()["durum"] == "bagli", "yalnız gizli anahtar düzeltildi — bağlantı koparılmamalı"

    cevap = asyncio.run(planner.google_kimlik_kaydet.__wrapped__(
        None, planner.GoogleKimlikBody(client_id=_CID2, client_secret="GOCSPX-yeni")))
    assert cevap["ayni_kimlik"] is False
    d = _durum()
    assert d["durum"] == "kopuk" and d["sebep"] == "kimlik-degisti", d


def test_planner_status_YER_TUTUCU_kimligi_yapilandirilmis_saymaz(monkeypatch):
    from app.api import planner
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "yer-tutucu")
    d = asyncio.run(planner.planner_status.__wrapped__(None))
    assert d["google_client_configured"] is False
    monkeypatch.setenv("GOOGLE_CLIENT_ID", _CID)
    assert asyncio.run(planner.planner_status.__wrapped__(None))["google_client_configured"] is True


# ── /google/dene ─────────────────────────────────────────────────────────────

def test_dene_ESZAMANLI_uc_istek_Googlea_TEK_istek(monkeypatch):
    """④ Çift tık uçta da korunur: kilit ikinci isteği ilkinin sonucuna bağlar."""
    from app.api import planner
    _yaz(_tok())
    sahte = _google(monkeypatch, {_TOKEN_URL: _yanit(200, {"access_token": "yeni", "expires_in": 3600})}, gecikme=0.05)

    async def uc_kez():
        return await asyncio.gather(*(planner.google_dene.__wrapped__(None) for _ in range(3)))

    sonuclar = asyncio.run(uc_kez())
    assert len(sahte.cagri) == 1, f"Google'a {len(sahte.cagri)} istek gitti"
    assert all(s["durum"] == "bagli" for s in sonuclar)


def test_dene_kimlik_degistiyse_Googlea_GITMEZ(monkeypatch):
    from app.api import planner
    from app.services import google_client as g
    _yaz(_tok(kimlik_izi=g.kimlik_izi(_CID2)))
    sahte = _google(monkeypatch, {_TOKEN_URL: _yanit(200, {"access_token": "x"})})
    d = asyncio.run(planner.google_dene.__wrapped__(None))
    assert sahte.cagri == [] and d["denendi"] is False
    assert d["durum"] == "kopuk" and d["sebep"] == "kimlik-degisti"


def test_dene_ag_yoksa_GECICI_der_kayit_bozulmaz(monkeypatch):
    from app.api import planner
    _yaz(_tok(deneme={"ok": True, "zaman": "2026-09-28T10:00:00+00:00", "sebep": None}))
    _google(monkeypatch, {_TOKEN_URL: httpx.ConnectError("ag yok")})
    d = asyncio.run(planner.google_dene.__wrapped__(None))
    assert d["gecici"] is True and d["durum"] == "bagli"


def test_status_ve_dene_AYNI_govdeyi_doner(monkeypatch):
    from app.api import planner
    _yaz(_tok())
    _google(monkeypatch, {_TOKEN_URL: _yanit(200, {"access_token": "y", "expires_in": 3600})})
    d = asyncio.run(planner.google_dene.__wrapped__(None))
    assert set(_durum()) <= set(d), "iki yüzey aynı soruya farklı alanlarla cevap veriyor"


# ── ③ PLAN takvim uçları: 401 bizim, Google'ınki başlıklı 409/502 ─────────────

@pytest.fixture
def istemci():
    from starlette.testclient import TestClient
    from app.api.todo import require_planner
    from app.main import app
    app.dependency_overrides[require_planner] = lambda: None
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(require_planner, None)


_OLAY = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


def _taze_tok():
    return _tok(expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                deneme={"ok": True, "zaman": datetime.now(timezone.utc).isoformat(), "sebep": None})


def test_takvim_KOPUK_409_ve_basligi_401_DEGIL(istemci):
    _yaz(_tok(deneme={"ok": False, "zaman": "2026-09-28T10:00:00+00:00", "sebep": "invalid_grant"}))
    r = istemci.get("/api/planner/google/events")
    assert r.status_code == 409 and r.headers.get("X-Google-Durum") == "kopuk", (r.status_code, r.headers)


def test_takvim_403_IZIN_YOK_der_500_degil(istemci, monkeypatch):
    _yaz(_taze_tok())
    _google(monkeypatch, {_OLAY: httpx.Response(403, json={"error": {"errors": [{"reason": "insufficientPermissions"}]}},
                                                 request=httpx.Request("GET", _OLAY))})
    r = istemci.get("/api/planner/google/events")
    assert r.status_code == 409 and r.headers.get("X-Google-Durum") == "izin-yok"
    assert "Takvim izni" in r.json()["detail"]


def test_takvim_Google_CEVAPSIZ_yalniz_gercekten_cevapsizken(istemci, monkeypatch):
    _yaz(_taze_tok())
    _google(monkeypatch, {_OLAY: httpx.ConnectError("zaman aşımı")})
    r = istemci.get("/api/planner/google/events")
    assert r.status_code == 502 and r.headers.get("X-Google-Durum") == "cevapsiz"


def test_takvim_401de_BIR_KEZ_yeniler_token_SILINMEZ(istemci, monkeypatch):
    from app.services import google_token_store as depo
    _yaz(_taze_tok())
    sayac = {"n": 0}

    def olaylar():
        sayac["n"] += 1
        kod = 401 if sayac["n"] == 1 else 200
        return httpx.Response(kod, json={"items": []}, request=httpx.Request("GET", _OLAY))

    _google(monkeypatch, {_OLAY: olaylar, _TOKEN_URL: _yanit(200, {"access_token": "taze", "expires_in": 3600})})
    r = istemci.get("/api/planner/google/events")
    assert r.status_code == 200 and sayac["n"] == 2
    assert depo.google_al()["access_token"] == "taze"


# ── ⑤ callback · disconnect · sohbet aracı ───────────────────────────────────

def _state(planner):
    return planner._generate_state_token("google")


def test_callback_degisim_REDDEDILINCE_musteri_sayfasi_500_degil(istemci, monkeypatch):
    from app.api import planner
    _google(monkeypatch, {_TOKEN_URL: _yanit(401, {"error": "invalid_client"})})
    r = istemci.get("/api/planner/google/callback", params={"code": "k", "state": _state(planner)})
    assert r.status_code == 400 and r.headers["content-type"].startswith("text/html")
    assert "istemci kimliğin geçersiz" in r.text
    assert "style=" not in r.text and "✅" not in r.text and "⚠️" not in r.text


def test_callback_IPTAL_edilen_onay_422_degil_sayfa(istemci):
    r = istemci.get("/api/planner/google/callback", params={"error": "access_denied"})
    assert r.status_code == 400 and "izin verilmedi" in r.text


def test_callback_basarili_DENEME_yazar_satir_ici_stil_emoji_yok(istemci, monkeypatch):
    from app.api import planner
    from app.services import google_client as g
    _google(monkeypatch, {_TOKEN_URL: _yanit(200, {"access_token": "a", "refresh_token": "r", "expires_in": 3600,
                                                   "scope": planner._GOOGLE_SCOPES})})
    r = istemci.get("/api/planner/google/callback", params={"code": "k", "state": _state(planner)})
    assert r.status_code == 200 and "Takvim ve Drive izinleri verildi" in r.text
    assert "style=" not in r.text and "✅" not in r.text
    d = _durum()
    assert d["durum"] == "bagli", "gerçek bir değişim az önce yapıldı — denenmiş sayılmalı"
    from app.services import google_token_store as depo
    assert depo.google_al()["kimlik_izi"] == g.kimlik_izi(_CID)


@pytest.mark.parametrize("revoke,iptal", [(lambda: _yanit(200, {}), True),
                                          (lambda: httpx.ConnectError("yok"), False)])
def test_disconnect_POST_Googleda_geri_alir_alamazsa_SOYLER(istemci, monkeypatch, revoke, iptal):
    from app.services import google_token_store as depo
    _yaz(_tok())
    _google(monkeypatch, {"https://oauth2.googleapis.com/revoke": revoke})
    r = istemci.post("/api/planner/google/disconnect")
    assert r.status_code == 200 and r.json()["iptal"] is iptal
    assert depo.google_al() is None


def test_sohbet_takvim_araci_DOGRU_YERI_ve_SEBEBI_soyler(monkeypatch):
    from app import config
    from app.services.tools import calendar
    metin = asyncio.run(calendar.get_calendar_events())
    assert "Planner" not in metin and "GOOGLE" in metin, metin
    _yaz(_tok(deneme={"ok": False, "zaman": "2026-09-28T10:00:00+00:00", "sebep": "invalid_client"}))
    metin = asyncio.run(calendar.create_calendar_event("a", "2026-09-28T10:00:00", "2026-09-28T11:00:00"))
    assert "istemci kimliğin geçersiz" in metin, "kimlik kaynaklı düşüşe 'bağlı değil' dendi"
    onceki = config.get_arayuz_dili()
    try:
        config.set_arayuz_dili("en", persist=False)
        assert "client ID" in asyncio.run(calendar.delete_calendar_event("x"))
    finally:
        config.set_arayuz_dili(onceki, persist=False)


# ── Panel davranışı (gerçek dosya, node + DOM sahtesi) ───────────────────────

def _node() -> str | None:
    yol = shutil.which("node")
    if yol:
        return yol
    adaylar = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/node")))
    return adaylar[-1] if adaylar else None


_KOSUM = r"""
const fs = require('fs');
const S = JSON.parse(process.argv[process.argv.length - 1]);
const cagri = [];
global.window = global;
window.YukiDil = { t: (k, d) => k + (d ? JSON.stringify(d) : ''), yerel: () => 'tr-TR' };
window.addEventListener = () => {};
const cizimler = [];
const el = { _h: '', get innerHTML() { return this._h; }, set innerHTML(v) { this._h = v; cizimler.push(v); },
  offsetParent: {}, dinle: {},
  addEventListener(t, f) { this.dinle[t] = f; }, contains() { return true; },
  querySelector(s) { const m = /data-g="kes"[^>]*?data-onay="1"/.test(this.innerHTML);
    return { dataset: { onay: m ? '1' : '' } }; } };
global.document = { hidden: false, addEventListener() {},
  getElementById(id) { return id === 'hq-panel-google' ? el : null; } };
function yanit(kod, govde) { return { status: kod, ok: kod >= 200 && kod < 300,
  headers: { get: () => null }, json: async () => govde }; }
window.authFetch = (url, o) => { const y = (o && o.method) || 'GET'; cagri.push(y + ' ' + url);
  const c = S[y + ' ' + url] || S[url] || [404, {}];
  return new Promise(r => setTimeout(() => r(yanit(c[0], c[1])), 15)); };
window.open = () => {};
eval(fs.readFileSync(S.dosya, 'utf8'));
const bekle = ms => new Promise(r => setTimeout(r, ms));
const tikla = g => el.dinle.click({ target: { closest: () => ({ dataset: { g }, disabled: false }) } });
(async () => {
  window.googlePanelAc(); await bekle(120);
  const acilis = el.innerHTML, acilisCagri = cagri.slice();
  cagri.length = 0;
  for (const g of (S.tik || [])) { tikla(g); if (S.aralik) await bekle(S.aralik); }
  await bekle(150);
  console.log(JSON.stringify({ acilis, acilisCagri, son: el.innerHTML, cagri, cizimler }));
})();
"""


def _panel(senaryo: dict) -> dict:
    node = _node()
    if not node:
        pytest.skip("node yok — panel davranışı ölçülemedi")
    senaryo = {"dosya": str(FRONTEND / "js" / "google-baglanti.js"), **senaryo}
    r = subprocess.run([node, "-e", _KOSUM, json.dumps(senaryo)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


_S = "/api/planner/google/status"
_D = "POST /api/planner/google/dene"


def _st(**ek):
    d = {"connected": True, "durum": "denenmedi", "sebep": None, "son_deneme": None, "kimlik_var": True,
         "kimlik_bicimsiz": False, "client_id": "1234-a…com", "eksik_izin": []}
    d.update(ek)
    return d


def test_panel_DENENMEMIS_baglantiya_yesil_yakmaz_bir_kez_kendisi_dener():
    simdi = datetime.now(timezone.utc).isoformat()
    s = _panel({_S: [200, _st()], _D: [200, _st(durum="bagli", son_deneme={"ok": True, "zaman": simdi})]})
    ilk = next(c for c in s["cizimler"] if "gg-bas" in c)          # durum okunduktan sonraki ilk çizim
    assert "google.baslik-denenmedi" in ilk and "durum-isik iyi" not in ilk, "denenmemiş bağlantıya yeşil yandı"
    assert s["acilisCagri"].count("POST /api/planner/google/dene") == 1, s["acilisCagri"]
    assert "google.baslik-bagli" in s["acilis"] and "durum-isik iyi" in s["acilis"], "başarılı denemeden sonra yeşil yok"


def test_panel_TAZE_denemede_Googlea_sormaz():
    simdi = datetime.now(timezone.utc).isoformat()
    s = _panel({_S: [200, _st(durum="bagli", son_deneme={"ok": True, "zaman": simdi})]})
    assert not any("dene" in c for c in s["acilisCagri"]), s["acilisCagri"]


def test_panel_UC_hizli_tik_TEK_istek_bitince_dugme_ACILIR():
    simdi = datetime.now(timezone.utc).isoformat()
    b = _st(durum="bagli", son_deneme={"ok": True, "zaman": simdi})
    s = _panel({_S: [200, b], _D: [200, b], "tik": ["dene", "dene", "dene"]})
    assert s["cagri"].count("POST /api/planner/google/dene") == 1, s["cagri"]
    dene = re.search(r'<button[^>]*data-g="dene"[^>]*>', s["son"]).group(0)
    assert "disabled" not in dene, "iş bitti ama 'Şimdi dene' pasif kaldı (tur 1'de ölçüldü)"


def test_panel_KOPUK_kirmizi_ve_sebebe_gore_cozum():
    s = _panel({_S: [200, _st(durum="kopuk", sebep="invalid_client",
                              son_deneme={"ok": False, "zaman": "2026-09-28T10:00:00+00:00", "sebep": "invalid_client"})]})
    h = s["acilis"]
    assert "durum-isik kritik" in h and "google.neden-client" in h
    assert 'data-g="degistir"' in h.split("gg-neden")[1][:600], "kimlik hatasında çözüm 'Kimliği değiştir' olmalı"
    assert "durum-isik iyi" not in h


def test_panel_401_ve_429_AYRI_ham_metin_yok():
    s = _panel({_S: [401, {"detail": "Unauthorized"}]})
    assert "hq.oturum-kilitli" in s["acilis"] and "Unauthorized" not in s["acilis"]
    s = _panel({_S: [429, {"detail": "Rate limit exceeded"}]})
    assert "google.cok-sik" in s["acilis"] and "Rate limit" not in s["acilis"]
    s = _panel({_S: [500, {"detail": "Internal Server Error"}]})
    assert "google.durum-hata" in s["acilis"] and "google.yukiye-ulasilamadi" not in s["acilis"], \
        "Yuki cevap verdi (500) ama ekran 'ulaşılamadı' diyor"


def test_panel_KES_iki_adim_ve_r_ok_denetler():
    simdi = datetime.now(timezone.utc).isoformat()
    b = _st(durum="bagli", son_deneme={"ok": True, "zaman": simdi})
    s = _panel({_S: [200, b], "tik": ["kes"]})
    assert s["cagri"] == [], "ilk tık bağlantıyı kesti — onay adımı yok"
    s = _panel({_S: [200, b], "POST /api/planner/google/disconnect": [500, {}], "tik": ["kes", "kes"], "aralik": 40})
    assert s["cagri"].count("POST /api/planner/google/disconnect") == 1
    assert "google.kesilemedi" in s["son"], "başarısız kesme sessiz geçti"
    s = _panel({_S: [200, b], "POST /api/planner/google/disconnect": [200, {"ok": True, "iptal": False}],
                "tik": ["kes", "kes"], "aralik": 40})
    assert "google.kesildi-yerel" in s["son"], "Google'da geri alınamayan izin söylenmedi"


def test_panel_KAYDET_mesaji_yeniden_cizimde_KAYBOLMAZ():
    s = _panel({_S: [200, _st(connected=False, durum="yok", kimlik_var=False)],
                "POST /api/planner/google/kimlik": [200, {"ok": True, "ayni_kimlik": False}], "tik": ["kaydet"]})
    assert "google.kaydedildi" in s["son"], "Kaydet sonrası başarı mesajı tazelemede silindi"


# ── goz tur 5 (2026-10-01) ───────────────────────────────────────────────────

def test_goz5_KAYDET_400_hatasi_FORMUN_icinde_alan_isaretli_ustte_degil():
    s = _panel({_S: [200, _st(connected=False, durum="yok", kimlik_var=False)],
                "POST /api/planner/google/kimlik": [400, {"detail": "Kimlik biçimi yanlış"}], "tik": ["kaydet"]})
    form = re.search(r'class="ak-form gg-form">(.*?)</div></div>', s["son"], re.S).group(1)
    assert "Kimlik biçimi yanlış" in form and "ak-uyari" in form, "400 cümlesi formun içinde değil"
    assert form.count('aria-invalid="true"') == 2, "hatalı alanlar işaretlenmedi"
    mesaj = re.search(r'<p id="g-mesaj"[^>]*>(.*?)</p>', s["son"], re.S).group(1)
    assert "Kimlik biçimi" not in mesaj, "aynı hata iki yerde"


def test_goz5_YEDEK_hatasi_yesil_izin_hapinin_arkasinda_GIZLENMEZ():
    simdi = datetime.now(timezone.utc).isoformat()
    s = _panel({_S: [200, _st(durum="bagli", son_deneme={"ok": True, "zaman": simdi})],
                "/api/yedekleme/durum": [200, {"son_tur": {"hata": "x", "bitti": simdi}}]})
    h = s["acilis"]
    assert "google.etiket-yedek-hata" in h and "google.baslik-bagli-yedek" in h, "yedek hatası görünmüyor"
    assert "durum-isik iyi" not in h, "yedek hatası varken yeşil ışık"
    assert "google.son-basarili" not in h


def test_goz5_EKSIK_izin_uyarisinin_altinda_BASARILI_yazmaz():
    simdi = datetime.now(timezone.utc).isoformat()
    s = _panel({_S: [200, _st(durum="bagli", eksik_izin=["https://www.googleapis.com/auth/drive.file"],
                              son_deneme={"ok": True, "zaman": simdi})]})
    assert "google.baslik-bagli-eksik" in s["acilis"] and "google.son-basarili" not in s["acilis"]


def test_goz5_DENENMEDI_basligi_alt_satirla_CELISMEZ():
    # ulaşılamadı: "henüz sorulmadı" yazmaz, sebep mesajı konuşur
    b = _st(durum="denenmedi", son_deneme=None)
    s = _panel({_S: [200, b], _D: [200, {**b, "denendi": True, "gecici": True}]})
    assert "google.dene-ulasilamadi" in s["son"] and "google.denenmedi-alt" not in s["son"], "sorulmadı + ulaşılamadı aynı blokta"
    # sürerken: başlık "denenmedi" değil "deneniyor"
    assert any("google.baslik-deneniyor" in c and "google.baslik-denenmedi" not in c for c in s["cizimler"]), "soruluyor iken başlık hâlâ 'denenmedi'"


def test_goz5_KIMLIK_hatasinda_TEK_degistir_dugmesi():
    s = _panel({_S: [200, _st(durum="kopuk", sebep="invalid_client",
                              son_deneme={"ok": False, "zaman": "2026-09-28T10:00:00+00:00", "sebep": "invalid_client"})]})
    assert s["acilis"].count('data-g="degistir"') == 1, "aynı iş için iki düğme"
    assert "google.baslik-kopuk-client" in s["acilis"]


def test_goz5_OKUNAMADI_isigi_soruluyor_isigindan_AYRI():
    s = _panel({_S: [429, {}]})
    assert "durum-isik olculemedi" not in s["acilis"] and "durum-isik uyari" in s["acilis"]


def test_goz5_PLAN_izin_yokken_serit_cikar_giris_pasif_ve_EKLE_reddi_seridi_acar():
    pl = (FRONTEND / "planner.html").read_text(encoding="utf-8")
    assert "inp.disabled = _aypDurum !== 'bagli' || izinYok" in pl, "izin yokken giriş davetkâr"
    assert re.search(r"else if \(tur === 'izin'\) \{ _aypHata = 'izin'; aypCiz\(\); \}", pl), \
        "EKLE izin yüzünden reddedilince şerit çıkmıyor (üstte BU GÜN BOŞ kalıyor)"


# ── PLAN takvim hatası: 401 "Google cevap vermedi" DEĞİLDİR ─────────────────

def test_PLAN_401_OTURUM_der_Google_cevap_vermedi_DEMEZ():
    node = _node()
    if not node:
        pytest.skip("node yok")
    kod = yorumsuz((FRONTEND / "planner.html").read_text(encoding="utf-8"))
    fonk = re.search(r"function _aypRet\(r\) \{.*?\n\}", kod, re.S).group(0)
    kosum = fonk + """
const h = (g) => ({ get: () => g });
console.log(JSON.stringify([_aypRet({status:401, headers:h(null)}), _aypRet({status:429, headers:h(null)}),
  _aypRet(null), _aypRet({status:409, headers:h('izin-yok')}), _aypRet({status:502, headers:h('cevapsiz')})]));"""
    r = subprocess.run([node, "-e", kosum], capture_output=True, text=True, timeout=30)
    assert json.loads(r.stdout) == ["kilitli", "cok", "ulasilamadi", "izin", "google"], r.stdout + r.stderr
    harita = re.search(r"const HATA = \{(.*?)\};", kod, re.S).group(1)
    satirlar = {m.group(1): m.group(2) for m in re.finditer(r"(\w+): \[([^\]]+)\]", harita)}
    assert "gtakvim.hata-alt" not in satirlar["kilitli"], "oturum kilidine 'Google cevap vermedi' deniyor"
    assert [k for k, v in satirlar.items() if "gtakvim.hata-alt" in v] == ["google"]


def test_kullanilan_ANAHTARLAR_iki_dilde():
    tr, en = sozluk("tr"), sozluk("en")
    js = yorumsuz((FRONTEND / "js" / "google-baglanti.js").read_text(encoding="utf-8"))
    pl = (FRONTEND / "planner.html").read_text(encoding="utf-8")
    anahtarlar = set(re.findall(r"'((?:google|gtakvim|hq)\.[\w.-]+)'", js))
    anahtarlar |= set(re.findall(r"'(gtakvim\.[\w-]+)'", pl))
    anahtarlar = {k for k in anahtarlar if not k.endswith("-")} | {f"google.adim1-{x}" for x in "abcd"}
    eksik = [f"{d}: {k}" for k in sorted(anahtarlar) for d, s in (("tr", tr), ("en", en)) if k not in s]
    assert not eksik, eksik

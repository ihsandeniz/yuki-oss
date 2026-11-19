"""
Planner API — Google Calendar + Microsoft To-Do
Endpoint prefix: /api/planner

Kademe: Pro (vitrin "Planlayıcı — görev, liste, takvim"). Kapı router düzeyinde;
gerekçe + Free'nin açık kalan yolu → `app/api/todo.py::require_planner`.
"""
import asyncio
import json
import logging
import os
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from app.limiter import limiter
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from app.api.todo import require_planner
from app.mesajlar import M

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/planner", tags=["planner"],
                   dependencies=[Depends(require_planner)])

# 🔴 2026-09-14 — bu iki yol `backend/`e sabitti ve SATILAN PAKETTE SALT OKUNURDU:
# kullanıcı Google'a bağlansa bile oturumu kaydedilemiyordu. 2026-07-31'de kapatılan
# dört kusurun ATLANMIŞ BEŞİNCİSİ (o turda kardeşi `calendar.py` düzeltilmişti).
# Ayrıca ikisi aynı adı farklı dizinde arıyordu → AYAR'dan bağlanan kullanıcıya
# sohbette "bağlı değilsin" deniyordu. Tek kaynak: `services/google_token_store`.
from app.services import google_token_store as _tok_deposu
# 🔵 2026-09-14 (FAZ 4): erişim tokeni + Drive çağrıları tek kaynakta.
# Gerekçe modülün kendi başlığında: aynı işi yapan iki kopya vardı, Drive üçüncüsü
# olacaktı ve üçü yenileme hatasını farklı yutuyordu.
from app.services import google_client as _gc


# ── Token persistence ─────────────────────────────────────────────────────────

def _load_tokens() -> dict:
    return _tok_deposu.yukle()


def _save_tokens(data: dict):
    _tok_deposu.kaydet(data)


def _load_state_tokens() -> dict:
    """OAuth state token'larını yükle — CSRF koruması için."""
    yol = _tok_deposu.durum_dosyasi()
    if yol.exists():
        try:
            return json.loads(yol.read_text())
        except Exception:
            pass
    return {}


def _save_state_tokens(data: dict):
    """OAuth state token'larını kaydet (yazılabilir veri kökünde)."""
    yol = _tok_deposu.durum_dosyasi()
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(data, indent=2))
    # Dosya izni: yalnız sahibi okur/yazar. Windows'ta etkisiz ama hatasız.
    try:
        os.chmod(yol, 0o600)
    except Exception:
        pass


def _generate_state_token(provider: str) -> str:
    """Rastgele state token üret ve kaydet."""
    state = secrets.token_urlsafe(32)
    states = _load_state_tokens()
    states[state] = {"provider": provider, "created_at": datetime.now(timezone.utc).isoformat()}
    _save_state_tokens(states)
    return state


def _validate_state_token(state: str, provider: str) -> bool:
    """State token'ını doğrula — CSRF saldırısını engelle."""
    if not state:
        return False
    states = _load_state_tokens()
    data = states.get(state)
    if not data:
        return False
    if data.get("provider") != provider:
        return False
    # Token'ı use et ve sil (replay attack'ları engelle)
    del states[state]
    _save_state_tokens(states)
    # Cleanup: 1 saatten eski token'ları sil
    now = datetime.now(timezone.utc)
    for old_state, old_data in list(states.items()):
        try:
            created = datetime.fromisoformat(old_data.get("created_at", ""))
            if (now - created).total_seconds() > 3600:
                del states[old_state]
        except Exception:
            pass
    _save_state_tokens(states)
    return True


# 🔵 2026-09-14 (FAZ 4) — modül seviyesindeki `_tokens` GLOBAL'İ KALDIRILDI.
# Bir kopya, ikinci yazar doğduğu an bayatlar: yedekleme zamanlayıcısı token
# yeniliyor ve bu süreç onu görmüyordu → kullanıcı bağlıyken "bağlı değilsin".
# Her okuma/yazma artık `google_token_store` üzerinden, tek kaynaktan geçer.


# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE CALENDAR
# ══════════════════════════════════════════════════════════════════════════════

# 🔵 2026-09-14 — scope DARALTILDI + Drive eklendi.
#    Karar (2026-09-14): OAuth kimliği kullanıcının kendi Google Cloud projesinden gelir.
#    · `calendar` → `calendar.events`: takvimin TAMAMINI yönetme yetkisi (takvim
#      oluşturma/silme, ayarlar) hiç kullanılmıyordu; kod yalnız `.../events`
#      uçlarına gidiyor. Gereğinden geniş izin istemek, kullanıcının onay ekranında
#      gördüğü şeyi de büyütür.
#    · `drive.file`: YALNIZ uygulamanın oluşturduğu ya da kullanıcının bizzat
#      seçtiği dosyalar. Tam `drive` scope'u Google'ın **restricted** sınıfındadır
#      ve kullanıcıyı da gereksiz bir denetim yüzeyine sokardı.
# ⚠️ Scope değişince MEVCUT token yetmez — kullanıcı yeniden onay vermeli.
#    `/google/status` bunu `eksik_izin` ile söyler, sessizce 403'e düşmez.
_GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/calendar.events "
    "https://www.googleapis.com/auth/drive.file"
)
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


# ⚠️ Hata metni KULLANICIYA gider. Eski hâli (*"GOOGLE_CLIENT_ID .env'de tanımlı
#    değil"*) kullanıcıya hiçbir şey anlatmıyordu: `.env` diye bir dosyayı ne görür
#    ne açabilir. Metin artık ne yapacağını söylüyor — ElevenLabs "401 = kota"
#    dersinin aynısı: doğru teşhis, doğru çözüme yollar.
#    🌐 metin katalogda (`planlayici.kimlik-yok`) ve ÇAĞRI anında üretilir —
#    modül sabiti ilk dilde donardı. `_KIMLIK_YOK` adı dışarıdan okunmaya devam
#    eder (testler) ama modül `__getattr__`'ı üzerinden, her okumada güncel dilde.
def __getattr__(ad: str) -> str:
    if ad == "_KIMLIK_YOK":
        return M("planlayici.kimlik-yok")
    raise AttributeError(ad)


def _google_client_id() -> str:
    v = os.getenv("GOOGLE_CLIENT_ID", "")
    if not v:
        raise HTTPException(503, M("planlayici.kimlik-yok"))
    return v


def _google_client_secret() -> str:
    v = os.getenv("GOOGLE_CLIENT_SECRET", "")
    if not v:
        raise HTTPException(503, M("planlayici.kimlik-yok"))
    return v


def _google_redirect_uri(request: Request) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/planner/google/callback"


async def _google_refresh(tok: dict) -> dict:
    """Access token süresi dolduysa refresh token ile yenile.

    🔵 2026-09-14 (FAZ 4): gövde `services/google_client`'a **devredildi**. Eskiden
    buradaki kod ile `services/tools/calendar.py::_get_access_token` aynı işi iki
    ayrı yerde yapıyordu; Drive üçüncüsünü yazacaktı. Yenileme hatasının anlamı
    (özellikle `invalid_grant` = 7 günlük 'Testing' iptali) artık **tek yerde**
    çözülüyor ve kullanıcıya ne yapacağını söyleyen bir metne çevriliyor.
    """
    return await _gc.yenile(tok)


async def _google_token() -> str:
    """Geçerli erişim tokeni. Kaynak: `google_client` (tek kaynak).

    ⚠️ Eskiden modül seviyesindeki `_tokens` global'inden okunuyordu. Yedekleme
    (FAZ 4) **zamanlayıcıdan** token yeniliyor — yani ikinci bir yazar var — ve
    global o anda bayatlıyordu: kullanıcı bağlıyken *"bağlı değilsin"* alabilirdi.
    Artık her çağrı diskten okur.

    🔴 **401 DEĞİL, 409 (2026-09-28):** 401 bizim oturum kapımızın cevabıdır (uygulama
    kilidi). Google'ın reddini de 401 ile döndürmek PLAN'ın ikisini ayıramamasına yol
    açıyordu — kilitli oturumda "Google bağlantısı koptu" denebiliyordu. Google kaynaklı
    her durum 409 + `X-Google-Durum` başlığıyla gelir; metin `detail`'de (kullanıcı cümlesi).
    """
    try:
        return await _gc.erisim_tokeni()
    except _gc.GoogleBagliDegil:
        raise _google_hatasi("bagli-degil", M("planlayici.takvim-bagli-degil"))
    except _gc.GoogleYetkiDustu as e:
        raise _google_hatasi("kopuk", str(e))


def _google_hatasi(kod: str, metin: str, durum: int = 409) -> HTTPException:
    """Google tarafındaki durumu bizim oturum hatalarımızdan AYIRAN tek biçim.

    `kod`: bagli-degil · kopuk · izin-yok · cevapsiz. Başlık okunur, metin gösterilir.
    """
    return HTTPException(durum, metin, headers={"X-Google-Durum": kod})


async def _takvim_istegi(yontem: str, url: str, **kw) -> httpx.Response:
    """Takvim API çağrısı — Google'ın cevabını kullanıcı diline çevirir.

    Eskiden `raise_for_status()`: izin eksik (403) → bizim ucumuz 500 veriyordu ve PLAN
    "Google cevap vermedi" diyordu; oysa Google cevap vermişti, "izin yok" demişti.
    401'de token SİLİNİYORDU — yani bir erişim tokeninin süresi sayaçtan önce dolsa
    bile bağlantı yok ediliyordu. Artık 401'de bir kez yenilenir ve tekrar denenir;
    yenileme de reddedilirse `yenile` bağlantıyı "kopuk" diye kaydeder.
    """
    async def _gonder(erisim: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=20) as c:
            gonder = c.post if yontem == "POST" else c.get
            return await gonder(url, headers={"Authorization": f"Bearer {erisim}"}, **kw)

    try:
        r = await _gonder(await _google_token())
        if r.status_code == 401:
            tok = _tok_deposu.google_al()
            if not tok:
                raise _google_hatasi("bagli-degil", M("planlayici.takvim-bagli-degil"))
            try:
                tok = await _gc.yenile(tok)
            except _gc.GoogleYetkiDustu as e:
                raise _google_hatasi("kopuk", str(e))
            r = await _gonder(tok.get("access_token", ""))
    except httpx.HTTPError as e:
        logger.warning("Google Takvim'e ulaşılamadı: %s", e)
        raise _google_hatasi("cevapsiz", M("planlayici.google-cevapsiz"), 502)
    except RuntimeError as e:          # yenileme ucu geçici hata verdi (5xx)
        logger.warning("Google token yenilenemedi: %s", e)
        raise _google_hatasi("cevapsiz", M("planlayici.google-cevapsiz"), 502)
    if 200 <= r.status_code < 300:
        return r
    if r.status_code == 401:
        raise _google_hatasi("kopuk", M("google.yetki-dustu"))
    if r.status_code == 403:
        govde = (r.text or "")[:400]
        # Kota/oran sınırı da 403 ile gelir — o "izin yok" DEĞİLDİR, beklemek yeter.
        if "rateLimitExceeded" in govde or "userRateLimitExceeded" in govde or "quotaExceeded" in govde:
            raise _google_hatasi("cevapsiz", M("planlayici.google-yogun"), 502)
        raise _google_hatasi("izin-yok", M("planlayici.takvim-izni-yok"))
    if r.status_code == 429:
        raise _google_hatasi("cevapsiz", M("planlayici.google-yogun"), 502)
    logger.warning("Google Takvim %s döndü: %s", r.status_code, (r.text or "")[:200])
    raise _google_hatasi("cevapsiz", M("planlayici.google-cevapsiz"), 502)


@router.get("/google/auth-url")
@limiter.limit("100/minute")
async def google_auth_url(request: Request):

    """Google OAuth auth URL'i döner — CSRF state token ile."""
    cid = _google_client_id()
    redirect = _google_redirect_uri(request)
    state = _generate_state_token("google")
    params = urllib.parse.urlencode({
        "client_id": cid,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": _GOOGLE_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,  # CSRF koruması
    })
    return {"url": f"{_GOOGLE_AUTH_URL}?{params}"}


def _callback_metni(scope: str) -> tuple[bool, str]:
    """Bağlantı sonrası sayfanın gövdesi — **Google'ın döndürdüğü kapsamdan**.

    🔴 **Neden ölçülerek yazılıyor (2026-09-14, geliştiricinin ilk gerçek turu):** sayfa
    *"Takvim ve Drive izinleri verildi"* diye **sabit** yazıyordu. O turda Google
    yalnız `drive.file` verdi; aynı anda panel doğru cevabı biliyordu
    (`eksik_izin: [calendar.events]`). İki yüzey aynı soruya zıt cevap veriyordu
    ve kullanıcının gördüğü **ilk** ekran yanlış olandı — eksik izin bir hafta
    sonra *"takvimimi neden görmüyor"* olarak geri döner.

    Döner: (iki izin de var mı, HTML gövde).
    """
    verilen = set(scope.split())
    takvim = "https://www.googleapis.com/auth/calendar.events" in verilen
    drive = "https://www.googleapis.com/auth/drive.file" in verilen
    if takvim and drive:
        return True, M("planlayici.izin-tam")

    duzelt = M("planlayici.izin-duzelt")
    if not takvim and not drive:
        return False, M("planlayici.izin-hic-yok", duzelt=duzelt)
    if not takvim:
        return False, M("planlayici.izin-takvim-yok", duzelt=duzelt)
    return False, M("planlayici.izin-drive-yok", duzelt=duzelt)


def _donus_sayfasi(baslik: str, govde: str, isik: str, durum: int = 200,
                   kapat: bool = True) -> HTMLResponse:
    """Onay dönüşü sayfası — SİSTEM TARAYICISINDA açılır, uygulamanın stili orada yok.

    Satır içi stil ve emoji yok (2026-09-28): durum başlıkla söylenir, simgeyle değil;
    görünüm `/ui/css/google-donus.css`'ten (ürün token'ları). Dil = uygulamanın dili.
    """
    from app.mesajlar import mevcut_dil
    dil = mevcut_dil()
    # `isik`: iyi · uyari (bağlandı, izin eksik) · kritik. Pencere yalnız TAM başarıda
    # kendini kapatır — eksik izin uyarısı okunmadan kapanmasın.
    betik = ""
    if isik != "kritik":
        betik = ("<script>try{window.opener&&window.opener.postMessage('google_ok','*');"
                 + ("window.close();" if isik == "iyi" else "") + "}catch(e){}</script>")
    return HTMLResponse(
        f"<!doctype html><html lang='{dil}' data-tema='koyu'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Yuki · Google</title>"
        "<link rel='stylesheet' href='/ui/vendor/fonts.css?v=1'>"
        "<link rel='stylesheet' href='/ui/css/tokens.css?v=8'>"
        "<link rel='stylesheet' href='/ui/css/google-donus.css?v=1'>"
        f"{betik}</head><body><main class='gd-kart' data-durum='{isik}'>"
        f"<h1>{baslik}</h1><p>{govde}</p>"
        + (f"<p class='gd-alt'>{M('planlayici.donus-kapat')}</p>" if kapat else "")
        + "</main></body></html>",
        status_code=durum,
    )


def _degisim_hatasi(r) -> tuple[str, int]:
    """Kod→token değişimi reddedildiyse kullanıcı cümlesi. Eskiden `raise_for_status` → çıplak 500."""
    hata = _gc._google_hatasi(r)
    if hata == "invalid_client" or hata == "unauthorized_client":
        return M("google.kimlik-gecersiz"), 400
    if hata == "redirect_uri_mismatch":
        return M("planlayici.donus-yonlendirme"), 400
    if hata == "invalid_grant":
        return M("planlayici.donus-kod-gecersiz"), 400
    return M("planlayici.donus-google-hatasi", kod=r.status_code), 502


@router.get("/google/callback")
@limiter.limit("30/minute")
async def google_callback(request: Request, code: str | None = Query(None),
                          state: str | None = Query(None), error: str | None = Query(None)):

    """Google OAuth callback — state token'ını doğrula (CSRF koruması).

    Her hata kullanıcıya SAYFA olarak döner (JSON değil): burası tarayıcıda açılır.
    """
    basarisiz = M("planlayici.donus-basarisiz")
    # Kullanıcı onay ekranında "İptal"e bastı ya da Google reddetti → `?error=access_denied`,
    # `code` YOK. Eskiden `code` zorunluydu ve kullanıcı ham 422 JSON görüyordu.
    if error or not code:
        return _donus_sayfasi(basarisiz, M("planlayici.donus-reddedildi"), "kritik", 400)
    # CSRF koruması: state token'ını doğrula
    if not state or not _validate_state_token(state, "google"):
        # "CSRF saldırısı tespit edildi" kullanıcıyı korkutur; gerçekte en sık sebep eski/
        # ikinci kez açılmış onay sekmesidir. Koruma aynı, cümle doğru olan.
        return _donus_sayfasi(basarisiz, M("planlayici.donus-eski-baglanti"), "kritik", 400)

    cid = os.getenv("GOOGLE_CLIENT_ID", "")
    sec = os.getenv("GOOGLE_CLIENT_SECRET", "")
    if not (cid and sec):
        return _donus_sayfasi(basarisiz, M("planlayici.kimlik-yok"), "kritik", 400)
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(_GOOGLE_TOKEN_URL, data={
                "code": code,
                "client_id": cid,
                "client_secret": sec,
                "redirect_uri": _google_redirect_uri(request),
                "grant_type": "authorization_code",
            })
    except httpx.HTTPError as e:
        logger.warning("Google onay kodu değişimi: ağ hatası %s", e)
        return _donus_sayfasi(basarisiz, M("planlayici.donus-ulasilamadi"), "kritik", 502)
    if not r.is_success:
        logger.warning("Google onay kodu değişimi reddedildi (%s): %s", r.status_code, (r.text or "")[:200])
        metin, kod = _degisim_hatasi(r)
        return _donus_sayfasi(basarisiz, metin, "kritik", kod)
    tok = r.json()
    tok["expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=tok.get("expires_in", 3600))
    ).isoformat()
    # Değişim az önce Google'la GERÇEKTEN yapıldı → bu bir deneme; iz, token'ı kimliğe bağlar.
    tok["kimlik_izi"] = _gc.kimlik_izi(cid)
    _gc.deneme_kaydet(tok, True)
    # ⚠️ Bu sayfa SİSTEM TARAYICISINDA açılır (Electron `dis-baglanti.js` her dış
    #    bağlantıyı `openExternal`'a devreder) → `window.opener` YOKTUR ve
    #    `window.close()` kullanıcının kendi açmadığı bir sekmede çalışmaz.
    #    O yüzden mesaj tek başına ayakta durmalı: script bir "bonus", metin asıl
    #    arayüzdür. Eski hâli yalnız "Calendar" diyordu — Drive de bu izinde.
    #
    # 🔴 **Metin SABİT YAZILMAZ (ölçüldü 2026-09-14, geliştiricinin ilk gerçek turu):**
    #    sayfa *"Takvim ve Drive izinleri verildi"* diyordu; o turda Google
    #    yalnız `drive.file` verdi ve panel aynı anda `eksik_izin: [calendar.events]`
    #    gösteriyordu. Yani iki yüzey aynı soruya **zıt** cevap veriyordu ve
    #    kullanıcının gördüğü ilk ekran yanlış olandı. Artık metin Google'ın
    #    DÖNDÜRDÜĞÜ kapsamdan üretilir — eksik izin burada, fark edildiği anda
    #    söylenir; bir hafta sonra "takvimimi neden görmüyor" olarak dönmez.
    tam, govde = _callback_metni(tok.get("scope") or "")
    baslik = M("planlayici.hesap-baglandi") if tam else M("planlayici.hesap-baglandi-eksik")
    # `izin-tam` zaten "sekmeyi kapatıp dön" diyor — ikinci kez yazılmaz.
    return _donus_sayfasi(baslik, govde, "iyi" if tam else "uyari", kapat=not tam)


_GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"


@router.post("/google/disconnect")
@limiter.limit("30/minute")
async def google_disconnect(request: Request):
    """Bağlantıyı kes — önce Google'da izni geri al, sonra bu bilgisayardan sil.

    `iptal`: Google izni gerçekten geri aldı mı. Alamadıysa (ağ yok, token zaten
    ölü) panel kullanıcıya hesabından kendisinin kaldırabileceği yeri söyler —
    "kesildi" demek, Google tarafında hâlâ duran bir izni saklamak olurdu.
    """
    tok = _tok_deposu.google_al()
    iptal = False
    jeton = (tok or {}).get("refresh_token") or (tok or {}).get("access_token")
    if jeton:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(_GOOGLE_REVOKE_URL, data={"token": jeton})
            iptal = r.status_code == 200
        except httpx.HTTPError as e:
            logger.info("Google izni geri alınamadı (ağ): %s", e)
    _tok_deposu.google_yaz(None)
    return {"ok": True, "iptal": iptal, "vardi": bool(tok)}


@router.get("/google/disconnect")
@limiter.limit("30/minute")
async def google_disconnect_eski(request: Request):
    """Geriye uyum (eski panel/PLAN sürümleri). Yan etkili GET — yeni kod POST kullanır;
    burası Google'da izni geri almaz, yalnız yerel oturumu siler (eski davranış)."""
    _tok_deposu.google_yaz(None)
    return {"ok": True}


class GoogleKimlikBody(BaseModel):
    """Kullanıcının KENDİ Google Cloud projesinden aldığı masaüstü istemci bilgisi."""
    client_id: str
    client_secret: str


#: Google masaüstü istemci kimliğinin değişmez eki (kural `google_client`'ta — tek yer).
_CID_EKI = _gc._CID_EKI


def _kimlik_gecerli(cid: str, sec: str) -> bool:
    """'Kimlik girilmiş mi' sorusunun TEK cevabı.

    🔴 **Neden sadece boşluk denetimi YETMEZ (ölçüldü 2026-09-14):** geliştirme
    `.env`'inde `GOOGLE_CLIENT_ID` **9 karakterlik bir yer tutucuyla** doluydu.
    "Boş değil → kimlik var" mantığı bunu geçerli sayıyordu: panel *"Kayıtlı ✓"*
    diyor, kullanıcı **Bağlan**'a basıyor ve Google `invalid_client` döndürüyor —
    kullanıcı ne olduğunu anlamıyor, üstelik panel ona *"kimliğin tamam"* demişti.
    📏 Ürünün kendi dersi: *ilan edilen yetenek ≠ ölçülen yetenek.*

    ⚠️ Denetim **gevşek**: yalnız ek aranır. Google eki değiştirirse geçerli bir
    kimliği reddeden sessiz bir duvar kurmuş oluruz — asıl kapı canlı denemedir.

    Gövde `google_client.kimlik_gecerli`'de: `/api/planner/status` ve yedekleme de
    aynı kuralı okusun (2026-09-28'e kadar ikisi "boş değil = var" diyordu).
    """
    return _gc.kimlik_gecerli(cid, sec)


def _kimlik_maskele(deger: str) -> str:
    """Anahtarı ekrana basmadan 'girilmiş mi' sorusunu cevaplar.

    Google kimliğinde sabit eki (`.apps.googleusercontent.com`) göster: "123456….com"
    kullanıcıya hiçbir şey söylemiyordu (panel 11, 2026-09-28) — ek, doğru alanın
    yapıştırıldığının görünür kanıtıdır; başındaki proje numarası kısaltılır.
    """
    if not deger:
        return ""
    if len(deger) <= 10:
        return "•" * len(deger)
    if deger.endswith(_CID_EKI) and len(deger) > len(_CID_EKI) + 6:
        return f"{deger[:6]}…{_CID_EKI}"
    return f"{deger[:6]}…{deger[-4:]}"


@router.post("/google/kimlik")
@limiter.limit("10/minute")
async def google_kimlik_kaydet(request: Request, body: GoogleKimlikBody):
    """Google istemci kimliğini kaydet — kök `.env`'e + çalışan sürece.

    🔑 **Karar (2026-09-14): kimlik KULLANICINİNDİR.** Ürünle birlikte bizim
    `client_id`/`client_secret`'ımız dağıtılmaz; kullanıcı kendi Google Cloud
    projesini açar.

    ⚠️ `.env` yazımı **BYOK anahtar ucuyla aynı deseni** kullanır
    (`llm_config_api._persist_env`): atomik (temp + `os.replace`) ve yorum
    satırlarına dokunmaz. Kendi yazıcını yazma — yarım yazma `.env`'i bozar ve
    kullanıcının LLM anahtarı da aynı dosyadadır.
    """
    cid = body.client_id.strip()
    sec = body.client_secret.strip()
    if not cid or not sec:
        raise HTTPException(400, M("planlayici.kimlik-bos"))

    # Google masaüstü istemcisinin kimliği daima bu ekle biter. Biçim denetimi
    # ⚠️ yalnız BURADA meşru: yanlış alanın yapıştırıldığını (ör. API anahtarı ya
    # da proje numarası) kullanıcı Google'ın ekranında ANLAYAMAZ, geri döner ve
    # "çalışmıyor" der. Ama denetim gevşek tutulur — Google eki değiştirirse
    # geçerli bir kimliği reddeden sessiz bir duvar kurmuş oluruz.
    if not _kimlik_gecerli(cid, sec):
        raise HTTPException(
            400,
            M("planlayici.kimlik-bicimsiz", ek=_CID_EKI),
        )

    # Kimlik DEĞİŞİYORSA eski bağlantı yeni kimlikle yenilenemez. Token silinmez
    # (kullanıcı vazgeçip eskisini geri girebilir) ama eski kimliğe İĞNELENİR:
    # durum ucu iz uyuşmazlığından "kopuk — kimlik değişti" der, Google'a sormadan.
    eski_cid = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    tok = _tok_deposu.google_al()
    if tok and not tok.get("kimlik_izi") and eski_cid != cid:
        tok["kimlik_izi"] = _gc.kimlik_izi(eski_cid)
        _tok_deposu.google_yaz(tok)

    from app.api.llm_config_api import _persist_env
    try:
        _persist_env("GOOGLE_CLIENT_ID", cid)
        _persist_env("GOOGLE_CLIENT_SECRET", sec)
    except Exception as e:
        # Kaynak etiketi zorunlu (`tests/test_hata_kaynagi_gorunur.py`): kullanıcı
        # ekran görüntüsü paylaştığında hatanın nereden geldiği okunabilsin.
        raise HTTPException(500, M("planlayici.env-yazilamadi", sebep=e))

    # Çalışan sürece de uygula — yoksa kullanıcı kaydeder, "bağlan"a basar ve
    # 503 alır; restart istemek bu akışta kabul edilemez (BYOK dersinin aynısı:
    # anahtar girildikten sonra yeniden başlatma gerektiren akış terk edilir).
    os.environ["GOOGLE_CLIENT_ID"] = cid
    os.environ["GOOGLE_CLIENT_SECRET"] = sec
    return {"ok": True, "client_id": _kimlik_maskele(cid), "ayni_kimlik": bool(eski_cid) and eski_cid == cid}


def _durum_govdesi() -> dict:
    """`/google/status` ile `/google/dene`'nin ORTAK cevabı — iki yüzey aynı soruya
    ayrı cevap üretmesin (`surum.js` dersi)."""
    # ⚠️ Diskten okunur, modül global'inden DEĞİL: yedekleme zamanlayıcısı da
    # token yeniliyor (ikinci yazar) → global bayatlar ve durum ucu yalan söyler.
    tok = _tok_deposu.google_al() or {}
    verilen = (tok.get("scope") or "").split()
    gereken = _GOOGLE_SCOPES.split()
    cid = os.getenv("GOOGLE_CLIENT_ID", "")
    sec = os.getenv("GOOGLE_CLIENT_SECRET", "")
    d = _gc.durum()
    return {
        # Geriye uyum: "token dosyası var mı". Bağlantının SAĞLIĞI değildir —
        # onu `durum` söyler (yalan yeşil: dosya durur, izin aylar önce gitmiş olabilir).
        "connected": bool(tok),
        # yok · hazir · denenmedi · bagli · kopuk — panelin ışığı buradan.
        "durum": d["durum"],
        # kopuksa neden: invalid_grant · invalid_client · unauthorized_client ·
        # kimlik-degisti · kimlik-gecersiz
        "sebep": d["sebep"],
        # {ok, zaman, sebep} — yalnız GERÇEKTEN yapılmış bir yenileme/bağlanma.
        "son_deneme": d["son_deneme"],
        # ⚠️ Biçim de denetlenir — yer tutucu/çöp değer "kimlik var" SAYILMAZ.
        # Gerekçe `_kimlik_gecerli`'de; kaydetme ucuyla aynı kuralı paylaşır ki
        # "girilebilen ama geçerli sayılmayan" bir değer doğmasın.
        "kimlik_var": _kimlik_gecerli(cid, sec),
        # Dolu ama geçersizse kullanıcı SEBEBİNİ görmeli: panel "Kayıtlı ✓" der,
        # Google `invalid_client` verir ve kimse ikisini birbirine bağlayamaz.
        "kimlik_bicimsiz": bool(cid) and not _kimlik_gecerli(cid, sec),
        "client_id": _kimlik_maskele(cid),
        # Scope 2026-09-14'te değişti: eski token'lar Drive'ı kapsamaz. Bunu
        # söylemezsek kullanıcı "bağlıyım" görür, Drive işi sessizce 403 alır.
        "eksik_izin": [s for s in gereken if tok and s not in verilen],
    }


@router.get("/google/status")
@limiter.limit("30/minute")
async def google_status(request: Request):
    """Bağlantı durumu — 'bağlı mı' ile 'kimlik girilmiş mi' AYRI sorulardır.

    İkisini tek bayrakta birleştirmek, kimliğini girmemiş kullanıcıya *"bağlı
    değilsin"* der ve onu bağlan düğmesine (dolayısıyla 503'e) yollar. Arayüz
    hangi adımda olduğunu bu alanlardan bilir. Google'a GİTMEZ — son denemeyi okur.
    """
    return _durum_govdesi()


#: Aynı anda gelen ikinci "dene" Google'a ikinci istek atmaz; ilkinin sonucunu bekler.
_dene_kilidi = asyncio.Lock()


@router.post("/google/dene")
@limiter.limit("20/minute")
async def google_dene(request: Request):
    """Bağlantıyı GERÇEKTEN dene: refresh token ile erişim tokenini yenile.

    Google'a tek küçük istek (token ucu) — takvim/Drive verisine dokunmaz. Sonuç ve
    zamanı token'ın yanına yazılır (`google_client.yenile`), cevap `/status` ile aynıdır.
    `gecici: true` → Google'a ulaşılamadı; bu bağlantının kopuk olduğu anlamına GELMEZ,
    kayıt değişmez.
    """
    if _dene_kilidi.locked():
        async with _dene_kilidi:
            pass
        return {**_durum_govdesi(), "denendi": False, "gecici": False}
    async with _dene_kilidi:
        tok = _tok_deposu.google_al()
        d = _gc.durum()
        denendi = gecici = False
        # Kimlik yoksa/değiştiyse sonuç bellidir — Google'a boşuna sorulmaz.
        if tok and d["sebep"] not in ("kimlik-degisti", "kimlik-gecersiz"):
            denendi = True
            try:
                await _gc.yenile(tok)
            except _gc.GoogleYetkiDustu:
                pass
            except (httpx.HTTPError, RuntimeError) as e:
                logger.warning("Google bağlantı denemesi: ulaşılamadı (%s)", e)
                gecici = True
        return {**_durum_govdesi(), "denendi": denendi, "gecici": gecici}


@router.get("/google/events")
@limiter.limit("30/minute")
async def google_events(request: Request, days: int = 14, baslangic: str | None = None):
    """Takvim etkinlikleri. `baslangic` verilirse oradan `days` gün (ay panosu geçmiş
    günleri de gösterir); verilmezse eski davranış: şu andan itibaren.

    🔑 `baslangic` İSTEMCİNİN yerel gece yarısıdır, saat dilimiyle birlikte
    (`2026-08-31T00:00:00+03:00` ya da `…Z`). Kişisel AliceAi aynı ucu sabit UTC+3
    ile yorumluyordu — ürünün kullanıcısı başka dilimde olabilir. Yalnız tarih
    (`2026-08-31`) gelirse UTC gece yarısı sayılır.
    """
    days = max(1, min(int(days), 120))
    if baslangic:
        try:
            now = datetime.fromisoformat(baslangic.strip().replace(" ", "+"))
        except ValueError:
            raise HTTPException(400, M("planlayici.baslangic-gecersiz"))
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
    else:
        now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days)).isoformat()
    r = await _takvim_istegi("GET", _GOOGLE_EVENTS_URL, params={
        "timeMin": time_min,
        "timeMax": time_max,
        "singleEvents": "true",
        "orderBy": "startTime",
        # Ay panosu ~42 gün ister; her gün tekrar eden TEK etkinlik 50'yi yalnız başına dolduruyordu.
        "maxResults": 250,
    })
    items = r.json().get("items", [])
    events = []
    for it in items:
        start = it.get("start", {})
        end = it.get("end", {})
        events.append({
            "id": it.get("id"),
            "title": it.get("summary", M("planlayici.basliksiz")),
            "start": start.get("dateTime") or start.get("date"),
            "end": end.get("dateTime") or end.get("date"),
            "all_day": "date" in start and "dateTime" not in start,
            "color": it.get("colorId"),
            "location": it.get("location"),
            "description": it.get("description", "")[:200],
            "html_link": it.get("htmlLink"),
        })
    return {"events": events}


class GoogleEventCreate(BaseModel):
    title: str
    start: str          # ISO datetime or date
    end: str
    all_day: bool = False
    description: str = ""
    # IANA saat dilimi (tarayıcının `Intl…timeZone`'u). Yoksa eski sabit — geriye uyum.
    saat_dilimi: str | None = None


@router.post("/google/events")
@limiter.limit("30/minute")
async def google_create_event(request: Request, body: GoogleEventCreate):

    if body.all_day:
        start_val = {"date": body.start[:10]}
        end_val = {"date": body.end[:10]}
    else:
        # 🔴 Eskiden SABİT "Europe/Istanbul": başka dilimdeki kullanıcının "19:00 spor"u
        # İstanbul'un 19:00'una yazılıyordu. İstemci kendi dilimini gönderir; geçersizse 400.
        dilim = "Europe/Istanbul"
        if body.saat_dilimi:
            try:
                from zoneinfo import ZoneInfo
                ZoneInfo(body.saat_dilimi)
            except Exception:
                raise HTTPException(400, M("planlayici.saat-dilimi-gecersiz"))
            dilim = body.saat_dilimi
        start_val = {"dateTime": body.start, "timeZone": dilim}
        end_val = {"dateTime": body.end, "timeZone": dilim}
    payload = {
        "summary": body.title,
        "description": body.description,
        "start": start_val,
        "end": end_val,
    }
    r = await _takvim_istegi("POST", _GOOGLE_EVENTS_URL, json=payload)
    return r.json()



# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
@limiter.limit("100/minute")
async def planner_status(request: Request):

    # `/google/status` ile AYNI kural: yer tutucu kimlik "yapılandırılmış" sayılmaz.
    return {
        "google": bool(_tok_deposu.google_al()),
        "google_client_configured": _gc.kimlik_var(),
    }

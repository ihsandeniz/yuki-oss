"""Google **erişiminin** tek kaynağı — token yenileme + Drive çağrıları.

🔴 **Neden bu modül var ( FAZ 4):** `google_token_store` token'ın *nerede
durduğunu* tekilleştirdi, ama *nasıl kullanıldığını* etmedi. Ölçüldü 2026-09-14:
erişim tokeni üreten **iki** ayrı kod vardı —

| Nerede | Davranışı |
|---|---|
| `api/planner.py::_google_token` | yoksa `HTTPException(401)` atar |
| `services/tools/calendar.py::_get_access_token` | yoksa **boş string** döner |

İkisi de aynı işi yapıyor, aynı uç noktaya gidiyor, **yenileme hatasını farklı
yutuyordu**. Drive üçüncüsünü yazsaydı bu bir desen olurdu. `surum.js` dersinin
üçüncü tekrarı: *aynı soruya iki yerde cevap üretilirse er geç ayrışırlar ve
ayrıştıkları yere kimse bakmaz.*

🔑 **İkinci kusur burada kapandı: BAYAT GLOBAL.** `planner.py` token'ları modül
seviyesinde bir global'e (`_tokens`) yükleyip oradan okuyordu. Tek süreç/tek
yazar varken zararsızdı; yedekleme **zamanlayıcıdan** token yenileyince ikinci
yazar doğuyor ve global bayatlıyor — yani kullanıcı bağlıyken *"bağlı değilsin"*
görülebiliyordu. Bu modül **her çağrıda diskten okur**; tek yazar kuralı yerine
tek okuyucu kuralı konmuştur.

⚠️ **`invalid_grant` sessiz geçilmez.** Google, OAuth izin ekranı `Testing`
durumundayken refresh token'ı **7 günde** iptal eder (rehberin kırmızı kutusu:
`frontend/docs/google-kurulum.html` § 4). O gün her çağrı çöker ve sebebi hiçbir
yerde yazmaz. Burada hata **ne yapılacağını söyleyen** bir metne çevrilir —
ElevenLabs *"401 = kota"* dersinin aynısı: yanlış teşhis, kullanıcıyı yanlış
çözüme yollar.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.mesajlar import M
from app.services import google_token_store as _depo

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_DRIVE_DOSYA_URL = "https://www.googleapis.com/drive/v3/files"
_DRIVE_YUKLE_URL = "https://www.googleapis.com/upload/drive/v3/files"

#: Yenilemeye kaç saniye kala tetiklenir. 60 sn: bir isteğin tamamlanması için
#: fazlasıyla yeterli, ama her çağrıda gereksiz yenileme yaptıracak kadar geniş değil.
_YENILEME_PAYI = 60


class GoogleBagliDegil(Exception):
    """Hiç token yok — kullanıcı henüz bağlanmamış."""


class GoogleYetkiDustu(Exception):
    """Token vardı ama Google reddetti (iptal / süresi geçmiş izin).

    Metin **kullanıcıya gider**; teknik sebep değil yapılacak iş yazılır.
    """


#: 🌐 Metin değil ANAHTAR saklanır: modül düzeyinde üretilen metin açılıştaki
#: dilde donar. Metin `M()` ile yükseltme ANINDA üretilir.
_YETKI_ANAHTARI = "google.yetki-dustu"

#: `invalid_grant` ile KARIŞTIRILMAZ — çözümleri zıt. Orada oturum düşmüştür
#: (yeniden bağlan), burada **istemci kimliği** geçersizdir: Google Cloud'daki
#: istemci silinmiş, yanlış kopyalanmış ya da başka projeden gelmiştir. Yeniden
#: bağlanmak hiçbir şeyi düzeltmez; kimliğin kendisi değişmelidir.
_KIMLIK_ANAHTARI = "google.kimlik-gecersiz"


def __getattr__(ad: str) -> str:
    """Geriye uyum: `_YETKI_METNI` / `_KIMLIK_METNI` eskiden sabit metindi ve
    testler hâlâ okuyor. Artık okunduğu anda aktif dilde üretilir (PEP 562)."""
    if ad == "_YETKI_METNI":
        return M(_YETKI_ANAHTARI)
    if ad == "_KIMLIK_METNI":
        return M(_KIMLIK_ANAHTARI)
    raise AttributeError(ad)


# ── Token ────────────────────────────────────────────────────────────────────

def token_var() -> bool:
    return bool(_depo.google_al())


#: Google masaüstü istemci kimliğinin değişmez eki.
_CID_EKI = ".apps.googleusercontent.com"


def kimlik_gecerli(cid: str, sec: str) -> bool:
    """'Kimlik girilmiş mi' sorusunun TEK cevabı (gerekçe: `api/planner.py::_kimlik_gecerli`).

    Burada yaşar ki yedekleme (`kimlik_var`), `/api/planner/status` ve `/google/status`
    aynı kuralı paylaşsın — eskiden yedekleme ve `/status` "boş değil = var" diyordu
    ve geliştirme `.env`'indeki 9 karakterlik yer tutucuyu **kayıtlı** sayıyordu.
    """
    return bool(cid and sec and cid.strip().endswith(_CID_EKI))


def kimlik_var() -> bool:
    """İstemci kimliği (client_id/secret) girilmiş mi — *bağlı mı* ile AYRI soru."""
    return kimlik_gecerli(os.getenv("GOOGLE_CLIENT_ID", ""), os.getenv("GOOGLE_CLIENT_SECRET", ""))


def kimlik_izi(cid: str | None = None) -> str:
    """İstemci kimliğinin kısa parmak izi — token'ın HANGİ kimlikle alındığını tutar.

    Sır değildir (client_id gizli değil), ama token dosyasına düz yazılmasına da
    gerek yok. Kimlik `Değiştir` ile değişince eski refresh token yeni kimlikle
    yenilenemez (Google `unauthorized_client`/`invalid_grant` der) — panel bunu
    Google'a sormadan, iz uyuşmazlığından bilir.
    """
    cid = (os.getenv("GOOGLE_CLIENT_ID", "") if cid is None else cid).strip()
    return hashlib.sha256(cid.encode("utf-8")).hexdigest()[:12] if cid else ""


# ── Son deneme — "bağlı" yalnız DENENMİŞ bağlantıya denir ───────────────────
#
# 🔴 **Yalan yeşil ( panel 11, 2026-09-28):** panel `connected = bool(token)`
# ile "Bağlı" diyordu. Token dosyası, Google izni aylar önce kaldırmış olsa bile
# diskte durur — yani yeşil ışık bir DOSYANIN varlığını ölçüyordu, bağlantıyı değil.
# Artık her yenileme (kendiliğinden ya da panelin "Şimdi dene"si) sonucunu ve
# zamanını token'ın yanına yazar; durum bu kayıttan okunur.

#: Google'ın "bu bağlantı artık geçmez" dediği üç cevap. Ağ/5xx bunlardan DEĞİLDİR —
#: geçici arıza kullanıcıyı yeniden bağlanmaya yollamamalı.
_KOPUK_HATALARI = ("invalid_client", "unauthorized_client", "invalid_grant")


def _google_hatasi(r: httpx.Response) -> str:
    """Google token ucunun `error` alanı. Gövde JSON değilse düz metinde aranır."""
    govde = r.text or ""
    try:
        import json
        hata = json.loads(govde).get("error")
        if isinstance(hata, str):
            return hata
    except Exception:  # noqa: BLE001
        pass
    for h in _KOPUK_HATALARI:
        if h in govde:
            return h
    return ""


def deneme_kaydet(tok: dict[str, Any], ok: bool, sebep: str | None = None) -> dict[str, Any]:
    tok["deneme"] = {"ok": bool(ok), "zaman": datetime.now(timezone.utc).isoformat(), "sebep": sebep}
    _depo.google_yaz(tok)
    return tok


def durum() -> dict[str, Any]:
    """Bağlantının tek cümlelik hâli: yok · hazir · denenmedi · bagli · kopuk.

    `kopuk` token'ı SİLMEZ: kullanıcı sebebi (hangi hesap, ne zaman) görebilmeli ve
    `invalid_client` gibi kimlik kaynaklı düşüşte kimliği düzeltince aynı bağlantı
    geri gelir. Yalnız "bağlı" denmez.
    """
    tok = _depo.google_al()
    cid = os.getenv("GOOGLE_CLIENT_ID", "")
    kimlik = kimlik_gecerli(cid, os.getenv("GOOGLE_CLIENT_SECRET", ""))
    if not tok:
        return {"durum": "hazir" if kimlik else "yok", "sebep": None, "son_deneme": None}
    son = tok.get("deneme") if isinstance(tok.get("deneme"), dict) else None
    if not kimlik:
        return {"durum": "kopuk", "sebep": "kimlik-gecersiz", "son_deneme": son}
    iz = tok.get("kimlik_izi")
    if iz and iz != kimlik_izi(cid):
        return {"durum": "kopuk", "sebep": "kimlik-degisti", "son_deneme": son}
    if son and son.get("ok") is False:
        return {"durum": "kopuk", "sebep": son.get("sebep") or "invalid_grant", "son_deneme": son}
    if son and son.get("ok"):
        return {"durum": "bagli", "sebep": None, "son_deneme": son}
    return {"durum": "denenmedi", "sebep": None, "son_deneme": None}


def kopuk_metni(sebep: str | None) -> str:
    """Kopukluğun kullanıcı cümlesi — çözümü sebebe göre: kimlik mi, yeniden bağlanmak mı."""
    if sebep in ("invalid_client", "kimlik-gecersiz"):
        return M(_KIMLIK_ANAHTARI)
    if sebep == "unauthorized_client":
        return M("google.istemci-yetkisiz")
    if sebep == "kimlik-degisti":
        return M("google.kimlik-degisti")
    return M(_YETKI_ANAHTARI)


async def yenile(tok: dict[str, Any]) -> dict[str, Any]:
    """Refresh token ile erişim tokenini tazele ve **diske yaz**.

    Yazmadan dönmek, aynı tokeni her çağrıda yeniden yenilemek demektir; Google'ın
    refresh uç noktasının da kotası var. Sonuç (başarı ya da Google'ın reddi) token'ın
    yanına `deneme` olarak yazılır — panelin "son deneme" satırı buradan okur.
    """
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(_TOKEN_URL, data={
            "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
            "refresh_token": tok.get("refresh_token", ""),
            "grant_type": "refresh_token",
        })
    if not r.is_success:
        # Diğer hatalar geçici olabilir (ağ, 5xx) — onlarda kayda DOKUNMA, yoksa
        # geçici bir arıza kullanıcıya "koptu" dedirtir.
        govde = (r.text or "")[:200]
        hata = _google_hatasi(r)
        if hata not in _KOPUK_HATALARI and r.status_code == 400:
            hata = "invalid_grant"          # eksik/bozuk refresh token da yenilenemez
        if hata in _KOPUK_HATALARI:
            # 🔴 Token SİLİNMEZ (2026-09-28; `invalid_client` için 09-14'ten beri):
            #   · `invalid_client` 401 ile gelir ve sorun KİMLİKTEDİR — token silinirse
            #     kullanıcı boşuna yeniden bağlanır, kimlik yanlış olduğu için yine düşer.
            #   · `invalid_grant` eskiden token'ı siliyordu → panel "bağlı değil" deyip
            #     kurulum adımlarını gösteriyordu; kullanıcı neyin, ne zaman koptuğunu
            #     göremiyordu. Artık "kopuk" + sebep; yeniden bağlanınca yenisi yazılır.
            # Kayıt DİSKTEKİ token'a yazılır, parametreye değil: çağıran eksik bir
            # sözlük geçmiş olabilir (yalnız refresh_token) ve onu yazmak oturumu bozardı.
            mevcut = _depo.google_al()
            if mevcut:
                deneme_kaydet(mevcut, False, hata)
            logger.warning("Google refresh reddedildi (%s): %s", hata, govde)
            raise GoogleYetkiDustu(kopuk_metni(hata))
        raise RuntimeError(M("google.token-yenilenemedi", kod=r.status_code, govde=govde))

    yeni = r.json()
    tok["access_token"] = yeni["access_token"]
    tok["expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=yeni.get("expires_in", 3600))
    ).isoformat()
    # Google refresh yanıtında `scope` döndürebilir; döndüyse SAKLA — "eksik izin"
    # uyarısı buna bakıyor ve yenileme onu silerse uyarı yanlış susar.
    if yeni.get("scope"):
        tok["scope"] = yeni["scope"]
    # Başarılı yenileme, token'ın BU kimliğe ait olduğunun kanıtıdır.
    tok["kimlik_izi"] = kimlik_izi()
    return deneme_kaydet(tok, True)


async def erisim_tokeni() -> str:
    """Geçerli bir erişim tokeni — gerekirse yenileyerek. **Diskten okur.**

    Kopuk bilinen bağlantı Google'a yeniden SORULMAZ: yedekleme zamanlayıcısı ve
    sohbet her çağrıda reddedilen bir yenilemeyi tekrarlamasın. Yeniden deneme
    yolu açıktır: panelin "Şimdi dene"si (`/google/dene`) ya da yeniden bağlanmak.
    """
    tok = _depo.google_al()
    if not tok:
        raise GoogleBagliDegil(M("google.bagli-degil"))
    d = durum()
    if d["durum"] == "kopuk":
        raise GoogleYetkiDustu(kopuk_metni(d["sebep"]))
    exp = tok.get("expires_at")
    if exp:
        try:
            expires = datetime.fromisoformat(exp)
        except ValueError:
            expires = None
        if expires and datetime.now(timezone.utc) >= expires - timedelta(seconds=_YENILEME_PAYI):
            tok = await yenile(tok)
    at = tok.get("access_token", "")
    if not at:
        raise GoogleBagliDegil(M("google.bagli-degil"))
    return at


async def _baslik() -> dict[str, str]:
    return {"Authorization": f"Bearer {await erisim_tokeni()}"}


class DriveHatasi(RuntimeError):
    """Drive'ın geçici/ kalıcı reddi. `RuntimeError` kalır (eski çağıranlar bozulmaz).

    `tur` panelin hangi cümleyi seçeceğini söyler (`dolu` · `api-kapali` · `reddetti` ·
    `hata`); `teknik` Google'ın ham gövdesidir — kullanıcı cümlesine KARIŞMAZ, yalnız
    "Teknik ayrıntı" katlanırında görünür.
    """

    def __init__(self, mesaj: str, tur: str, teknik: str = ""):
        super().__init__(mesaj)
        self.tur = tur
        self.teknik = teknik


def _drive_hatasi(r: httpx.Response) -> None:
    """Drive yanıtını ortak dile çevir. 401/403'ü sessiz geçirmek yasak."""
    if r.is_success:
        return
    if r.status_code == 401:
        raise GoogleYetkiDustu(M(_YETKI_ANAHTARI))
    if r.status_code == 403:
        govde = (r.text or "")[:300]
        # İki farklı 403 var ve çözümleri ZIT: kota dolması beklemeyi, izin eksiği
        # yeniden bağlanmayı gerektirir. Tek mesaj yazmak birini yanlış yere yollar.
        if "storageQuotaExceeded" in govde:
            raise DriveHatasi(M("google.drive-dolu"), "dolu", govde)
        if "insufficientFilePermissions" in govde or "insufficientPermissions" in govde:
            raise GoogleYetkiDustu(M("google.drive-izin-yok"))
        # Drive API'si kullanıcının Cloud projesinde açılmamış (rehberin 2. adımı atlanmış).
        if "accessNotConfigured" in govde or "SERVICE_DISABLED" in govde:
            raise DriveHatasi(M("google.drive-api-kapali"), "api-kapali", govde)
        raise DriveHatasi(M("google.drive-reddetti", govde=govde), "reddetti", govde)
    # 404: saklı kimlik ölü (kullanıcı dosyayı/klasörü Drive'da sildi). Ayrı etiket, çünkü
    # çağıran bunu ONARABİLİR (kimliği bırakıp yeniden oluşturur); "hata" diye geçerse
    # yedek her gün aynı ölü kimliğe çarpar ve kendiliğinden hiç düzelmez.
    tur = "bulunamadi" if r.status_code == 404 else "hata"
    raise DriveHatasi(M("google.drive-hatasi", kod=r.status_code, govde=(r.text or "")[:300]),
                      tur, (r.text or "")[:300])


# ── Drive ────────────────────────────────────────────────────────────────────
#
# ⚠️ Scope `drive.file` — uygulama YALNIZ kendi oluşturduğu dosyaları görür.
# Sonucu ikidir: ① kullanıcının Drive'ının geri kalanı bize kapalıdır (satış vaadi
# bu) ② kullanıcı bizim oluşturduğumuz klasörü Drive'da elle silerse onu ARAYAMAYIZ
# bile — `_klasor_ara` boş döner ve yenisi oluşturulur. Bu bir kusur değil, scope'un
# kendisidir; durum dosyası bu yüzden klasör kimliğini saklar ama ona **güvenmez**.

async def _klasor_ara(ad: str, ebeveyn_id: str | None) -> str | None:
    q = [
        "mimeType='application/vnd.google-apps.folder'",
        "trashed=false",
        f"name='{ad.replace(chr(39), chr(92) + chr(39))}'",
        f"'{ebeveyn_id or 'root'}' in parents",
    ]
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(_DRIVE_DOSYA_URL, headers=await _baslik(), params={
            "q": " and ".join(q), "fields": "files(id,name)", "pageSize": 10,
        })
    _drive_hatasi(r)
    dosyalar = r.json().get("files", [])
    return dosyalar[0]["id"] if dosyalar else None


async def klasor_al_veya_olustur(ad: str, ebeveyn_id: str | None = None) -> str:
    mevcut = await _klasor_ara(ad, ebeveyn_id)
    if mevcut:
        return mevcut
    govde: dict[str, Any] = {"name": ad, "mimeType": "application/vnd.google-apps.folder"}
    if ebeveyn_id:
        govde["parents"] = [ebeveyn_id]
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(_DRIVE_DOSYA_URL, headers=await _baslik(), json=govde,
                         params={"fields": "id"})
    _drive_hatasi(r)
    return r.json()["id"]


async def klasor_gecerli_mi(dosya_id: str) -> bool:
    """Durum dosyasındaki klasör kimliği hâlâ yaşıyor mu (silinmiş/çöpte değil)."""
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{_DRIVE_DOSYA_URL}/{dosya_id}", headers=await _baslik(),
                        params={"fields": "id,trashed"})
    if r.status_code == 404:
        return False
    if r.status_code == 401:
        raise GoogleYetkiDustu(M(_YETKI_ANAHTARI))
    if not r.is_success:
        return False
    return not r.json().get("trashed", False)


async def dosya_yukle(yerel_yol, ad: str, ebeveyn_id: str, dosya_id: str | None = None) -> dict:
    """Tek dosyayı yükle (yeni) ya da içeriğini güncelle (`dosya_id` verilmişse).

    🔑 **Güncelleme ayrı bir yoldur (PATCH + `uploadType=media`).** Aynı adla
    yeniden POST etmek Drive'da **ikinci bir dosya** yaratır — Drive dosyaları
    adla değil kimlikle ayırır. Ayna mantığı bunu bilmezse her turda kopya üretir
    ve kullanıcının alanı sessizce dolar.
    """
    veri = open(yerel_yol, "rb")
    try:
        baslik = await _baslik()
        async with httpx.AsyncClient(timeout=None) as c:
            if dosya_id:
                r = await c.patch(
                    f"{_DRIVE_YUKLE_URL}/{dosya_id}", headers=baslik,
                    params={"uploadType": "media", "fields": "id,name,size,md5Checksum"},
                    content=veri.read(),
                )
            else:
                # multipart: üstveri (ad + ebeveyn) ile içerik tek istekte gider.
                r = await c.post(
                    _DRIVE_YUKLE_URL, headers=baslik,
                    params={"uploadType": "multipart", "fields": "id,name,size,md5Checksum"},
                    files={
                        "metadata": (None, _json_metin({"name": ad, "parents": [ebeveyn_id]}),
                                     "application/json; charset=UTF-8"),
                        "file": (ad, veri.read(), "application/octet-stream"),
                    },
                )
        _drive_hatasi(r)
        return r.json()
    finally:
        veri.close()


def _json_metin(d: dict) -> str:
    import json
    return json.dumps(d, ensure_ascii=False)


async def kullanim() -> dict:
    """Drive alanı — 'dolu' hatasını YAŞAMADAN önce söyleyebilmek için."""
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get("https://www.googleapis.com/drive/v3/about",
                        headers=await _baslik(), params={"fields": "storageQuota"})
    _drive_hatasi(r)
    kota = r.json().get("storageQuota", {})
    return {
        "limit": int(kota["limit"]) if kota.get("limit") else None,
        "kullanilan": int(kota.get("usage", 0)),
    }

"""SIWC kimlik katmanı — kayıt, kod değişimi, doğrulama, yerel kayıt, yenileme, çıkış.

Belge: OpenAI "Sign in with ChatGPT" açık kaynak token paylaşımı belgeleri
(developers.openai.com/siwc/token-sharing-open-source). Bu dosya belgedeki akışın kendi
yazımıdır; OpenAI'nin ticari olmayan lisanslı DevKit kodundan kopya içermez.

🔴 Kurallar (her biri testle korunur — `tests/test_chatgpt_plan.py`):
  · İlk kayıt `client_id=dynamic_agent_client` + `agent_name_hint=Yuki` + `ext_agent_host_id`.
    `dynamic_agent_client` ASLA kaydedilen kimlik değildir; dönen `oaiapp_…` saklanır.
  · Yeniden girişte kayıtlı client_id kullanılır, `agent_name_hint` GÖNDERİLMEZ.
  · ID token imzası JWKS'ten, iss/aud/exp/nonce kontrolüyle doğrulanır.
  · Plan kullanımı yalnız dönen kapsamda `chatgpt.tokens.use.direct` varsa açık.
  · Dosyalar atomik, 0600 (dizin 0700); token log'a, istisna metnine girmez.
  · Yenileme kayıtlı client_id + resource ile, scope'suz; dönen yeni refresh token saklanır;
    aynı anda iki süreç yenilemesin diye flock.

Token dosyası `chatgpt_token.json` (0600) veri dizinindedir; `.gitignore` ve temizlik kapısı
tarafından depoya girmesi engellenir.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

try:  # yalnız POSIX; Windows'ta süreç içi kilit yeter
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Sabitler (belgeden)
# ------------------------------------------------------------------ #

AGENT_ADI = "Yuki"                       # her kurulumda AYNI — kimlik değil, görünen ad
DINAMIK_ISTEMCI = "dynamic_agent_client"  # yalnız ilk kayıt girişi
KIMLIK_KAPSAMLARI = ("openid", "profile", "email")
PLAN_KAPSAMLARI = ("offline_access", "resource.invoke", "chatgpt.tokens.use.direct")
PLAN_KAPSAMI = "chatgpt.tokens.use.direct"
GERI_DONUS_YOLU = "/auth/callback"       # `/callback` eşleşmez
VARSAYILAN_PORT = 1455
TAZELEME_PAYI_SN = 300
VARSAYILAN_DIZIN = str(DATA_DIR / "chatgpt_plan")

# Yenilemede "bu refresh token öldü, yeniden giriş" diyen kodlar (errors-and-recovery § Refresh).
OLU_REFRESH_KODLARI = frozenset({
    "invalid_grant", "invalid_refresh_token", "token_expired",
    "refresh_token_expired", "refresh_token_invalidated", "refresh_token_reused",
})


def auth_taban() -> str:
    """Kimlik sunucusu. `YUKI_CHATGPT_AUTH_TABAN` yalnız sahte sunucu testi içindir."""
    return os.getenv("YUKI_CHATGPT_AUTH_TABAN", "https://auth.openai.com").rstrip("/")


def api_taban() -> str:
    """Çıkarım ucu = `resource` değeri. Test dışında `https://api.openai.com/v1`."""
    return os.getenv("YUKI_CHATGPT_API_TABAN", "https://api.openai.com/v1").rstrip("/")


def yetki_ucu() -> str:
    return f"{auth_taban()}/api/accounts/authorize"


def token_ucu() -> str:
    return f"{auth_taban()}/api/accounts/oauth/token"


def iptal_ucu() -> str:
    return f"{auth_taban()}/api/accounts/oauth/revoke"


def jwks_ucu() -> str:
    return f"{auth_taban()}/.well-known/jwks.json"


def dizin() -> Path:
    return Path(os.getenv("YUKI_CHATGPT_DIZIN", VARSAYILAN_DIZIN)).expanduser()


def kimlik_dosyasi() -> Path:
    return dizin() / "chatgpt_token.json"


def host_dosyasi() -> Path:
    return dizin() / "chatgpt_host.json"


# ------------------------------------------------------------------ #
# Hatalar
# ------------------------------------------------------------------ #


class PlanKimlikHatasi(Exception):
    """SIWC kimlik katmanının ata hatası."""


class PlanGirisYok(PlanKimlikHatasi):
    """Hiç giriş yok. Çözüm: "Continue with ChatGPT" ile giriş."""


class PlanGirisGerekli(PlanKimlikHatasi):
    """Refresh token öldü / kimlik tutmadı — yeniden giriş."""


class PlanKullanimiKapali(PlanKimlikHatasi):
    """Giriş var ama `chatgpt.tokens.use.direct` verilmemiş: çıkarım YAPILMAZ."""


class PlanGeciciHata(PlanKimlikHatasi):
    """Ağ / 5xx / 429 — kimlik SAĞLAM, silinmez; sonra tekrar denenir."""


class GeriDonusHatasi(PlanKimlikHatasi):
    """Tarayıcı dönüşü reddedildi (state, error, client_id uyuşmazlığı)."""


# ------------------------------------------------------------------ #
# Disk — atomik, 0600
# ------------------------------------------------------------------ #


def _atomik_yaz(yol: Path, veri: dict[str, Any]) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(yol.parent, 0o700)
    gecici = yol.with_name(f".{yol.name}.{os.getpid()}.tmp")
    fd = os.open(gecici, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(veri, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(gecici, 0o600)
        os.replace(gecici, yol)
    finally:
        if gecici.exists():
            gecici.unlink()
    os.chmod(yol, 0o600)


def host_kimligi() -> str:
    """Bu kurulumun kalıcı `ext_agent_host_id`'si — ilk girişten ÖNCE üretilir, sonra hep aynı."""
    yol = host_dosyasi()
    if yol.exists():
        try:
            deger = str(json.loads(yol.read_text(encoding="utf-8")).get("ext_agent_host_id") or "")
            if deger:
                return deger
        except Exception:
            logger.warning("chatgpt_plan: chatgpt_host.json okunamadı, yeniden üretilecek")
    deger = f"urn:uuid:{uuid.uuid4()}"
    _atomik_yaz(yol, {"ext_agent_host_id": deger})
    return deger


@dataclass
class Kayit:
    """Tek ChatGPT hesabı kaydı (kişisel kurulum: tek profil)."""

    client_id: str = ""
    ext_agent_host_id: str = ""
    issuer: str = ""
    subject: str = ""
    email: str = ""
    id_token: str = ""
    access_token: str = ""
    refresh_token: str = ""
    token_type: str = "Bearer"
    expires_in: int = 0
    expires_at: int = 0
    scopes: list[str] = field(default_factory=list)
    saved_at: str = ""

    @property
    def plan_acik(self) -> bool:
        return bool(self.access_token) and PLAN_KAPSAMI in self.scopes

    def sozluk(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    def __repr__(self) -> str:  # token'lar repr'e/log'a sızmasın
        return (f"Kayit(client_id={self.client_id[:10]!r}…, plan_acik={self.plan_acik}, "
                f"expires_at={self.expires_at})")


def oku() -> Kayit | None:
    yol = kimlik_dosyasi()
    if not yol.exists():
        return None
    try:
        ham = json.loads(yol.read_text(encoding="utf-8"))
    except Exception as e:
        raise PlanGirisGerekli(f"chatgpt_plan kimlik dosyası okunamadı ({type(e).__name__})") from None
    alanlar = Kayit.__dataclass_fields__
    return Kayit(**{k: v for k, v in ham.items() if k in alanlar})


def kaydet(kayit: Kayit) -> None:
    if kayit.client_id == DINAMIK_ISTEMCI:
        # Belge: "Do not save dynamic_agent_client as the connection's issued ID."
        raise PlanKimlikHatasi("dynamic_agent_client kayıtlı kimlik olarak saklanamaz")
    _atomik_yaz(kimlik_dosyasi(), kayit.sozluk())


def _zaman_damgasi() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ------------------------------------------------------------------ #
# Yetki isteği
# ------------------------------------------------------------------ #


@dataclass
class Deneme:
    """Tek yetki denemesinin geçici sırları — yalnız bellekte."""

    state: str
    nonce: str
    dogrulayici: str
    redirect_uri: str
    client_id: str           # dynamic_agent_client (yeni) ya da kayıtlı oaiapp_…
    yeni_kayit: bool
    host_id: str

    @property
    def meydan(self) -> str:
        ozet = hashlib.sha256(self.dogrulayici.encode("ascii")).digest()
        return base64.urlsafe_b64encode(ozet).rstrip(b"=").decode("ascii")


def deneme_baslat(redirect_uri: str, mevcut: Kayit | None = None) -> Deneme:
    yeni = not (mevcut and mevcut.client_id)
    return Deneme(
        state=secrets.token_urlsafe(32),
        nonce=secrets.token_urlsafe(32),
        dogrulayici=secrets.token_urlsafe(64),
        redirect_uri=redirect_uri,
        client_id=DINAMIK_ISTEMCI if yeni else mevcut.client_id,  # type: ignore[union-attr]
        yeni_kayit=yeni,
        host_id=host_kimligi(),
    )


def yetki_url(deneme: Deneme, mevcut: Kayit | None = None) -> str:
    """Sistem tarayıcısında açılacak URL. 🔴 id_token_hint taşıyabilir — LOG'A YAZMA."""
    p: dict[str, str] = {
        "client_id": deneme.client_id,
        "ext_agent_host_id": deneme.host_id,
        "response_type": "code",
        "redirect_uri": deneme.redirect_uri,
        "scope": " ".join(KIMLIK_KAPSAMLARI + PLAN_KAPSAMLARI),
        "resource": api_taban(),
        "state": deneme.state,
        "nonce": deneme.nonce,
        "code_challenge_method": "S256",
        "code_challenge": deneme.meydan,
    }
    if deneme.yeni_kayit:
        p["agent_name_hint"] = AGENT_ADI
    elif mevcut is not None:
        if mevcut.id_token:
            p["id_token_hint"] = mevcut.id_token
        if mevcut.email:
            p["login_hint"] = mevcut.email
    return f"{yetki_ucu()}?{urlencode(p)}"


def geri_donus_dogrula(deneme: Deneme, sorgu: dict[str, str]) -> str:
    """Dönüşü doğrula, değişimde kullanılacak client_id'yi döndür."""
    if not secrets.compare_digest(str(sorgu.get("state", "")), deneme.state):
        raise GeriDonusHatasi("state uyuşmuyor — dönüş reddedildi")
    if sorgu.get("error"):
        raise GeriDonusHatasi(f"yetki verilmedi: {sorgu.get('error')}")
    if not sorgu.get("code"):
        raise GeriDonusHatasi("dönüşte code yok")
    gelen = str(sorgu.get("client_id") or "")
    if deneme.yeni_kayit:
        if not gelen or gelen == DINAMIK_ISTEMCI:
            raise GeriDonusHatasi("yeni kayıt dönüşünde verilmiş client_id yok — kayıt tamamlanmadı")
        return gelen
    if gelen and gelen != deneme.client_id:
        raise GeriDonusHatasi("dönüşteki client_id kayıtlı hesapla uyuşmuyor — reddedildi")
    return deneme.client_id


# ------------------------------------------------------------------ #
# HTTP
# ------------------------------------------------------------------ #

_ISTEMCI_BASLIKLARI = {"Accept": "application/json", "User-Agent": "Yuki"}


def _form_post(url: str, veri: dict[str, str], zaman_asimi: float = 20.0) -> httpx.Response:
    try:
        with httpx.Client(timeout=zaman_asimi, headers=_ISTEMCI_BASLIKLARI) as c:
            return c.post(url, data=veri)
    except httpx.HTTPError as e:
        raise PlanGeciciHata(f"kimlik sunucusuna ulaşılamadı ({type(e).__name__})") from None


def _hata_kodu(r: httpx.Response) -> str:
    try:
        govde = r.json()
    except Exception:
        return ""
    if isinstance(govde, dict):
        hata = govde.get("error")
        if isinstance(hata, dict):
            return str(hata.get("code") or hata.get("type") or "")
        return str(hata or "")
    return ""


# ------------------------------------------------------------------ #
# ID token
# ------------------------------------------------------------------ #

JwksAnahtarBulucu = Callable[[str], Any]


def _varsayilan_anahtar_bulucu(id_token: str) -> Any:
    import jwt

    return jwt.PyJWKClient(jwks_ucu(), timeout=5).get_signing_key_from_jwt(id_token).key


def id_token_dogrula(
    id_token: str,
    client_id: str,
    nonce: str,
    anahtar_bulucu: JwksAnahtarBulucu | None = None,
) -> dict[str, Any]:
    """İmza (JWKS, RS256) + iss + aud(client_id) + exp + nonce. Döner: iddialar."""
    import jwt

    if not id_token:
        raise PlanGirisGerekli("token cevabında id_token yok")
    try:
        anahtar = (anahtar_bulucu or _varsayilan_anahtar_bulucu)(id_token)
        iddia = jwt.decode(
            id_token,
            anahtar,
            algorithms=["RS256"],
            audience=client_id,
            issuer=auth_taban(),
            leeway=60,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except Exception as e:
        raise PlanGirisGerekli(f"ID token doğrulanamadı ({type(e).__name__})") from None
    if not secrets.compare_digest(str(iddia.get("nonce", "")), nonce):
        raise PlanGirisGerekli("ID token nonce uyuşmuyor")
    return iddia


# ------------------------------------------------------------------ #
# Kod değişimi
# ------------------------------------------------------------------ #


def kod_degistir(
    deneme: Deneme,
    sorgu: dict[str, str],
    mevcut: Kayit | None = None,
    anahtar_bulucu: JwksAnahtarBulucu | None = None,
) -> Kayit:
    """Dönüşü doğrula → (yeni kayıtta önce client_id'yi sakla) → kod değiş → doğrula → kaydet."""
    client_id = geri_donus_dogrula(deneme, sorgu)

    if deneme.yeni_kayit:
        # Belge: kod süresi dolarsa sonraki deneme aynı client_id'yi kullanabilsin diye
        # kayıt, değişimden ÖNCE saklanır.
        kaydet(Kayit(client_id=client_id, ext_agent_host_id=deneme.host_id,
                     issuer=auth_taban(), saved_at=_zaman_damgasi()))

    r = _form_post(token_ucu(), {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": str(sorgu["code"]),
        "code_verifier": deneme.dogrulayici,
        "redirect_uri": deneme.redirect_uri,
        "resource": api_taban(),
    })
    if r.status_code != 200:
        kod = _hata_kodu(r)
        raise PlanGirisGerekli(f"kod değişimi başarısız (HTTP {r.status_code} {kod})".strip())
    veri = r.json()

    iddia = id_token_dogrula(str(veri.get("id_token") or ""), client_id, deneme.nonce, anahtar_bulucu)
    if mevcut is not None and mevcut.subject and iddia.get("sub") != mevcut.subject:
        raise GeriDonusHatasi("dönen hesap kayıtlı hesapla aynı değil — kimlik değiştirilmedi")

    kayit = _token_cevabindan(veri, Kayit(
        client_id=client_id,
        ext_agent_host_id=deneme.host_id,
        issuer=auth_taban(),
        subject=str(iddia.get("sub") or ""),
        email=str(iddia.get("email") or ""),
        id_token=str(veri.get("id_token") or ""),
    ))
    kaydet(kayit)
    logger.info("chatgpt_plan: giriş tamam (plan kullanımı %s)", "AÇIK" if kayit.plan_acik else "KAPALI")
    return kayit


def _token_cevabindan(veri: dict[str, Any], taban: Kayit) -> Kayit:
    at = str(veri.get("access_token") or "").strip()
    if not at:
        raise PlanGirisGerekli("token cevabında access_token yok")
    rt = str(veri.get("refresh_token") or "").strip() or taban.refresh_token
    try:
        sure = int(veri.get("expires_in") or 3600)
    except (TypeError, ValueError):
        sure = 3600
    kapsam = veri.get("scope")
    kapsamlar = sorted(str(kapsam).split()) if kapsam is not None else list(taban.scopes)
    taban.access_token = at
    taban.refresh_token = rt
    taban.token_type = str(veri.get("token_type") or "Bearer")
    taban.expires_in = sure
    taban.expires_at = int(time.time()) + sure
    taban.scopes = kapsamlar
    taban.saved_at = _zaman_damgasi()
    return taban


# ------------------------------------------------------------------ #
# Yenileme
# ------------------------------------------------------------------ #


def _tokenlari_temizle(kayit: Kayit, id_token_da: bool = False) -> Kayit:
    """Token'ları sil; client_id + hesap + host eşlemesi KALIR (sonraki giriş aynı kaydı kullanır)."""
    kayit.access_token = ""
    kayit.refresh_token = ""
    kayit.expires_at = 0
    kayit.scopes = []
    if id_token_da:
        kayit.id_token = ""
    return kayit


def tazele(kayit: Kayit) -> Kayit:
    if not kayit.refresh_token:
        raise PlanGirisGerekli("refresh token yok — yeniden giriş")
    r = _form_post(token_ucu(), {
        "grant_type": "refresh_token",
        "client_id": kayit.client_id,       # kayıtlı oaiapp_…, ASLA dynamic_agent_client
        "refresh_token": kayit.refresh_token,
        "resource": api_taban(),
        # scope YOK — belge: "omit scope to retain the grant"
    })
    if r.status_code == 200:
        yeni = _token_cevabindan(r.json(), kayit)
        kaydet(yeni)
        logger.info("chatgpt_plan: token yenilendi")
        return yeni

    kod = _hata_kodu(r)
    if r.status_code == 429 or r.status_code >= 500:
        raise PlanGeciciHata(f"yenileme geçici olarak başarısız (HTTP {r.status_code})")
    if kod in OLU_REFRESH_KODLARI:
        kaydet(_tokenlari_temizle(kayit))
        raise PlanGirisGerekli(f"refresh token kullanılamaz ({kod}) — yeniden giriş gerekli")
    if kod == "invalid_client":
        raise PlanGirisGerekli("invalid_client — istemci yapılandırması bozuk")
    raise PlanGirisGerekli(f"yenileme başarısız (HTTP {r.status_code} {kod})".strip())


def suresi_doluyor(kayit: Kayit, payi_sn: int = TAZELEME_PAYI_SN) -> bool:
    return not kayit.expires_at or time.time() >= kayit.expires_at - payi_sn


def gecerli_kimlik(zorla_tazele: bool = False) -> Kayit:
    """Çıkarıma hazır kayıt; gerekirse yeniler. Aynı oturumun yenilemesi flock ile sıralanır."""
    kayit = oku()
    if kayit is None or not kayit.client_id:
        raise PlanGirisYok("ChatGPT girişi yok — 'Continue with ChatGPT' ile giriş yap")
    if not kayit.access_token and not kayit.refresh_token:
        raise PlanGirisGerekli("ChatGPT (resmî yol) oturumu kapalı — yeniden giriş")
    if not zorla_tazele and not suresi_doluyor(kayit):
        return _plan_kapisi(kayit)

    kilit = dizin() / "chatgpt_token.lock"
    kilit.parent.mkdir(parents=True, exist_ok=True)
    with open(kilit, "w") as fh:
        if fcntl:
            fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            kayit = oku() or kayit
            if not zorla_tazele and not suresi_doluyor(kayit):
                return _plan_kapisi(kayit)
            return _plan_kapisi(tazele(kayit))
        finally:
            if fcntl:
                fcntl.flock(fh, fcntl.LOCK_UN)


def _plan_kapisi(kayit: Kayit) -> Kayit:
    if PLAN_KAPSAMI not in kayit.scopes:
        raise PlanKullanimiKapali(
            "ChatGPT plan kullanımı verilmemiş (chatgpt.tokens.use.direct yok) — çıkarım yapılmaz"
        )
    return kayit


# ------------------------------------------------------------------ #
# Çıkış
# ------------------------------------------------------------------ #


def cikis(deneme_sayisi: int = 3, bekleme_sn: float = 1.0) -> dict[str, Any]:
    """Refresh token'ı iptal et, sonra yerel token'ları sil. client_id + host KALIR."""
    kayit = oku()
    if kayit is None:
        return {"cikis": True, "uzak_iptal": None}
    onay = False
    if kayit.refresh_token:
        for i in range(deneme_sayisi):
            try:
                r = _form_post(iptal_ucu(), {
                    "token": kayit.refresh_token,
                    "token_type_hint": "refresh_token",
                    "client_id": kayit.client_id,
                })
            except PlanGeciciHata:
                r = None
            if r is not None and r.status_code == 200:
                onay = True
                break
            if r is not None and r.status_code < 500:
                break
            time.sleep(bekleme_sn * (2 ** i))
    kaydet(_tokenlari_temizle(kayit, id_token_da=True))
    if not onay:
        logger.warning("chatgpt_plan: uzak iptal doğrulanamadı — ChatGPT Ayarlar'dan bağlantıyı kes")
    return {"cikis": True, "uzak_iptal": onay}


# ------------------------------------------------------------------ #
# Durum — istisna fırlatmaz, sır döndürmez
# ------------------------------------------------------------------ #


def durum() -> dict[str, Any]:
    try:
        kayit = oku()
    except PlanKimlikHatasi as e:
        return {"yol": "resmi", "giris": False, "sebep": type(e).__name__}
    if kayit is None or not kayit.client_id:
        return {"yol": "resmi", "giris": False, "sebep": "PlanGirisYok"}
    return {
        "yol": "resmi",
        "giris": bool(kayit.access_token or kayit.refresh_token),
        "plan_acik": kayit.plan_acik,
        "client_id": kayit.client_id[:10] + "…",
        "son_kullanma": time.strftime("%Y-%m-%d %H:%M", time.localtime(kayit.expires_at))
        if kayit.expires_at else None,
    }

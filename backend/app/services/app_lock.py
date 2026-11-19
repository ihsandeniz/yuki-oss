"""Uygulama kilidi — açılışta parola (ve/veya yüz).

🔴 **NEDEN VAR (geliştirici kararı, 2026-09-06):** aynı bilgisayarı paylaşan başka
kişilerin Yuki'yi açıp sohbet geçmişini okumasını, notlara ve araçlara
erişmesini engellemek. Kullanıcı Ayarlar → Güvenlik'ten kendisi kurar; kurmazsa
hiçbir şey değişmez (varsayılan KAPALI).

## `AUTH_TOKEN`'dan farkı — ikisi karıştırılmamalı

| | `AUTH_TOKEN` | uygulama kilidi |
|---|---|---|
| kime karşı | **uzaktan** erişim (cloudflared tüneli) | **aynı makinedeki** başka kişi |
| nerede durur | `.env` — kullanıcı arayüzünden değiştirilemez | Ayarlar'dan kurulur |
| nasıl saklanır | **düz metin**, parolanın kendisi token olur | **hash**, parola hiç saklanmaz |
| istemcide | parolanın kendisi `sessionStorage`'da | yalnız kısa ömürlü **oturum** token'ı |

İkisi birlikte yaşar: middleware ikisinden **birini** kabul eder. `AUTH_TOKEN`
kuruluyken tünelden gelen istek onu kullanır; yerel kullanıcı kilidi açtığında
oturum token'ı alır.

## Parola hash'i — SECURITY.md'den bilinçli sapma

`SCHEMA/SECURITY.md` § 4 *"parolalar bcrypt (min cost 12) veya argon2"* diyor.
Burada **`hashlib.scrypt`** kullanıldı. Gerekçe ölçülü, tercih değil:

- `bcrypt` de `argon2` de pakette **YOK** (`backend/pybundle/lib/.../site-packages`
  tarandı, 2026-09-06). Eklemek `requirements-product.txt` + `pybundle-kilit.txt`
  değiştirir → **`shell_id` döner** → delta güncelleme kapanır ve mevcut her
  kullanıcı **375 MB'ı yeniden indirir**. Bir parola alanı için bu bedel yanlış.
- `scrypt` stdlib'dedir (OpenSSL üzerinden), **memory-hard** sınıftadır — bu
  sınıfta bcrypt'in üstünde durur; bcrypt yalnız CPU-hard'dır.

Parametreler `n=2**14, r=8, p=1` → yaklaşık **16 MiB** bellek / doğrulama.
Masaüstünde tek kullanıcı için seçildi: daha yükseği (`2**17`, 128 MiB) zayıf
makinelerde açılışı hissedilir yavaşlatırdı, daha düşüğü GPU'ya alan açardı.

## Ne YAPMAZ — dürüstlük sınırı

Bu kilit **veriyi şifrelemez.** Makinede dosya sistemine erişebilen biri
`~/.config/Yuki/` altındaki sohbet geçmişini, notları ve `.env`'i doğrudan
okuyabilir. Kilit **uygulamanın kapısıdır**, diskin değil. "Şifreliyorum" diye
anlatmak, ürünün kendi kurallarında yasak olan ölçülmemiş iddia olur.

Oturum token'ları **yalnız bellekte** durur: uygulama kapanınca hepsi gider ve
kilit yeniden sorulur. Bu bilinçli — diske yazılan bir "beni hatırla" kaydı,
kilidi ilk açılıştan sonra kalıcı olarak devre dışı bırakırdı.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import tempfile
import time
from threading import Lock

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

KILIT_DOSYASI = DATA_DIR / "app_lock.json"

# scrypt parametreleri — dosyaya da yazılır (bkz. `_dogrula`), böylece ileride
# artırılabilir ve ESKİ hash'ler kendi parametreleriyle doğrulanmaya devam eder.
_N = 2 ** 14
_R = 8
_P = 1
_TUZ_BAYT = 16
_ANAHTAR_BAYT = 32

# Oturum ömrü. Uygulama kapanınca zaten sıfırlanır; bu üst sınır, açık bırakılmış
# bir uygulamanın sonsuza dek açık kalmasını engeller.
OTURUM_SANIYE = 12 * 3600

# Parola uzunluk sınırları. Alt sınır zayıf parolayı, üst sınır scrypt'e
# devasa girdi verip CPU'yu meşgul etmeyi (ucuz bir DoS) engeller.
MIN_UZUNLUK = 4
MAX_UZUNLUK = 256

_LOCK = Lock()
_oturumlar: dict[str, float] = {}   # token → son geçerlilik damgası


# ══════════════════════════════════════════════════════════════════════════
#  Parola kaydı
# ══════════════════════════════════════════════════════════════════════════

def _oku() -> dict | None:
    """Kilit kaydını oku. Yoksa/bozuksa None → kilit KURULU DEĞİL sayılır.

    ⚠️ Bozuk dosyada `None` dönmek kapıyı açar. Bilinçli: alternatif, kullanıcıyı
    kendi uygulamasından kalıcı olarak kilitlemekti. Bozulma diske özgü bir
    arızadır, saldırı yüzeyi değil — saldırgan dosyayı bozabiliyorsa zaten
    silebilir de.
    """
    try:
        if not KILIT_DOSYASI.exists():
            return None
        with open(KILIT_DOSYASI, encoding="utf-8") as f:
            kayit = json.load(f)
        if not kayit.get("hash") or not kayit.get("tuz"):
            return None
        return kayit
    except (json.JSONDecodeError, OSError, ValueError) as e:
        logger.warning("app_lock kaydı okunamadı (%s): %s", type(e).__name__, e)
        return None


def _yaz(kayit: dict | None) -> None:
    """Kaydı atomik yaz (`os.replace`) ya da sil.

    Atomiklik login_guard'daki dersin aynısı: doğrudan üzerine yazmak, yazma
    sırasında kesilen bir işlemde dosyayı yarım bırakır ve `_oku()` bozuk
    dosyada `None` döndüğü için **kilit sessizce açılır**.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if kayit is None:
        try:
            KILIT_DOSYASI.unlink()
        except FileNotFoundError:
            pass
        return
    fd, gecici = tempfile.mkstemp(dir=str(DATA_DIR), prefix=".app_lock-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(kayit, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(gecici, KILIT_DOSYASI)
        # Parola hash'i — sahibinden başkası okumasın.
        try:
            os.chmod(KILIT_DOSYASI, 0o600)
        except OSError:
            pass   # Windows/NTFS'te anlamsız; hata değil
    except BaseException:
        try:
            os.unlink(gecici)
        except OSError:
            pass
        raise


def _turet(parola: str, tuz: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(parola.encode("utf-8"), salt=tuz, n=n, r=r, p=p,
                          dklen=_ANAHTAR_BAYT, maxmem=n * r * 256)


def kurulu() -> bool:
    """Kullanıcı bir parola belirlemiş mi?"""
    return _oku() is not None


def parola_kur(parola: str) -> None:
    """Parolayı hash'leyip kaydet. Uzunluk kapısı çağıranın değil, buranın işi."""
    if not isinstance(parola, str) or not (MIN_UZUNLUK <= len(parola) <= MAX_UZUNLUK):
        # Mesaj `lock_api`'de `str(e)` ile 422'nin gövdesine geçiyor, yani
        # KULLANICIYA gider — bu yüzden katalogdan okunuyor. İçe aktarma
        # fonksiyonun içinde: `app_lock` kilit zincirinin en alt katmanı.
        from app.mesajlar import M

        raise ValueError(M("kilit.uzunluk", min=MIN_UZUNLUK, max=MAX_UZUNLUK))
    tuz = secrets.token_bytes(_TUZ_BAYT)
    _yaz({
        "surum": 1,
        "kdf": "scrypt",
        "n": _N, "r": _R, "p": _P,
        "tuz": tuz.hex(),
        "hash": _turet(parola, tuz, _N, _R, _P).hex(),
        "olusturuldu": int(time.time()),
    })


def parola_kaldir() -> None:
    """Kilidi kaldır ve **tüm açık oturumları düşür.**

    Oturumların düşmesi şart: kilit kaldırılıp yeniden kurulduğunda eski
    token'ın geçerli kalması, yeni parolayı bilmeyen birine açık kapı bırakırdı.
    """
    _yaz(None)
    with _LOCK:
        _oturumlar.clear()


def parola_dogrula(parola: str) -> bool:
    """Parola doğru mu? Kilit kurulu değilse **False** (kapı yoksa açılmaz da)."""
    kayit = _oku()
    if kayit is None or not isinstance(parola, str):
        return False
    if len(parola) > MAX_UZUNLUK:
        return False   # scrypt'e devasa girdi vermeden reddet
    try:
        beklenen = bytes.fromhex(kayit["hash"])
        tuz = bytes.fromhex(kayit["tuz"])
        hesap = _turet(parola, tuz,
                       int(kayit.get("n", _N)),
                       int(kayit.get("r", _R)),
                       int(kayit.get("p", _P)))
    except (ValueError, KeyError, TypeError) as e:
        logger.warning("app_lock hash'i çözülemedi: %s", e)
        return False
    return secrets.compare_digest(hesap, beklenen)


# ══════════════════════════════════════════════════════════════════════════
#  Oturumlar
# ══════════════════════════════════════════════════════════════════════════

def _temizle(simdi: float) -> None:
    """Süresi dolmuş token'ları at. `_LOCK` tutulurken çağrılır."""
    for t in [t for t, bitis in _oturumlar.items() if bitis <= simdi]:
        _oturumlar.pop(t, None)


def oturum_ac() -> str:
    """Yeni oturum token'ı üret. Çağıran, doğrulamayı ZATEN yapmış olmalıdır."""
    token = secrets.token_urlsafe(32)
    simdi = time.time()
    with _LOCK:
        _temizle(simdi)
        _oturumlar[token] = simdi + OTURUM_SANIYE
    return token


def oturum_gecerli(token: str) -> bool:
    """Token canlı mı? Sabit zamanlı karşılaştırma ile.

    🔑 Sözlükte `token in _oturumlar` demek yeterli görünür ama sözlük araması
    anahtarı bayt bayt kıyaslar ve erken çıkar; ölçülebilir bir zaman farkı
    bırakır. Token 32 baytlık rastgele bir değer olduğu için pratikte bunu
    sömürmek zordur — yine de karşılaştırma `compare_digest` ile yapılır,
    çünkü "zor" ile "imkânsız" arasındaki farkı ölçmedik.
    """
    if not token or not isinstance(token, str):
        return False
    simdi = time.time()
    with _LOCK:
        _temizle(simdi)
        for aday, bitis in _oturumlar.items():
            if secrets.compare_digest(aday, token) and bitis > simdi:
                return True
    return False


def oturum_kapat(token: str) -> None:
    """Tek oturumu düşür (kullanıcı 'kilitle' dediğinde)."""
    with _LOCK:
        _oturumlar.pop(token, None)


def tum_oturumlari_kapat() -> None:
    with _LOCK:
        _oturumlar.clear()


def durum() -> dict:
    """Kilit durumu — **parola hakkında hiçbir şey sızdırmaz.**"""
    with _LOCK:
        acik_oturum = len(_oturumlar)
    return {
        "kurulu": kurulu(),
        "acik_oturum": acik_oturum,
        "oturum_saniye": OTURUM_SANIYE,
        "min_uzunluk": MIN_UZUNLUK,
        "max_uzunluk": MAX_UZUNLUK,
    }

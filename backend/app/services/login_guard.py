"""Giriş deneme kilidi — karşılıklı yol kapatma.

Kişisel Alice'ten taşındı ( Dalga 2 FAZ 4). Fikir: iki giriş yolu var
(parola · yüz). Biri üst üste N kez başarısız olursa **yalnız o yol** geçici
kapanır, diğeri açık kalır. Kullanıcı asla tamamen kilitlenmez ama otomatik
deneme spam'i durur.

    4 hatalı yüz taraması  → yüz yolu 10 dk kapalı, parola çalışır
    4 hatalı parola        → parola yolu 10 dk kapalı, yüz çalışır

⚠️ **Sınırı bilerek yazıyoruz:** bu **brute force**'u durdurur, fotoğrafla giriş
riskini DURDURMAZ — fotoğraf saldırısı ilk denemede başarılı olur, sayaç hiç
dolmaz. Fotoğraf yolunu kapatan şey `face_liveness.py`'dir, bu dosya değil.
Kişiselde canlılık yoktu ve bu satırın karşılığı orada açık bir borçtu.

📦 Üründeki iki fark:
  1. Veri yolu `app.config.DATA_DIR`'den gelir (kişiselde `parents[3]` sabitiydi;
     ürün paketlenince o yol paketin içini gösterir ve **salt-okunurdur**).
  2. Yazma atomik (`os.replace`) — doğrudan üzerine yazmak, yazma sırasında
     kesilen bir işlemde dosyayı yarım bırakır ve aşağıdaki "bozuk dosyada
     sıfırdan başla" yolu **kilidi sessizce açar**.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from threading import Lock

from app.config import DATA_DIR, LOGIN_LOCK_MINUTES, LOGIN_MAX_FAILS

logger = logging.getLogger(__name__)

PASSWORD = "password"
FACE = "face"

LOCK_STATE_FILE = DATA_DIR / "login_guard_state.json"

_LOCK = Lock()
_fails: dict[tuple[str, str], int] = {}
_until: dict[tuple[str, str], float] = {}


def _load_state() -> None:
    """Disk'ten kalıcı sayaçları yükle. Bozuk/eksik dosyada sıfırdan başla."""
    global _fails, _until
    try:
        if LOCK_STATE_FILE.exists():
            with open(LOCK_STATE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            # JSON tuple tutmaz → "yol|ip" biçiminde saklanır
            _fails = {tuple(k.split("|", 1)): v for k, v in data.get("fails", {}).items()}
            _until = {tuple(k.split("|", 1)): v for k, v in data.get("until", {}).items()}
        else:
            _fails, _until = {}, {}
    except (json.JSONDecodeError, OSError, KeyError, ValueError) as e:
        logger.warning("login_guard durumu okunamadı (%s), temiz başlanıyor: %s",
                       type(e).__name__, e)
        _fails, _until = {}, {}


def _save_state() -> None:
    """Durumu diske ATOMİK yaz. Çağıran `_LOCK`'u tutuyor olmalı."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        now = time.time()   # ⚠️ monotonic DEĞİL: kilit süreç yeniden başlasa da geçerli olmalı
        until_clean = {k: v for k, v in _until.items() if v > now}
        fails_clean = {k: v for k, v in _fails.items() if k in until_clean or k not in _until}

        govde = {
            "fails": {"|".join(k): v for k, v in fails_clean.items()},
            "until": {"|".join(k): v for k, v in until_clean.items()},
        }
        fd, gecici = tempfile.mkstemp(dir=str(DATA_DIR), prefix=".login-guard-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(govde, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(gecici, LOCK_STATE_FILE)
        except BaseException:
            try:
                os.unlink(gecici)
            except OSError:
                pass
            raise
    except OSError as e:
        logger.error("login_guard durumu diske yazılamadı: %s", e)


_load_state()


def _key(method: str, ip: str) -> tuple[str, str]:
    return (method, ip or "-")


def locked_for(method: str, ip: str) -> float:
    """Bu yol kilitliyse kalan saniye, değilse 0."""
    with _LOCK:
        t = _until.get(_key(method, ip))
        if not t:
            return 0.0
        left = t - time.time()
        if left <= 0:
            _until.pop(_key(method, ip), None)
            _fails.pop(_key(method, ip), None)
            return 0.0
        return left


def record_fail(method: str, ip: str) -> dict:
    """Başarısız denemeyi say. Sınır dolduysa yolu kilitler."""
    if LOGIN_MAX_FAILS <= 0:
        return {"locked": False, "remaining": None, "lock_seconds": 0.0}
    k = _key(method, ip)
    with _LOCK:
        n = _fails.get(k, 0) + 1
        _fails[k] = n
        if n >= LOGIN_MAX_FAILS:
            secs = max(1, int(LOGIN_LOCK_MINUTES * 60))
            _until[k] = time.time() + secs
            logger.warning("Giriş yolu kilitlendi: %s (ip=%s, %d başarısız, %d sn)",
                           method, ip, n, secs)
            sonuc = {"locked": True, "remaining": 0, "lock_seconds": float(secs)}
        else:
            sonuc = {"locked": False, "remaining": LOGIN_MAX_FAILS - n, "lock_seconds": 0.0}
        _save_state()
        return sonuc


def record_success(method: str, ip: str) -> None:
    k = _key(method, ip)
    with _LOCK:
        _fails.pop(k, None)
        _until.pop(k, None)
        _save_state()


def other(method: str) -> str:
    return FACE if method == PASSWORD else PASSWORD


def state(ip: str) -> dict:
    """Giriş ekranı için: hangi yol açık, kilit ne zaman bitiyor."""
    p, f = locked_for(PASSWORD, ip), locked_for(FACE, ip)
    with _LOCK:
        pf, ff = _fails.get(_key(PASSWORD, ip), 0), _fails.get(_key(FACE, ip), 0)
    return {
        "max_fails": LOGIN_MAX_FAILS,
        "lock_minutes": LOGIN_LOCK_MINUTES,
        "password": {"locked": p > 0, "seconds_left": int(p), "fails": pf,
                     "remaining": max(0, LOGIN_MAX_FAILS - pf) if LOGIN_MAX_FAILS > 0 else None},
        "face": {"locked": f > 0, "seconds_left": int(f), "fails": ff,
                 "remaining": max(0, LOGIN_MAX_FAILS - ff) if LOGIN_MAX_FAILS > 0 else None},
    }


def lock_message(method: str, seconds: float, other_available: bool) -> str:
    """Giriş yolu kapatıldığında kullanıcıya dönen cümle.

    🔴 2026-09-19 (Blok 6): cümle artık **kelime yerleştirerek** kurulmuyor.
    Eski hâl `f"{yol} girişi … {alt} girin."` idi ve yalnız Türkçe'de
    çalışıyordu — "yüzünüzle girin" ile "parolayla girin" farklı ek taşıyor,
    İngilizce'de ise alternatif ifadenin cümledeki yeri değişiyor. İki yol ×
    iki durum = dört ayrı anahtar; her dil kendi cümlesini bütün kuruyor.

    İçe aktarma fonksiyonun İÇİNDE: `login_guard` kilit ekranının en alt
    katmanı ve `app.mesajlar` → `app.config` zincirini modül yükleme anında
    çekmesi için bir sebep yok (config bu modülü import ettiği anda döngü
    riski doğardı).
    """
    from app.mesajlar import M

    dk = max(1, int(seconds / 60 + 0.5))
    yol = "parola" if method == PASSWORD else "yuz"
    durum = "alt-var" if other_available else "alt-yok"
    return M(f"giris-kilidi.{yol}-{durum}", dk=dk, kez=LOGIN_MAX_FAILS)


def _sifirla() -> None:
    """YALNIZ testler için — sayaçları ve kilitleri temizler."""
    with _LOCK:
        _fails.clear()
        _until.clear()
        _save_state()

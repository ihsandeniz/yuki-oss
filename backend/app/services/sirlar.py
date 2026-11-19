"""API anahtarları için işletim sistemi anahtarlığı (2026-10-10).

Neden: kullanıcının BYOK anahtarı (OpenRouter, Anthropic, … 14 bulut sağlayıcısı) diskte
düz metin `.env`'de duruyordu, izin ayarı da yoktu (umask). Yedek klasörüne, senkron
dizinine, yanlış zip'e giden her kopya anahtarı da götürüyordu.

Ne yapar:
- `yukle(env_path)` — `config.py` `.env`'i yükledikten hemen SONRA çağırır.
  ① `.env`'deki `*_API_KEY` satırları anahtarlığa taşınır (GÖÇ, bir kez): yazılır, GERİ
     OKUNUR, ancak değer birebir dönerse `.env`'den silinir. Geri okuma tutmazsa satır
     kalır — veri kaybı yok. ② Anahtarlıktaki anahtarlar `os.environ`'a konur; böylece
     `os.getenv` ile okuyan kodun (config, llm_providers, ambient …) hiçbiri değişmez.
- `kaydet(ad, deger)` — key sihirbazı yazarken. Anahtarlık yoksa False döner; çağıran
  `.env`'e yazar ve dosyayı 600 yapar.
- `durum()` — panelde "anahtarın nerede" bilgisi (anahtarlık / şifresiz dosya + sebep).

Neden Python `keyring` (Electron `safeStorage` değil): anahtarı yazan ve okuyan zaten
motor; `safeStorage` her anahtar değişiminde motordan Electron'a yeni bir kanal isterdi.
Linux'ta anahtarlık yokken `safeStorage` sabit parolalı `basic_text`'e düşer (Electron
belgesi: "unprotected") — yani korumasız olduğu hâlde korunuyor görünür. Burada o durumda
açıkça `.env` + 600 + uyarı var.

Sınırlar (vaat edilmez): anahtarlık aynı kullanıcıda çalışan başka programa karşı korumaz.
Kazanç: diskte düz metin anahtar kalmaz; yedeklere/zip'lere/başka kullanıcıya sızmaz.

🔴 Bu modül `llm_providers`'ı import ETMEZ: o modül import anında `os.getenv` ile anahtar
deposunu doldurur (`_env_yukle`). Burada import edilseydi anahtarlıktaki anahtarlar ortama
konmadan ÖNCE dolar, ürün "anahtar yok" diye açılırdı. Bilinen adlar bu yüzden aşağıda
ayrıca yazılı; `test_sirlar.py` kayıtla aynı olduğunu denetler.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from pathlib import Path

log = logging.getLogger(__name__)

SERVIS = "yuki-oss"
_DIZIN = "__adlar__"   # anahtarlıkta saklanan adların listesi (sır değil, yalnız adlar)
ZAMAN_ASIMI = 5.0      # sn — kilitli anahtarlık parola penceresi açıp beklerse motor takılmasın

# `llm_providers.SAGLAYICILAR`'daki bulut sağlayıcılarının env adları (yerel ollama hariç).
BILINEN = (
    "OPENROUTER_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    "GROQ_API_KEY", "CEREBRAS_API_KEY", "DEEPSEEK_API_KEY", "MISTRAL_API_KEY",
    "XAI_API_KEY", "TOGETHER_API_KEY", "FIREWORKS_API_KEY", "DEEPINFRA_API_KEY",
    "NEBIUS_API_KEY", "CHUTES_API_KEY",
)

_kilit = threading.RLock()
_kr = None             # seçilen keyring arka ucu (None = kullanılamıyor)
_profil = ""
_durum: dict = {"depo": "dosya", "arka_uc": None, "sebep": "henuz-yuklenmedi", "tasinan": 0}


def sir_mi(ad: str) -> bool:
    """Anahtarlığa giden ad mı? Sağlayıcı anahtarları + aynı kalıbı taşıyan her `*_API_KEY`."""
    return bool(ad) and (ad in BILINEN or ad.endswith("_API_KEY"))


def _kullanici(ad: str) -> str:
    # Profil önekli: geliştirme profili (yuki-urun-dev), kurulum (yuki-oss) ve testlerin
    # geçici dizinleri aynı işletim sistemi anahtarlığında birbirinin anahtarını görmesin.
    return f"{_profil}:{ad}"


def _zamanli(fn, *args):
    """Anahtarlık çağrısını süre sınırıyla koş. Kilitli koleksiyon parola penceresi açar ve
    kullanıcı cevap verene kadar bekler — motor açılışı bunun arkasında takılmamalı."""
    sonuc: dict = {}

    def _koş():
        try:
            sonuc["v"] = fn(*args)
        except BaseException as e:   # noqa: BLE001 — hatayı çağırana taşırız
            sonuc["e"] = e

    t = threading.Thread(target=_koş, daemon=True)
    t.start()
    t.join(ZAMAN_ASIMI)
    if t.is_alive():
        raise TimeoutError(f"anahtarlık {ZAMAN_ASIMI:.0f} sn'de cevap vermedi (kilitli olabilir)")
    if "e" in sonuc:
        raise sonuc["e"]
    return sonuc.get("v")


def _arka_uc_sec():
    """(arka_uç | None, sebep). Sebep arayüze ve log'a gider."""
    if os.getenv("YUKI_ANAHTARLIK", "1").strip().lower() in ("0", "hayir", "kapali", "false"):
        return None, "kapatildi"
    try:
        import keyring
        from keyring.backends import fail
    except Exception:   # paket yok (eski pybundle) → dosya yedeği
        return None, "paket-yok"
    try:
        kr = keyring.get_keyring()
    except Exception as e:
        return None, f"secilemedi: {type(e).__name__}"
    if isinstance(kr, fail.Keyring) or getattr(kr, "priority", 0) <= 0:
        return None, "anahtarlik-yok"
    return kr, None


def _dizin_oku() -> list[str]:
    v = _zamanli(_kr.get_password, SERVIS, _kullanici(_DIZIN)) or ""
    return [a for a in v.split(",") if a]


def _dizin_yaz(adlar) -> None:
    _zamanli(_kr.set_password, SERVIS, _kullanici(_DIZIN), ",".join(sorted(set(adlar))))


def _anahtarliga_yaz(ad: str, deger: str) -> bool:
    """Yaz + geri oku. True yalnız değer birebir döndüyse."""
    _zamanli(_kr.set_password, SERVIS, _kullanici(ad), deger)
    if _zamanli(_kr.get_password, SERVIS, _kullanici(ad)) != deger:
        return False
    _dizin_yaz(set(_dizin_oku()) | {ad})
    return True


def env_izin_kis(env_path: Path) -> None:
    """`.env`'i yalnız sahibi okuyabilsin (600). Windows'ta etkisiz, hata vermez."""
    try:
        if env_path.exists():
            os.chmod(env_path, 0o600)
    except OSError:
        pass


def env_satir_sil(env_path: Path, adlar) -> None:
    """`.env`'den `AD=` satırlarını sil (yorumlara dokunmaz). Atomik: tmp + os.replace."""
    adlar = set(adlar)
    if not adlar or not env_path.exists():
        return
    satirlar = env_path.read_text(encoding="utf-8").splitlines()
    kalan = [s for s in satirlar
             if s.lstrip().startswith("#") or s.split("=", 1)[0].strip() not in adlar]
    if len(kalan) == len(satirlar):
        return
    tmp = env_path.with_suffix(env_path.suffix + ".tmp")
    tmp.write_text("\n".join(kalan) + ("\n" if kalan else ""), encoding="utf-8")
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    os.replace(tmp, env_path)


def _env_sirlari(env_path: Path) -> dict[str, str]:
    """`.env`'deki dolu sır satırları. Değer python-dotenv ile aynı kuralla okunur."""
    if not env_path.exists():
        return {}
    from dotenv import dotenv_values
    return {k: (v or "").strip() for k, v in dotenv_values(env_path).items()
            if sir_mi(k) and (v or "").strip()}


def yukle(env_path: Path, veri_dizini: Path) -> dict:
    """Açılışta bir kez: göç + anahtarlıktan ortama yükleme. Hiçbir durumda istisna atmaz —
    anahtarlık sorunu ürünün açılmasını engellemez, yalnız dosya yedeğine düşer."""
    global _kr, _profil
    with _kilit:
        _profil = hashlib.sha256(str(Path(veri_dizini).resolve()).encode()).hexdigest()[:12]
        _kr, sebep = _arka_uc_sec()
        _durum.update(depo="dosya", arka_uc=None, sebep=sebep, tasinan=0)
        if _kr is None:
            env_izin_kis(env_path)
            if _env_sirlari(env_path):
                log.warning("API anahtarı şifresiz dosyada (%s): işletim sistemi anahtarlığı "
                            "kullanılamıyor (%s). Dosya izni 600.", env_path, sebep)
            return durum()
        _durum["arka_uc"] = f"{type(_kr).__module__}.{type(_kr).__name__}"
        try:
            # ① GÖÇ — yalnız geri okuması tutan satır silinir
            tasinan = []
            for ad, deger in _env_sirlari(env_path).items():
                if _anahtarliga_yaz(ad, deger):
                    tasinan.append(ad)
                else:
                    log.warning("%s anahtarlığa yazıldı ama geri okunamadı — .env'de bırakıldı", ad)
            env_satir_sil(env_path, tasinan)
            # ② YÜKLEME — gerçek ortam değişkeni (kullanıcının kendi export'u) önde kalır
            for ad in set(BILINEN) | set(_dizin_oku()):
                if (os.environ.get(ad) or "").strip() and ad not in tasinan:
                    continue
                v = _zamanli(_kr.get_password, SERVIS, _kullanici(ad))
                if v:
                    os.environ[ad] = v
            _durum.update(depo="anahtarlik", sebep=None, tasinan=len(tasinan))
            if tasinan:
                log.info("%d API anahtarı .env'den işletim sistemi anahtarlığına taşındı", len(tasinan))
        except Exception as e:   # kilitli/zaman aşımı/D-Bus koptu → dosya yedeği, ürün açılır
            log.warning("işletim sistemi anahtarlığı kullanılamadı (%s: %s) — .env yedeği",
                        type(e).__name__, str(e)[:160])
            _kr = None
            _durum.update(depo="dosya", arka_uc=None, sebep=f"hata: {type(e).__name__}")
            env_izin_kis(env_path)
        return durum()


def kaydet(ad: str, deger: str) -> bool:
    """Sırrı anahtarlığa yaz. False → anahtarlık yok/başarısız; çağıran `.env`'e yazar."""
    global _kr
    if not sir_mi(ad):
        return False
    with _kilit:
        if _kr is None:
            return False
        try:
            if _anahtarliga_yaz(ad, deger):
                return True
            log.warning("%s anahtarlığa yazıldı ama geri okunamadı — .env yedeği", ad)
        except Exception as e:
            log.warning("anahtarlığa yazılamadı (%s: %s) — .env yedeği", type(e).__name__, str(e)[:160])
            _kr = None
            _durum.update(depo="dosya", arka_uc=None, sebep=f"hata: {type(e).__name__}")
        return False


def durum() -> dict:
    return dict(_durum)

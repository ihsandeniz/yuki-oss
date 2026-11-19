"""Cihaz eşleştirme — QR ile tanıtılan cihazların TEK kimlik kaynağı.

🔴 **Neden var — ölçülmüş bir açık (2026-09-18):** `/ws/agent` kapısı şöyleydi:

    if AUTH_TOKEN and not secrets.compare_digest(_token, AUTH_TOKEN):

Üründe `AUTH_TOKEN` varsayılanı **boş** (`config.py`, `.env.example`) → `and`in sol
tarafı falsy, koşul kısa devre yapar, `ws.close()` **hiç çağrılmaz**. Canlı ölçüldü:
token verilmeden bağlanılıp sahte cihaz kaydedildi. Yani kapı vardı, çalışmıyordu.

📏 Ders: *"kapı yazılmış olması kapının çalıştığını göstermez"* — bir sırrın **boş
olabildiği** yerde `if SIR and ...` deseni kapıyı sessizce açar. Bu modülde sır asla
boş olamaz: yoksa doğrulama **reddeder** (fail-closed), atlamaz.

── Akış ────────────────────────────────────────────────────────────────────
1. Kullanıcı Yuki'de "Cihaz Ekle" der        → `kod_uret()` kısa ömürlü kod verir
2. Kod QR'a çevrilir (arayüz tarafında)      → içinde adres + kod var
3. Cihaz `ws://…/ws/agent?eslestirme=KOD`    → `kod_dogrula()` kodu TÜKETİR,
                                               kalıcı bir cihaz tokeni döndürür
4. Sonraki bağlantılar `?cihaz=TOKEN`        → `token_dogrula()`

**Kod tek kullanımlıktır ve 5 dakika yaşar** — QR ekranda kalsa, fotoğrafı çekilse
bile ikinci bir cihaz aynı kodla giremez.

**Token diske DÜZ yazılmaz.** Parola gibi davranılır: yalnız sha256'sı saklanır.
Dosya sızsa bile (yedeğe girse, Drive'a kopyalansa) içinden cihaz tokeni çıkmaz.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Kod ömrü. Kısa tutuluyor: QR ekranda açık kalırsa pencere de açık kalır.
KOD_OMRU_SN = 300

#: Kod uzunluğu. 8 × 32 alfabe ≈ 1,1e12 olasılık — kaba kuvvet için yeterince geniş,
#: elle girilebilecek kadar kısa (QR okunamazsa kullanıcı yazabilsin).
KOD_UZUNLUK = 8

#: Karışan karakterler ÇIKARILDI (0/O, 1/I/l) — kullanıcı kodu elle girebilmeli.
ALFABE = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

#: Bir kod için kabul edilen yanlış deneme sayısı. Aşılırsa kod yakılır —
#: yoksa 5 dakikalık pencere kaba kuvvete açık kalırdı.
MAX_DENEME = 5

#: Bellekte tutulan açık eşleştirme kodları. Bilerek KALICI DEĞİL: sunucu yeniden
#: başlayınca yarım kalmış eşleştirme geçersiz olmalı (kullanıcı ekranı da kapanmıştır).
_kodlar: dict[str, dict[str, Any]] = {}


def _veri_koku() -> Path:
    """Yazılabilir veri kökü.

    ⚠️ `Path(__file__)` ile paket dizinine yazma — satılan pakette (AppImage /
    `resources/`) orası **salt okunurdur** ve eşleştirme sessizce kaydedilemezdi.
    `google_token_store.py`'nin 2026-09-14 dersi.
    """
    ham = os.getenv("YUKI_DATA_DIR")
    if ham:
        return Path(ham)
    return Path(__file__).resolve().parents[2]


def cihaz_dosyasi() -> Path:
    return _veri_koku() / "cihazlar.json"


def _oku() -> dict[str, Any]:
    p = cihaz_dosyasi()
    if not p.exists():
        return {"cihazlar": []}
    try:
        veri = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(veri, dict) or "cihazlar" not in veri:
            raise ValueError("beklenen şema yok")  # i18n-istisna: hemen yakalanıp yalnız log'a yazılıyor
        return veri
    except Exception as e:
        # Bozuk dosyayı SESSİZCE sıfırlamıyoruz — eşleştirilmiş cihazların
        # kaybı kullanıcıya görünmeli, yoksa "cihazım neden düştü" sorusu
        # hiçbir yerde cevaplanmaz.
        logger.error("cihazlar.json okunamadı (%s) — boş liste ile devam", e)
        return {"cihazlar": []}


def _yaz(veri: dict[str, Any]) -> None:
    p = cihaz_dosyasi()
    p.parent.mkdir(parents=True, exist_ok=True)
    gecici = p.with_suffix(".json.tmp")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")
    gecici.replace(p)          # atomik — yarım dosya bırakma


def _ozet(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── Eşleştirme kodu ──────────────────────────────────────────────────────────

def _temizle() -> None:
    simdi = time.time()
    for kod in [k for k, v in _kodlar.items() if v["son"] < simdi]:
        _kodlar.pop(kod, None)


def kod_uret() -> dict[str, Any]:
    """Yeni bir eşleştirme kodu üretir. Önceki açık kodları GEÇERSİZ kılar.

    Tek kod kuralı bilinçli: kullanıcı "Cihaz Ekle"ye iki kez basarsa ekranda tek
    QR görür ama arkada iki geçerli kod dururdu — görünmeyen ikinci kapı.
    """
    _kodlar.clear()
    kod = "".join(secrets.choice(ALFABE) for _ in range(KOD_UZUNLUK))
    _kodlar[kod] = {"son": time.time() + KOD_OMRU_SN, "deneme": 0}
    logger.info("eşleştirme kodu üretildi (%d sn geçerli)", KOD_OMRU_SN)
    return {"kod": kod, "omur_sn": KOD_OMRU_SN}


def acik_kod_var() -> bool:
    _temizle()
    return bool(_kodlar)


def kod_iptal() -> None:
    _kodlar.clear()


def kod_normallestir(kod: str) -> str:
    """Elle yazılan kodu tek biçime indirir: boşluk/tire/nokta atılır, BÜYÜK harf.

    Ekranda kod okunsun diye gruplanabilir ("K7MQ 4X2P"); kullanıcı öyle yazarsa ya da
    küçük harfle girerse eşleşme reddedilmesin. Alfabe 0/O/1/I/L'yi zaten dışlıyor →
    normalleştirme karışıklık yaratmaz. Yalnız alfabedeki karakterler kalır.
    """
    return "".join(c for c in (kod or "").upper() if c in ALFABE)


def kod_dogrula(kod: str, cihaz_adi: str = "") -> str | None:
    """Kodu TÜKETİR ve kalıcı cihaz tokeni döndürür. Geçersizse `None`.

    Fail-closed: boş/yanlış/süresi geçmiş kodun hepsi `None`. Çağıran taraf
    `None` gelince bağlantıyı kapatmak ZORUNDA.
    """
    _temizle()
    kod = kod_normallestir(kod)
    if not kod:                     # boş / yalnız ayraç → deneme sayılmaz
        return None

    kayit = _kodlar.get(kod)
    if kayit is None:
        # Yanlış kod — açık koddaki deneme sayacını artır, pencereyi daralt.
        for v in _kodlar.values():
            v["deneme"] += 1
            if v["deneme"] >= MAX_DENEME:
                logger.warning("eşleştirme kodu %d yanlış denemeden sonra iptal edildi",
                               MAX_DENEME)
                _kodlar.clear()
                break
        return None

    _kodlar.pop(kod, None)          # TEK KULLANIM — doğrulanır doğrulanmaz yanar

    token = secrets.token_urlsafe(32)
    veri = _oku()
    veri["cihazlar"].append({
        "id": secrets.token_hex(8),
        "ad": (cihaz_adi or "Cihaz").strip()[:60],
        "token_ozet": _ozet(token),      # DÜZ token saklanmaz
        "eklendi": time.time(),
        "son_gorulme": None,
    })
    _yaz(veri)
    logger.info("yeni cihaz eşleştirildi (%s)", cihaz_adi or "adsız")
    return token


# ── Cihaz tokeni ─────────────────────────────────────────────────────────────

def token_dogrula(token: str) -> dict[str, Any] | None:
    """Tokenin eşleştirilmiş bir cihaza ait olup olmadığını söyler.

    Karşılaştırma `compare_digest` ile yapılır — düz `==` uzunluk/karakter
    farkında erken döner ve zamanlama sızdırır.
    """
    if not token:
        return None
    ozet = _ozet(token)
    veri = _oku()
    for c in veri["cihazlar"]:
        if secrets.compare_digest(c.get("token_ozet", ""), ozet):
            return c
    return None


def gorundu(cihaz_id: str) -> None:
    veri = _oku()
    for c in veri["cihazlar"]:
        if c.get("id") == cihaz_id:
            c["son_gorulme"] = time.time()
            _yaz(veri)
            return


def cihazlar() -> list[dict[str, Any]]:
    """Eşleştirilmiş cihazlar — token özeti DIŞARI VERİLMEZ."""
    return [
        {k: v for k, v in c.items() if k != "token_ozet"}
        for c in _oku()["cihazlar"]
    ]


def cihaz_sil(cihaz_id: str) -> bool:
    veri = _oku()
    kalan = [c for c in veri["cihazlar"] if c.get("id") != cihaz_id]
    if len(kalan) == len(veri["cihazlar"]):
        return False
    veri["cihazlar"] = kalan
    _yaz(veri)
    logger.info("cihaz eşleştirmesi kaldırıldı (%s)", cihaz_id)
    return True

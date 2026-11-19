"""Postgres'siz yüz deposu — satılan ürünün tek yüz kaynağı.

🔴 **NEDEN VAR:** kişisel Alice yüzleri pgvector'da tutuyor (`faces` tablosu,
`embedding <=> $1::vector`). Satılan pakette **Postgres yok** — `electron/main.js`
bunu açıkça yazar: *"üründe Postgres YOK, .env de paketlenmiyor"*. Kişiseldeki kod
olduğu gibi taşınsaydı `get_pool()` `None` döner ve yüz tanımanın **dokuz ucu da
503** verirdi: özellik kutuda ölü doğardı, üstelik geliştirici makinesinde (PG var)
kusursuz çalıştığı için fark edilmezdi.

Bu tam olarak PLAN ekranını öldüren hatanın aynısı — `todo_store.py` onun için
yazılmıştı ve bu modül onun desenini izler (RLock + geçici dosya + `os.replace`).

**Neden pgvector'a hiç gerek yok:** `FACES_MAX_COUNT` = 20 kişi. Kişi başına birkaç
kayıtla en fazla birkaç yüz vektör eder; 512 boyutlu birkaç yüz vektörde doğrudan
arama numpy'da **mikrosaniyeler** sürer. HNSW indeksi milyonlar için vardır, burada
taşıdığı tek şey bağımlılıktır.

⚠️ **Mesafe tanımı pgvector'ın `<=>` operatörüyle aynı olmalı** (kosinüs mesafesi
= 1 − kosinüs benzerliği). Eşikler (`FACE_RECOGNITION_THRESHOLD` = 0,45 ·
`FACE_CONFIDENT_THRESHOLD`) o tanımda kalibre edildi; başka bir mesafeye geçmek
eşikleri **sessizce** geçersizleştirir.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from typing import Any

import numpy as np

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

_DOSYA = DATA_DIR / "faces.json"
_kilit = threading.RLock()
_SEMA_SURUMU = 1

#: Embedding'ler diske kaç ondalıkla yazılır. pgvector yolundaki `_vec_str`
#: de 6 basamak kullanıyordu — iki depo arasında mesafe farkı doğmasın.
_BASAMAK = 6


# ── disk ────────────────────────────────────────────────────────────────────
def _bos() -> dict[str, Any]:
    return {"_schema": _SEMA_SURUMU, "owner": None, "next_id": 1, "faces": []}


def _oku() -> dict[str, Any]:
    if not _DOSYA.exists():
        return _bos()
    try:
        with open(_DOSYA, encoding="utf-8") as f:
            veri = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        # 🔴 Bozuk dosyayı SESSİZCE boş kabul etmek, kullanıcının bütün yüz
        # kayıtlarını yok saymak demektir. Yedeğe alıp öyle sıfırlıyoruz —
        # veri kaybı geri alınamaz, bir dosya kopyası ucuzdur.
        bozuk = _DOSYA.with_suffix(".bozuk")
        try:
            _DOSYA.replace(bozuk)
            logger.error("faces.json okunamadı (%s) — %s olarak saklandı, boş başlanıyor", e, bozuk)
        except OSError:
            logger.error("faces.json okunamadı ve yedeklenemedi: %s", e)
        return _bos()
    if not isinstance(veri, dict) or "faces" not in veri:
        return _bos()
    veri.setdefault("owner", None)
    veri.setdefault("next_id", max((f.get("id", 0) for f in veri["faces"]), default=0) + 1)
    return veri


def _yaz(veri: dict[str, Any]) -> None:
    """Atomik yazma: geçici dosya + `os.replace`.

    Doğrudan üzerine yazmak, yazma sırasında kesilen bir işlemde dosyayı yarım
    bırakır — yani yukarıdaki "bozuk dosya" yolunu biz üretmiş oluruz.
    """
    # Geçici dosya HEDEFİN yanında: `os.replace` diskler arası taşıyamaz (DATA_DIR'de açılıp
    # başka bir diske yamalanan `_DOSYA`'ya taşımak EXDEV veriyordu — 09-27 test yönlendirmesi).
    _DOSYA.parent.mkdir(parents=True, exist_ok=True)
    fd, gecici = tempfile.mkstemp(dir=str(_DOSYA.parent), prefix=".faces-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(gecici, _DOSYA)
    except BaseException:
        try:
            os.unlink(gecici)
        except OSError:
            pass
        raise


# ── vektör ──────────────────────────────────────────────────────────────────
def _yuvarla(v: np.ndarray) -> list[float]:
    return [round(float(x), _BASAMAK) for x in np.asarray(v).ravel()]


def _mesafe(a: np.ndarray, b: np.ndarray) -> float:
    """Kosinüs mesafesi — pgvector `<=>` ile aynı tanım.

    Embedding'ler zaten L2-normalize (`normed_embedding`) ama normlara yine de
    bölüyoruz: diske 6 basamakla yazılınca norm tam 1 olmuyor ve eşiğin yakınında
    bu fark taraf değiştirebiliyor.
    """
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-12 or nb < 1e-12:
        return 2.0
    return float(1.0 - np.dot(a, b) / (na * nb))


def _kayitlar(veri: dict[str, Any]) -> list[tuple[int, str, np.ndarray, str | None]]:
    return [
        (int(f["id"]), str(f["name"]),
         np.asarray(f["embedding"], dtype=np.float32), f.get("created_at"))
        for f in veri["faces"]
    ]


# ── genel API ───────────────────────────────────────────────────────────────
def ekle(name: str, embedding: np.ndarray) -> int:
    """Yeni encoding ekler, id döner."""
    with _kilit:
        veri = _oku()
        yeni_id = int(veri["next_id"])
        veri["faces"].append({
            "id": yeni_id,
            "name": name,
            "embedding": _yuvarla(embedding),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        veri["next_id"] = yeni_id + 1
        _yaz(veri)
        return yeni_id


def benzersiz_kisiler() -> set[str]:
    with _kilit:
        return {f["name"] for f in _oku()["faces"]}


def kisi_kayit_sayisi(name: str) -> int:
    with _kilit:
        return sum(1 for f in _oku()["faces"] if f["name"] == name)


def kisiler() -> list[dict]:
    """Kişi listesi — kayıt sayısı + ilk görülme (kişiseldeki `list_faces` şekli)."""
    with _kilit:
        kayitlar = _kayitlar(_oku())
    gruplar: dict[str, list[tuple[int, str, np.ndarray, str | None]]] = {}
    for k in kayitlar:
        gruplar.setdefault(k[1], []).append(k)
    cikti = [
        {"name": ad,
         "encodings": len(g),
         "first_seen": min((k[3] for k in g if k[3]), default=None)}
        for ad, g in gruplar.items()
    ]
    cikti.sort(key=lambda d: (d["first_seen"] or ""))
    return cikti


def en_yakin_kisiler(embedding: np.ndarray, limit: int = 2) -> list[tuple[str, float]]:
    """Kişi başına EN İYİ mesafe, yakından uzağa — `(ad, mesafe)`.

    pgvector karşılığı: `SELECT name, MIN(embedding <=> $1) ... GROUP BY name
    ORDER BY dist LIMIT n`. İkinci sıra `margin` için gerekli.
    """
    with _kilit:
        kayitlar = _kayitlar(_oku())
    if not kayitlar:
        return []
    en_iyi: dict[str, float] = {}
    for _, ad, emb, _ts in kayitlar:
        d = _mesafe(embedding, emb)
        if ad not in en_iyi or d < en_iyi[ad]:
            en_iyi[ad] = d
    return sorted(en_iyi.items(), key=lambda t: t[1])[:limit]


def kisiye_min_mesafe(embedding: np.ndarray, name: str) -> float | None:
    """Bu karenin, adı geçen kişinin MEVCUT kayıtlarına en yakın mesafesi (drift).

    `None` = o kişinin hiç kaydı yok (ilk kayıt).
    """
    with _kilit:
        kayitlar = [k for k in _kayitlar(_oku()) if k[1] == name]
    if not kayitlar:
        return None
    return min(_mesafe(embedding, k[2]) for k in kayitlar)


def tum_kayitlar() -> list[tuple[int, str, np.ndarray, str | None]]:
    """Kalite raporu için ham kayıtlar."""
    with _kilit:
        return _kayitlar(_oku())


def sil_kayit(enc_id: int) -> str:
    """Tek encoding siler, sahibinin adını döner. Yoksa `KeyError`."""
    with _kilit:
        veri = _oku()
        hedef = next((f for f in veri["faces"] if int(f["id"]) == enc_id), None)
        if hedef is None:
            raise KeyError(enc_id)
        veri["faces"] = [f for f in veri["faces"] if int(f["id"]) != enc_id]
        _yaz(veri)
        return str(hedef["name"])


def sil_kayit_denetimli(enc_id: int) -> str:
    """Tek kaydı siler ama kişinin **son** kaydını silmeyi reddeder.

    ⚠️ Denetim ve silme AYNI kilit altında olmalı. "Önce say, sonra sil" iki ayrı
    çağrıya bölünürse arada gelen ikinci bir silme kişiyi kayıtsız bırakır —
    kullanıcı kişiyi silmediği hâlde kişi tanınmaz olur ve sebebi hiçbir yerde
    görünmez.
    """
    with _kilit:
        veri = _oku()
        hedef = next((f for f in veri["faces"] if int(f["id"]) == enc_id), None)
        if hedef is None:
            raise KeyError(enc_id)
        ad = str(hedef["name"])
        kalan = sum(1 for f in veri["faces"] if f["name"] == ad)
        if kalan <= 1:
            from app.mesajlar import M
            raise ValueError(M("yuz.tek-kayit", ad=ad))
        veri["faces"] = [f for f in veri["faces"] if int(f["id"]) != enc_id]
        _yaz(veri)
        return ad


def sil_kisi(name: str) -> int:
    """Kişiyi ve tüm kayıtlarını siler, silinen kayıt sayısını döner."""
    with _kilit:
        veri = _oku()
        once = len(veri["faces"])
        veri["faces"] = [f for f in veri["faces"] if f["name"] != name]
        silinen = once - len(veri["faces"])
        if silinen:
            _yaz(veri)
        return silinen


# ── sahiplik ────────────────────────────────────────────────────────────────
def sahip_oku() -> str | None:
    with _kilit:
        return _oku().get("owner") or None


def sahip_yaz(name: str) -> None:
    with _kilit:
        veri = _oku()
        veri["owner"] = name
        _yaz(veri)
    logger.info("Yüz sahibi ayarlandı: %s", name)


# ── test kolaylığı ──────────────────────────────────────────────────────────
def _sifirla() -> None:
    """YALNIZ testler için — depoyu boşaltır."""
    with _kilit:
        _yaz(_bos())

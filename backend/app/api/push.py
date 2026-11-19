"""Faz 12 — Android Companion: Web Push / VAPID API.
Faz 23 — DB persistence: subscriptions + notification history.

Endpoint'ler:
  GET  /api/push/vapid-public-key      → VAPID public key
  POST /api/push/subscribe             → Subscription kaydet (SQLite'a persist)
  POST /api/push/unsubscribe           → Subscription sil
  POST /api/push/test                  → Test push gönder
  GET  /api/push/subscriptions/count   → Aktif subscription sayısı
  GET  /api/push/yuki-dedi              → Yuki'nin kendiliğinden söyledikleri + her kanalın sonucu
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request
from app.limiter import limiter
from app.mesajlar import M
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def require_push() -> None:
    """Telefon bildirimi kademe kapısı — **Pro** (Dalga 4, 2026-09-18).

    Kapı router düzeyinde: bu modülde 6 uç var (09-27; önce 10) ve uç uç yazılan kapıda bir uç
    atlanır (`api/memory.py`, 2026-08-06: 9 uçtan 4'ü kapısızdı). Router
    düzeyi, sonradan eklenen ucu da kendiliğinden kapsar.
    """
    try:
        from app.services import yetki
        izin = yetki.feature_allowed("push_notifications")
    except Exception:
        izin = False          # hata → kapalı (üst kademe sızmasın)
    if not izin:
        raise HTTPException(
            status_code=403,
            detail=M("bildirim.pro-ozelligi"),
        )


router = APIRouter(prefix="/api/push", tags=["push"],
                   dependencies=[Depends(require_push)])

from app.config import DATA_DIR
_KEY_DIR = DATA_DIR  # yazılabilir dizin (vapid anahtarları + push.db burada üretilir/tutulur)
_PRIV_KEY = _KEY_DIR / "vapid_private.pem"
_PUB_KEY  = _KEY_DIR / "vapid_public.pem"
_DB_PATH  = _KEY_DIR / "data" / "push.db"

VAPID_CLAIMS = {"sub": "mailto:yuki@localhost"}


# ── DB ────────────────────────────────────────────────────────────────────────

async def init_push_db() -> None:
    """Push tablolarını oluştur (idempotent)."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                endpoint   TEXT PRIMARY KEY,
                p256dh     TEXT NOT NULL,
                auth       TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_sent  TEXT
            );
            CREATE TABLE IF NOT EXISTS push_notifications (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT NOT NULL,
                body       TEXT NOT NULL DEFAULT '',
                url        TEXT NOT NULL DEFAULT '/',
                sent_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            -- Yuki'nin kendiliğinden söyledikleri (alarm · sabah · gecikmiş · rutin · sistem)
            -- ve her kanalın sonucu: ekran = mesajı alan açık pencere, telefon = push
            -- ulaşan cihaz, ses = seslendirildi mi. İkisi de 0 → kullanıcı KAÇIRDI.
            CREATE TABLE IF NOT EXISTS yuki_dedi (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ts         REAL NOT NULL,
                kaynak     TEXT NOT NULL,
                metin      TEXT NOT NULL,
                ekran      INTEGER NOT NULL DEFAULT 0,
                telefon    INTEGER NOT NULL DEFAULT 0,
                ses        INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS yuki_dedi_ts ON yuki_dedi(ts);
        """)
        await db.commit()
    logger.info("Push DB hazır: %s", _DB_PATH)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── VAPID ─────────────────────────────────────────────────────────────────────

def _get_or_create_vapid_keys() -> tuple[str, str]:
    try:
        from cryptography.hazmat.primitives import serialization
        from py_vapid import Vapid, b64urlencode
    except ImportError:
        raise RuntimeError("pywebpush kurulu değil: pip install pywebpush")  # i18n-istisna: yalnız log'a düşer — iki yakalayıcı da logger.warning ile yutar

    if not _PRIV_KEY.exists():
        logger.info("VAPID anahtarları oluşturuluyor…")
        v = Vapid()
        v.generate_keys()
        v.save_key(str(_PRIV_KEY))
        v.save_public_key(str(_PUB_KEY))

    v = Vapid.from_file(str(_PRIV_KEY))

    # 🔴 2026-09-18 — `v.public_key_urlsafe_base64` py_vapid'de YOK. `from_file`
    # bir `Vapid02` döndürüyor ve o sınıfta böyle bir üye hiç bulunmuyor
    # (üyeler: public_key · public_pem · sign · verify …). Uç bu yüzden 500
    # veriyordu: **telefon bildirimi hiç kurulamıyordu** — tarayıcı
    # `applicationServerKey`i buradan alır, alamayınca abone olamaz.
    # Kusur Dalga 4/1'in kademe turunda çıktı: kapı eklenip uç uçtan uca
    # ölçülünce Pro'da 500 göründü. "İlan edildi ama çalışmıyor" sınıfı —
    # kapıyı yazıp özelliği ölçmeseydik Pro kullanıcı parasını verip
    # abone olamayacaktı.
    #
    # Doğru dönüşüm (Web Push / RFC 8292): ham public key **uncompressed
    # point** (X9.62, 0x04 önekli 65 bayt) olarak alınır, **padding'siz**
    # urlsafe base64'e çevrilir → 87 karakter, 'B' ile başlar. Ölçüldü.
    raw = v.public_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return str(_PRIV_KEY), b64urlencode(raw)


# ── Endpointler ───────────────────────────────────────────────────────────────

@router.get("/vapid-public-key")
@limiter.limit("30/minute")
async def get_vapid_public_key(request: Request):

    try:
        _, pub = _get_or_create_vapid_keys()
        return {"publicKey": pub}
    except (RuntimeError, ImportError) as e:
        logger.warning("Web Push devre dışı: %s", e)
        return {"publicKey": None, "disabled": True}
    except Exception as e:
        # Ham istisna metni kullanıcıya teşhis değil korku verir; sebep log'a,
        # kullanıcıya YAPILACAK İŞ. (CLAUDE.md § ham teknik metin gösterilmez)
        logger.exception("VAPID anahtarı üretilemedi")
        raise HTTPException(status_code=500, detail=M("bildirim.anahtar-uretilemedi"))


class PushSubscription(BaseModel):
    endpoint: str
    keys: dict  # {"p256dh": "...", "auth": "..."}


@router.post("/subscribe")
@limiter.limit("30/minute")
async def subscribe(request: Request, sub: PushSubscription):

    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            """INSERT INTO push_subscriptions (endpoint, p256dh, auth, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(endpoint) DO UPDATE SET p256dh=excluded.p256dh, auth=excluded.auth""",
            (sub.endpoint, sub.keys.get("p256dh", ""), sub.keys.get("auth", ""), _now()),
        )
        await db.commit()
        cur = await db.execute("SELECT COUNT(*) FROM push_subscriptions")
        total = (await cur.fetchone())[0]
    logger.info("Push subscription eklendi: %s… (%d toplam)", sub.endpoint[:60], total)
    return {"status": "subscribed", "total": total}


@router.post("/unsubscribe")
@limiter.limit("30/minute")
async def unsubscribe(request: Request, sub: PushSubscription):

    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (sub.endpoint,))
        await db.commit()
        cur = await db.execute("SELECT COUNT(*) FROM push_subscriptions")
        remaining = (await cur.fetchone())[0]
    logger.info("Push subscription kaldırıldı. Kalan: %d", remaining)
    return {"status": "unsubscribed", "remaining": remaining}


@router.post("/test")
@limiter.limit("30/minute")
async def send_test_push(request: Request):

    # 🔑 Bu metin `push_notifications` tablosuna YAZILIR → BİLDİRİM odasının
    # listesinde görünür. Sabit TR bırakılsaydı oda "temiz" ölçülürken
    # kullanıcının bastığı ilk düğme Türkçe bir satır üretirdi.
    sent = await send_push_to_all("Yuki 🌸", M("bildirim.test-metni"))
    return {"sent": sent}


@router.get("/subscriptions/count")
@limiter.limit("30/minute")
async def get_subscription_count(request: Request):

    async with aiosqlite.connect(_DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM push_subscriptions")
        count = (await cur.fetchone())[0]
    return {"count": count}


# 🔑 2026-09-27 (GELEN KUTUSU): `/send` · `/history` · `PUT|DELETE /notifications*`
# KALDIRILDI. Tek tüketicileri eski BİLDİRİM odasıydı (elle bildirim gönder +
# geçmiş kaydını düzenle/sil); yeni oda Yuki'nin kendi söylediklerini
# `/yuki-dedi`den okur. Geçmişi "düzenlemek" günlüğü yalancı yapıyordu.
# `push_notifications` tablosu durur — `send_push_to_all` hâlâ yazıyor.
@router.get("/yuki-dedi")
@limiter.limit("60/minute")
async def get_yuki_dedi(request: Request, limit: int = 50, once: int | None = None):
    """Yuki'nin kendiliğinden söyledikleri, yeniden eskiye. `once` = bu id'den eskiler (sayfa).

    `kacan_7g`: son 7 günde hiçbir kanala ulaşmayan (ekran=0 ve telefon=0) kayıt sayısı.
    """
    import time as _t
    limit = max(1, min(limit, 200))
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if once:
            cur = await db.execute("SELECT * FROM yuki_dedi WHERE id < ? ORDER BY id DESC LIMIT ?", (once, limit))
        else:
            cur = await db.execute("SELECT * FROM yuki_dedi ORDER BY id DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in await cur.fetchall()]
        cur = await db.execute("SELECT COUNT(*) FROM yuki_dedi WHERE ekran = 0 AND telefon = 0 AND ts >= ?",
                               (_t.time() - 7 * 86400,))
        kacan = (await cur.fetchone())[0]
    return {"kayitlar": rows, "kacan_7g": kacan}


async def yuki_dedi_kaydet(kaynak: str, metin: str, ekran: int, telefon: int, ses: int) -> None:
    """Bir proaktif mesajın kanal sonuçlarını yaz. Hata yutulur — kayıt, mesajın kendisini durdurmaz."""
    import time as _t
    try:
        async with aiosqlite.connect(_DB_PATH) as db:
            await db.execute(
                "INSERT INTO yuki_dedi (ts, kaynak, metin, ekran, telefon, ses) VALUES (?,?,?,?,?,?)",
                (_t.time(), kaynak, metin[:2000], int(ekran), int(telefon), int(ses)))
            await db.execute("DELETE FROM yuki_dedi WHERE id NOT IN (SELECT id FROM yuki_dedi ORDER BY id DESC LIMIT 1000)")
            await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("yuki_dedi yazılamadı: %s", e)


async def yuki_dedi_bugun_var_mi(kaynak: str) -> bool:
    """Bugün (yerel gün) bu kaynaktan kayıt var mı — sabah özeti telafisi için."""
    from datetime import datetime as _dt
    gece = _dt.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    try:
        async with aiosqlite.connect(_DB_PATH) as db:
            cur = await db.execute("SELECT 1 FROM yuki_dedi WHERE kaynak = ? AND ts >= ? LIMIT 1", (kaynak, gece))
            return (await cur.fetchone()) is not None
    except Exception:  # noqa: BLE001
        return False


# ── Push gönderme yardımcısı ──────────────────────────────────────────────────

async def send_push_to_all(title: str, body: str, url: str = "/") -> int:
    """Kayıtlı tüm subscription'lara Web Push gönder; history'ye logla."""
    try:
        from pywebpush import webpush, WebPushException
        priv_key_path, _ = _get_or_create_vapid_keys()
    except Exception as e:
        logger.warning("Web Push gönderilemedi (kütüphane/anahtar hatası): %s", e)
        return 0

    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT endpoint, p256dh, auth FROM push_subscriptions")
        subs = await cur.fetchall()

    if not subs:
        return 0

    payload = json.dumps({"title": title, "body": body, "url": url})
    dead: list[str] = []
    sent = 0

    for row in subs:
        sub_info = {
            "endpoint": row["endpoint"],
            "keys": {"p256dh": row["p256dh"], "auth": row["auth"]},
        }
        try:
            webpush(
                subscription_info=sub_info,
                data=payload,
                vapid_private_key=priv_key_path,
                vapid_claims=VAPID_CLAIMS,
            )
            sent += 1
        except Exception as e:
            err_str = str(e)
            if "410" in err_str or "404" in err_str:
                dead.append(row["endpoint"])
            else:
                logger.warning("Push hatası (%s…): %s", row["endpoint"][:40], e)

    now = _now()
    async with aiosqlite.connect(_DB_PATH) as db:
        # Geçersiz subscription'ları temizle
        for ep in dead:
            await db.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (ep,))
        # Gönderilen bildirimi logla
        await db.execute(
            "INSERT INTO push_notifications (title, body, url, sent_count, created_at) VALUES (?,?,?,?,?)",
            (title, body, url, sent, now),
        )
        # History'yi 500 satırla sınırla
        await db.execute(
            "DELETE FROM push_notifications WHERE id NOT IN (SELECT id FROM push_notifications ORDER BY id DESC LIMIT 500)"
        )
        await db.commit()

    if dead:
        logger.info("%d geçersiz subscription temizlendi.", len(dead))

    return sent

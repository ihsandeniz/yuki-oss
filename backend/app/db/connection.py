"""Async PostgreSQL connection pool (asyncpg) — Faz 3 hafıza katmanı."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import asyncpg

from app.config import DATABASE_URL

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

# Bağlantı kurulamadığında her istekte yeniden denemeyiz (her deneme TCP
# zaman aşımı kadar sürer ve ucu bekletir). Başarısızlığı damgalayıp bu
# süre boyunca doğrudan None döneriz; süre dolunca bir kez daha denenir —
# böylece Postgres sonradan ayağa kalkarsa kendiliğinden geri bağlanır.
_POOL_RETRY_SEC = 60.0
_pool_fail_at: float | None = None
# Son basılan bağlantı hatası. 🔴 2026-09-28 (SAĞLIK paneli): her 60 sn'lik yeniden
# denemede AYNI uyarı WARNING basılıyordu → `error_log.GunlukHandler` onu kullanıcının
# hata günlüğüne yazıyordu (canlıda 30 kopya; `.env`'de DATABASE_URL dolu, hafıza sqlite,
# Postgres kapalı). İlk başarısızlık ve hata DEĞİŞİRSE yine WARNING; aynı hatanın
# tekrarları DEBUG. Sessiz düşüş değil, tekrarsız düşüş.
_son_uyari: str | None = None

_INIT_SQL = Path(__file__).parent / "init.sql"
_MIGRATE_SCOPE_SQL = Path(__file__).parent / "migrate_scope.sql"
_MIGRATE_CHAR_SQL = Path(__file__).parent / "migrate_character.sql"


async def get_pool() -> asyncpg.Pool | None:
    """Bağlantı havuzunu döner.

    None döner: DATABASE_URL yoksa **ya da** Postgres'e bağlanılamıyorsa.
    İkincisi bilinçli: çağıranların hepsi (`memory`, `todo`, `health`, araçlar)
    `pool is None` dalını zaten taşıyor — todo ucu orada `todo_store.json`'a
    düşer. Eskiden burada istisna fırlıyordu ve o yedek dal hiç çalışmıyordu:
    `DATABASE_URL` dolu ama parola/sunucu hatalıysa PLAN ekranı 500 alıp
    *"Plan ekranı açılamadı"* hata kartına düşüyordu (ölçüldü 2026-09-20,
    `InvalidPasswordError: user "yuki"`). Sessiz düşüş değil: WARNING basılır.
    """
    global _pool, _pool_fail_at, _son_uyari
    if not DATABASE_URL:
        return None
    if _pool is not None:
        return _pool
    if _pool_fail_at is not None and (time.monotonic() - _pool_fail_at) < _POOL_RETRY_SEC:
        return None
    try:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=30,
            max_inactive_connection_lifetime=3600,
        )
    except Exception as e:
        _pool_fail_at = time.monotonic()
        imza = f"{type(e).__name__}: {e}"
        seviye = logging.DEBUG if imza == _son_uyari else logging.WARNING
        _son_uyari = imza
        logger.log(
            seviye,
            "PostgreSQL'e bağlanılamadı (%s) — gömülü depoya düşülüyor, "
            "%.0f sn sonra yeniden denenecek.",
            imza, _POOL_RETRY_SEC,
        )
        return None
    _pool_fail_at = None
    _son_uyari = None
    return _pool


async def init_db() -> None:
    """pgvector extension + tabloları oluşturur (CREATE IF NOT EXISTS — idempotent).

    Migration sırası:
      1. migrate_scope.sql     — scope sütunu (Faz C)
      2. migrate_character.sql — character_key sütunu (Faz 17)
      3. init.sql              — tam schema (tablo + index'ler)
    """
    pool = await get_pool()
    if pool is None:
        return
    async with pool.acquire() as conn:
        # Boş veritabanı (ilk kurulum, `docker compose up -d postgres`): göçler var olan
        # `memories` tablosunu değiştirir; tablo yokken ALTER/CREATE INDEX düşüyor ve
        # init.sql'e hiç sıra gelmiyordu → şema hiç kurulmuyor, hafıza her açılışta
        # kapalı kalıyordu (gerçek Postgres'te ölçüldü 2026-11-14). Tablo yoksa göç
        # gereksizdir: init.sql tam şemayı kurar.
        if await conn.fetchval("SELECT to_regclass('memories')") is None:
            await conn.execute(_INIT_SQL.read_text(encoding="utf-8"))
            return
        if _MIGRATE_SCOPE_SQL.exists():
            await conn.execute(_MIGRATE_SCOPE_SQL.read_text(encoding="utf-8"))
        if _MIGRATE_CHAR_SQL.exists():
            await conn.execute(_MIGRATE_CHAR_SQL.read_text(encoding="utf-8"))
        await conn.execute(_INIT_SQL.read_text(encoding="utf-8"))


async def close_pool() -> None:
    """Uygulama kapanışında bağlantı havuzunu kapat."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None

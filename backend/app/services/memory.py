"""Yuki Semantic Memory Service — pgvector + sentence-transformers.

Faz 3:  Uzun vadeli semantik hafıza sistemi.
Faz C:  Named Memory Scopes (conversation/fact/preference/skill).
Faz 17: Per-character memory — her karakterin anı kümesi izole (character_key).

- add()       : Yeni anı kaydet (embedding otomatik hesaplanır)
- search()    : Semantik benzerlikle ilgili anıları bul
- get_recent(): Son N konuşma mesajını getir (short-term context)
- cleanup()   : Eski & düşük önemli anıları sil (forgetting mekanizması)

DATABASE_URL tanımlı değilse tüm metodlar sessizce None/[] döner.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.config import MEMORY_ENABLED, SESSION_ID, MEMORY_MIN_SIMILARITY, HNSW_EF_SEARCH
from app.db.connection import get_pool

log = logging.getLogger(__name__)

# Arayüz her sohbet mesajının sonuna Yuki için gizli bir sekme bağlamı ekler
# (frontend/js/map-init.js buildContext → core.js `t + _ctx`; `uptime-display` hep dolu
# olduğu için blok HER mesajda var). Yuki onu o tur görmeli, ama HAFIZAYA girmemeli:
# 2026-09-27 ölçümü — kullanıcı yolunda (sqlite-vec) her kullanıcı kaydı blokla yazılıyordu.
# Tek kaynak: iki hafıza servisi (pgvector + sqlite) ve llm._strip_tab_context bunu kullanır.
# Kapanmamış blok da kesilir — kesik kayıtlar kişisel hafızada görüldü.
_SEKME_BAGLAMI = re.compile(r"\s*\[TAB_CONTEXT\b[\s\S]*?(?:\[/TAB_CONTEXT\]|$)")


# Türkçe harfler ASCII karşılığına: aksansız klavyeyle "isik" / "sut" yazan "Işık" / "süt"ü bulsun
# (ölçüldü 09-27: yalnız i/ı katlanırken "ISIK" araması "Işık"ı BULMUYORDU). pgvector tarafı
# aynı eşlemeyi `translate(content, _TR_HARF, _TR_ASCII)` ile uygular — iki liste tek kaynak.
_TR_HARF = "İIıÇçĞğÖöŞşÜü"
_TR_ASCII = "iiiccggoossuu"
_I_KATLA = str.maketrans(_TR_HARF, _TR_ASCII)


def arama_katla(metin: str) -> str:
    """Kelime araması için harf katlama — iki backend de AYNI kuralı uygular.

    sqlite `LIKE` yalnız ASCII'de harf duyarsız ("İstanbul" ≠ "istanbul"), Python'un
    `lower()`'ı "İ"yi "i̇" (i + birleşik nokta) yapar. Türkçe harfler ASCII'ye katlanır:
    arama kutusunda kullanıcı büyük/küçük, noktalı/noktasız ya da aksanlı harfe dikkat etmez.
    """
    return (metin or "").translate(_I_KATLA).lower()


def arama_kalibi(q: str) -> str:
    r"""`LIKE … ESCAPE '\'` kalıbı: kullanıcının % ve _ harfleri joker sayılmaz."""
    k = arama_katla(q).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{k}%"


def sekme_baglamini_ayikla(metin: str) -> str:
    """Metinden [TAB_CONTEXT …] bloğunu çıkarır; blok yoksa metne dokunmaz."""
    if not metin or "[TAB_CONTEXT" not in metin:
        return metin
    return _SEKME_BAGLAMI.sub("", metin).strip()

# ------------------------------------------------------------------ #
# Embedding (lokal, Türkçe dahil çok dilli)
# ------------------------------------------------------------------ #

_model = None
_model_lock = threading.Lock()


def _load_model():
    """sentence-transformers modelini thread-safe yükle."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer
                _model = SentenceTransformer(
                    "paraphrase-multilingual-MiniLM-L12-v2"
                )
    return _model


async def _embed(text: str) -> list[float]:
    """Metni 384 boyutlu vektöre çevir (blocking → executor)."""
    result = await _embed_batch([text])
    return result[0]


def _use_onnx() -> bool:
    """ONNX motoru mu kullanılsın? (paketli üründe torch yok → tek seçenek)"""
    from app.config import EMBED_BACKEND
    from app.services import embedding_onnx

    if EMBED_BACKEND == "st":
        return False
    if EMBED_BACKEND == "onnx":
        return True
    return embedding_onnx.available()  # auto


async def _embed_batch(texts: list[str]) -> list[list[float]]:
    """Birden fazla metni tek seferde encode et (batch). Performans: N ayrı çağrıdan hızlı.

    Motor: ONNX (paketli ürün, torch'suz) ya da sentence-transformers (geliştirme).
    İkisi de normalize edilmiş 384-dim vektör döner — depodaki vektörler uyumludur.
    """
    def _do():
        if _use_onnx():
            from app.services import embedding_onnx
            return embedding_onnx.encode(texts)
        model = _load_model()
        embeddings = model.encode(texts, normalize_embeddings=True, batch_size=len(texts))
        return [e.tolist() for e in embeddings]

    return await asyncio.get_running_loop().run_in_executor(None, _do)


async def warm_embedding() -> str:
    """Aktif embedding motorunu önden yükle (cold start'ı kısaltır). Motor adını döner."""
    def _do():
        if _use_onnx():
            from app.services import embedding_onnx
            embedding_onnx.encode(["ısınma"])
            return "onnx"
        _load_model()
        return "sentence-transformers"

    return await asyncio.get_running_loop().run_in_executor(None, _do)


def _vec_to_pg(vec: list[float]) -> str:
    """asyncpg için pgvector string formatı: [0.1,0.2,...]"""
    return "[" + ",".join(f"{v:.8f}" for v in vec) + "]"


# ------------------------------------------------------------------ #
# Karakter anahtarı yardımcısı
# ------------------------------------------------------------------ #

def _get_active_character() -> str:
    """Aktif persona'nın character_key'ini döner.

    Circular import'tan kaçınmak için lazy import kullanır (personas → memory olmaması için).
    Herhangi bir hata durumunda 'yuki' varsayılanına döner.
    """
    try:
        from app.services.personas import get_persona  # lazy — circular dep yok
        return get_persona()  # direkt string döner: "yuki" vb.
    except Exception:
        return "yuki"


# ------------------------------------------------------------------ #
# Memory dataclass
# ------------------------------------------------------------------ #


VALID_SCOPES = ("conversation", "fact", "preference", "skill")
# Geçerli karakterler = persona kaydı (2026-11-14: yalnız Yuki). Eski kurulumlarda
# kaldırılmış karakterlerin satırları DB'de durabilir; silinmez, yalnız okunmaz.
from app.services.personas import PERSONAS as _PERSONAS  # noqa: E402
VALID_CHARACTERS = tuple(_PERSONAS)

# Scope bazlı importance ağırlıkları (C3 hibrit skor için)
SCOPE_IMPORTANCE_WEIGHT = {
    "preference": 0.9,
    "fact": 0.8,
    "skill": 0.7,
    "conversation": 0.4,
}


@dataclass
class Memory:
    id: int
    session_id: str
    role: str
    content: str
    category: str
    importance: float
    created_at: datetime
    similarity: float = field(default=0.0)
    scope: str = "conversation"
    character_key: str = "yuki"


# ------------------------------------------------------------------ #
# MemoryService
# ------------------------------------------------------------------ #


class MemoryService:
    """Tek örnek (singleton) hafıza servisi."""

    async def add(
        self,
        content: str,
        role: str = "user",
        category: str = "conversation",
        importance: float = 0.5,
        session_id: str = SESSION_ID,
        scope: str = "conversation",
        emit: bool = True,
        emit_kind: str = "skill",
        character_key: Optional[str] = None,
    ) -> int | None:
        """Yeni anı ekle. Embedding otomatik hesaplanır. ID döner.

        character_key=None ise aktif persona'nın anahtarı kullanılır.
        scope=='skill' ve emit ise frontend'e beceri kazanım kartı yayınlanır.
        """
        pool = await get_pool()
        if pool is None:
            return None

        if scope not in VALID_SCOPES:
            scope = "conversation"

        content = sekme_baglamini_ayikla(content)
        if not content:
            return None

        char_key = character_key or _get_active_character()

        vec = await _embed(content)
        vec_str = _vec_to_pg(vec)

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO memories (session_id, role, content, embedding, category, importance, scope, character_key)
                VALUES ($1, $2, $3, $4::vector, $5, $6, $7, $8)
                RETURNING id
                """,
                session_id, role, content, vec_str, category, importance, scope, char_key,
            )
        rid = row["id"] if row else None
        if rid is not None and emit and scope == "skill":
            try:
                from app.services.skill_events import note_skill_memory
                await note_skill_memory(content, emit_kind)
            except Exception:
                pass
        return rid

    async def search(
        self,
        query: str,
        limit: int = 5,
        session_id: str = SESSION_ID,
        min_similarity: float = MEMORY_MIN_SIMILARITY,
        category: Optional[str] = None,
        scope: Optional[str] = None,
        character_key: Optional[str] = None,
        cross_character: bool = False,
    ) -> list[Memory]:
        """Semantik benzerlikle hibrit skor: 0.50*cosine + 0.20*importance + 0.15*recency + 0.15*scope_weight.

        character_key=None ise aktif persona'nın anılarında arama yapar.
        cross_character=True ise character_key filtresi UYGULANMAZ — tüm karakterlerin
        anıları taranır (global hafıza; Memory.character_key ile kaynak ayırt edilebilir).
        """
        pool = await get_pool()
        if pool is None:
            return []

        char_key = character_key or _get_active_character()
        vec = await _embed(query)
        vec_str = _vec_to_pg(vec)

        # Dinamik filtreler
        filters: list[str] = []
        params: list = [vec_str, session_id]
        param_idx = 3

        # Karakter izolasyonu — global hafıza modunda atlanır (tüm karakterler taranır)
        if not cross_character:
            filters.append(f"AND character_key = ${param_idx}")
            params.append(char_key)
            param_idx += 1

        if category:
            filters.append(f"AND category = ${param_idx}")
            params.append(category)
            param_idx += 1

        if scope:
            filters.append(f"AND scope = ${param_idx}")
            params.append(scope)
            param_idx += 1

        filter_sql = " ".join(filters)

        # Hibrit skor: 0.50*cosine + 0.20*importance + 0.15*recency + 0.15*scope_weight
        # recency: Park et al. exponential decay — POWER(0.995, hours_elapsed)
        # scope_weight: preference=0.9, fact=0.8, skill=0.7, conversation=0.4
        async with pool.acquire() as conn:
            await conn.execute(f"SET hnsw.ef_search = {int(HNSW_EF_SEARCH)}")
            await conn.execute("SET hnsw.iterative_scan = strict_order")
            rows = await conn.fetch(
                f"""
                SELECT id, session_id, role, content, category, importance, created_at, scope, character_key,
                       1 - (embedding <=> $1::vector) AS similarity,
                       (
                         0.50 * (1 - (embedding <=> $1::vector))
                         + 0.20 * importance
                         + 0.15 * POWER(0.995, EXTRACT(EPOCH FROM (NOW() - created_at)) / 3600.0)
                         + 0.15 * CASE scope
                             WHEN 'preference' THEN 0.9
                             WHEN 'fact'       THEN 0.8
                             WHEN 'skill'      THEN 0.7
                             WHEN 'conversation' THEN 0.4
                             ELSE 0.5
                           END
                       ) AS hybrid_score
                FROM memories
                WHERE session_id = $2
                  {filter_sql}
                  AND 1 - (embedding <=> $1::vector) >= {min_similarity}
                ORDER BY hybrid_score DESC
                LIMIT {limit}
                """,
                *params,
            )

        mems = [
            Memory(**{k: v for k, v in dict(r).items() if k != "hybrid_score"})
            for r in rows
        ]
        # Sıra-duyarlı kapı — sqlite backend'iyle aynı davranış (memory_gate.py).
        from app.config import MEMORY_REL_RATIO
        from app.services.memory_gate import filter_relative
        return filter_relative(mems, floor=min_similarity, ratio=MEMORY_REL_RATIO)

    async def get_recent(
        self,
        limit: int = 20,
        session_id: str = SESSION_ID,
        category: str = "conversation",
        character_key: Optional[str] = None,
    ) -> list[Memory]:
        """Son N konuşma mesajını kronolojik sırayla getir.

        character_key=None ise aktif persona'nın mesajlarını getirir.
        """
        pool = await get_pool()
        if pool is None:
            return []

        char_key = character_key or _get_active_character()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, session_id, role, content, category, importance, created_at, scope, character_key,
                       0.0::float AS similarity
                FROM memories
                WHERE session_id = $1 AND category = $2 AND character_key = $3
                ORDER BY created_at DESC, id DESC
                LIMIT $4
                """,
                session_id, category, char_key, limit,
            )

        # DESC sorgudan geldi, kronolojik sıra için tersine çevir
        return list(reversed([Memory(**dict(r)) for r in rows]))

    async def cleanup(
        self,
        session_id: str = SESSION_ID,
        importance_threshold: float = 0.35,
        days_old: int = 7,
        character_key: Optional[str] = None,
    ) -> int:
        """Eski ve düşük önem puanlı conversation anılarını sil.

        preference/fact kategorileri dokunulmaz (sadece conversation).
        character_key=None ise aktif persona'nın anılarını temizler.
        """
        pool = await get_pool()
        if pool is None:
            return 0

        char_key = character_key or _get_active_character()

        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM memories
                WHERE session_id = $1
                  AND character_key = $2
                  AND category = 'conversation'
                  AND importance < $3
                  AND created_at < NOW() - ($4 || ' days')::INTERVAL
                """,
                session_id, char_key, importance_threshold, str(days_old),
            )

        # "DELETE N" formatından sayıyı çıkar
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0

    async def update(
        self,
        memory_id: int,
        importance: Optional[float] = None,
        content: Optional[str] = None,
        character_key: Optional[str] = None,
    ) -> bool:
        """Anının importance ve/veya içeriğini güncelle. True döner güncellendiyse.

        character_key: karakter izolasyonu (None ise aktif persona'nın anahtarı kullanılır).
        """
        pool = await get_pool()
        if pool is None:
            return False

        char_key = character_key or _get_active_character()

        sets = []
        params: list = []
        if importance is not None:
            params.append(importance)
            sets.append(f"importance = ${len(params)}")
        if content is not None:
            # İçerik değişince vektör de yenilenir: eskiden eski metnin vektörü kalıyordu,
            # düzeltilen anı eski anlamıyla bulunuyordu. Gömme düşerse güncelleme yapılmaz
            # (add() ile aynı davranış) — "yeni metin + eski vektör" çifti hiç oluşmaz.
            try:
                vec_str = _vec_to_pg(await _embed(content))
            except Exception as e:  # noqa: BLE001
                log.error("Anı güncellemesinde gömme başarısız, güncelleme yapılmadı: %s", e)
                return False
            params.append(content)
            sets.append(f"content = ${len(params)}")
            params.append(vec_str)
            sets.append(f"embedding = ${len(params)}::vector")
        if not sets:
            return False
        params.append(memory_id)
        params.append(char_key)
        sql = f"UPDATE memories SET {', '.join(sets)} WHERE id = ${len(params) - 1} AND character_key = ${len(params)}"
        async with pool.acquire() as conn:
            result = await conn.execute(sql, *params)
        return result == "UPDATE 1"

    async def delete(self, memory_id: int, character_key: Optional[str] = None) -> bool:
        """Tek anıyı sil. True döner silinirse.

        character_key: karakter izolasyonu (None ise aktif persona'nın anahtarı kullanılır).
        """
        pool = await get_pool()
        if pool is None:
            return False

        char_key = character_key or _get_active_character()

        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM memories WHERE id = $1 AND character_key = $2",
                memory_id,
                char_key,
            )
        return result == "DELETE 1"

    async def clear_conversations(
        self,
        session_id: str = SESSION_ID,
        character_key: Optional[str] = None,
    ) -> int:
        """Bir oturumun 'conversation' anılarını sil (fact/preference KALIR).

        clear_history'nin backend-bağımsız yolu — sqlite backend'de aynı adlı
        metot vec tablosunu da temizler.
        """
        pool = await get_pool()
        if pool is None:
            return 0

        char_key = character_key or _get_active_character()

        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM memories WHERE session_id = $1 AND character_key = $2 "
                "AND category = 'conversation'",
                session_id,
                char_key,
            )
        try:
            return int(str(result).rsplit(" ", 1)[-1])
        except (ValueError, IndexError):
            return 0

    async def list_all(
        self,
        session_id: str = SESSION_ID,
        limit: int = 50,
        offset: int = 0,
        category: Optional[str] = None,
        scope: Optional[str] = None,
        character_key: Optional[str] = None,
        icerik: Optional[str] = None,
    ) -> list[Memory]:
        """Tüm anıları listele (pagination destekli). `icerik` = kelime araması.

        character_key=None ise aktif persona'nın anılarını listeler.
        """
        pool = await get_pool()
        if pool is None:
            return []

        char_key = character_key or _get_active_character()

        filters: list[str] = []
        params: list = [session_id, char_key, limit, offset]
        param_idx = 5

        if category:
            filters.append(f"AND category = ${param_idx}")
            params.append(category)
            param_idx += 1

        if scope:
            filters.append(f"AND scope = ${param_idx}")
            params.append(scope)
            param_idx += 1

        if icerik:
            # arama_katla ile aynı kural: Türkçe harf → ASCII, sonra küçük harf
            filters.append(f"AND lower(translate(content, '{_TR_HARF}', '{_TR_ASCII}')) LIKE ${param_idx} ESCAPE '\\'")
            params.append(arama_kalibi(icerik))
            param_idx += 1

        filter_sql = " ".join(filters)

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT id, session_id, role, content, category, importance, created_at,
                       0.0::float AS similarity, scope, character_key
                FROM memories
                WHERE session_id = $1
                  AND character_key = $2
                  {filter_sql}
                ORDER BY created_at DESC, id DESC
                LIMIT $3 OFFSET $4
                """,
                *params,
            )

        return [Memory(**dict(r)) for r in rows]

    async def add_batch(
        self,
        items: list[dict],
        session_id: str = SESSION_ID,
        character_key: Optional[str] = None,
    ) -> list[int]:
        """Toplu anı ekle. Tek seferde batch embed + insert.

        items: [{"content": str, "role": str, "category": str, "importance": float}, ...]
        Aynı içerikli kayıtları yinelemez (in-batch + son 60s DB kontrolü).
        character_key=None ise aktif persona'nın anahtarı kullanılır.
        """
        pool = await get_pool()
        if pool is None:
            return []

        char_key = character_key or _get_active_character()

        # Sekme bağlamı hafızaya girmez (bkz. sekme_baglamini_ayikla); dedup'tan ÖNCE —
        # blokta Uptime her mesajda farklı, ayıklanmadan aynı mesaj tekrarı yakalanmaz
        items = [dict(it, content=sekme_baglamini_ayikla(it["content"])) for it in items]
        items = [it for it in items if it["content"]]

        # In-batch dedup: aynı (role, content) çiftini bir kez ekle
        seen: set[tuple[str, str]] = set()
        deduped: list[dict] = []
        for item in items:
            key = (item.get("role", "user"), item["content"])
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        items = deduped

        if not items:
            return []

        texts = [item["content"] for item in items]
        vecs = await _embed_batch(texts)

        ids: list[int] = []
        async with pool.acquire() as conn:
            # Son 60 saniyede kaydedilen (role, content) çiftlerini al (double-save önlemi)
            recent_rows = await conn.fetch(
                """
                SELECT role, content FROM memories
                WHERE session_id = $1 AND character_key = $2
                  AND created_at > NOW() - INTERVAL '60 seconds'
                """,
                session_id, char_key,
            )
            recent_keys = {(r["role"], r["content"]) for r in recent_rows}

            for item, vec in zip(items, vecs):
                key = (item.get("role", "user"), item["content"])
                if key in recent_keys:
                    continue  # Son 60s içinde zaten kaydedilmiş, atla
                vec_str = _vec_to_pg(vec)
                scope = item.get("scope", item.get("category", "conversation"))
                if scope not in VALID_SCOPES:
                    scope = "conversation"
                row = await conn.fetchrow(
                    """
                    INSERT INTO memories (session_id, role, content, embedding, category, importance, scope, character_key)
                    VALUES ($1, $2, $3, $4::vector, $5, $6, $7, $8)
                    RETURNING id
                    """,
                    session_id,
                    item.get("role", "user"),
                    item["content"],
                    vec_str,
                    item.get("category", "conversation"),
                    item.get("importance", 0.5),
                    scope,
                    char_key,
                )
                if row:
                    ids.append(row["id"])
        return ids

    async def count(
        self,
        session_id: str = SESSION_ID,
        character_key: Optional[str] = None,
    ) -> int:
        """Toplam anı sayısını döner.

        character_key=None ise aktif persona'nın anı sayısını döner.
        """
        pool = await get_pool()
        if pool is None:
            return 0

        char_key = character_key or _get_active_character()

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) AS cnt FROM memories WHERE session_id = $1 AND character_key = $2",
                session_id, char_key,
            )
        return row["cnt"] if row else 0

    async def reinforce(self, memory_ids: list[int], delta: float = 0.03, character_key: Optional[str] = None) -> None:
        """Erişilen anıların önem puanını artır (reinforcement learning).

        Sık erişilen anılar zamanla daha önemli hale gelir. importance 1.0 ile sınırlanır.

        character_key: karakter izolasyonu (None ise aktif persona'nın anahtarı kullanılır).
        """
        pool = await get_pool()
        if pool is None or not memory_ids:
            return

        char_key = character_key or _get_active_character()

        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE memories SET importance = LEAST(1.0, importance + $1) WHERE id = ANY($2::int[]) AND character_key = $3",
                delta, memory_ids, char_key,
            )

    async def consolidate_facts(
        self,
        session_id: str = SESSION_ID,
        threshold: float = 0.92,
        character_key: Optional[str] = None,
    ) -> int:
        """Fact/preference kapsamındaki benzer anıları pgvector ile bul, eskiyi sil.

        Cosine similarity >= threshold olan çiftlerde yenisi (created_at DESC) korunur.
        character_key=None ise aktif persona'nın anılarında işlem yapar.
        Döner: silinen anı sayısı.
        """
        pool = await get_pool()
        if pool is None:
            return 0

        char_key = character_key or _get_active_character()

        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM memories
                WHERE id IN (
                    SELECT DISTINCT m1.id
                    FROM memories m1
                    JOIN memories m2
                        ON m1.session_id = m2.session_id
                       AND m1.character_key = m2.character_key
                       AND m1.id <> m2.id
                       AND m1.created_at < m2.created_at
                       AND m1.scope IN ('fact', 'preference')
                       AND m2.scope IN ('fact', 'preference')
                       AND 1 - (m1.embedding <=> m2.embedding) >= $2
                    WHERE m1.session_id = $1
                      AND m1.character_key = $3
                )
                """,
                session_id, threshold, char_key,
            )
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0

    async def stats(
        self,
        session_id: str = SESSION_ID,
        character_key: Optional[str] = None,
    ) -> dict:
        """Kapsam başına anı sayısı, ortalama önem ve toplam (tek connection, tutarlı).

        character_key=None ise aktif persona'nın istatistiklerini döner.
        """
        pool = await get_pool()
        if pool is None:
            return {"total": 0, "scopes": {}}

        char_key = character_key or _get_active_character()

        async with pool.acquire() as conn:
            total_row = await conn.fetchrow(
                "SELECT COUNT(*) AS cnt FROM memories WHERE session_id = $1 AND character_key = $2",
                session_id, char_key,
            )
            rows = await conn.fetch(
                """
                SELECT scope, COUNT(*) AS cnt, AVG(importance) AS avg_imp
                FROM memories
                WHERE session_id = $1 AND character_key = $2
                GROUP BY scope
                ORDER BY cnt DESC
                """,
                session_id, char_key,
            )
            # 🔴 `scope` ile `category` AYRI kavramlar: `scope` hibrit skorun
            #    ağırlığıdır (`SCOPE_IMPORTANCE_WEIGHT`), `category` ise Hafıza
            #    Yöneticisi'nin süzgeci — liste ucu `?category=` ile filtreliyor.
            #    Panel 2026-09-20'ye kadar süzgeç sayaçlarını `scopes`'tan
            #    okuyordu: her anının scope'u varsayılan 'conversation' olduğu
            #    için "Gerçek 0 · Tercih 0 · Görev 0" yazıyordu, liste doluyken.
            kat_rows = await conn.fetch(
                """
                SELECT category, COUNT(*) AS cnt
                FROM memories
                WHERE session_id = $1 AND character_key = $2
                GROUP BY category
                """,
                session_id, char_key,
            )
        total = total_row["cnt"] if total_row else 0
        scopes = {
            r["scope"]: {"count": r["cnt"], "avg_importance": round(float(r["avg_imp"]), 3)}
            for r in rows
        }
        categories = {r["category"]: r["cnt"] for r in kat_rows}
        return {"total": total, "scopes": scopes, "categories": categories,
                "character_key": char_key}

    async def sekme_baglami_temizle(self) -> dict:
        """Eski sürümlerin hafızaya yanlış yazdıklarını BİR KEZ düzeltir — pgvector karşılığı.

        Kurallar ve gerekçe `memory_sqlite.SqliteVecMemoryService.sekme_baglami_temizle` ile
        aynı (blok kesilir + vektör yeniden · yalnız blok → silinir · _save_exchange imzalı
        cevap/soru → conversation; /öğren ve çıkarım satırları korunur). Yedek: etkilenen
        satırların JSON dökümü DATA_DIR/yedek/ altına (vektörler temiz metinden yeniden üretilir).
        Tek işlem: yarıda hata → hiçbir satır değişmez.
        """
        import json
        from app import config

        pool = await get_pool()
        if pool is None:
            return {}
        async with pool.acquire() as conn:
            etkilenen = await conn.fetch(
                """
                SELECT id, role, category, scope, importance, character_key, content FROM memories
                WHERE content LIKE '%[TAB_CONTEXT%'
                   OR (role = 'assistant' AND scope <> 'conversation' AND category = scope)
                   OR (role = 'user' AND scope <> 'conversation' AND category = scope
                       AND rtrim(content) LIKE '%?')
                ORDER BY id
                """
            )
        if not etkilenen:
            return {}

        yedek_dizin = config.DATA_DIR / "yedek"
        yedek_dizin.mkdir(parents=True, exist_ok=True)
        yedek = yedek_dizin / f"hafiza-sekme-{datetime.now():%Y%m%d-%H%M%S}.json"
        yedek.write_text(json.dumps([dict(r) for r in etkilenen], ensure_ascii=False, indent=1),
                         encoding="utf-8")

        bloklu = [r for r in etkilenen if "[TAB_CONTEXT" in r["content"]]
        temiz = [(r["id"], sekme_baglamini_ayikla(r["content"])) for r in bloklu]
        guncel = [t for t in temiz if t[1]]
        silinecek = [t[0] for t in temiz if not t[1]]
        vecs = await _embed_batch([t[1] for t in guncel]) if guncel else []

        async with pool.acquire() as conn:
            async with conn.transaction():
                for (rid, metin), vec in zip(guncel, vecs):
                    await conn.execute(
                        "UPDATE memories SET content = $1, embedding = $2::vector WHERE id = $3",
                        metin, _vec_to_pg(vec), rid,
                    )
                if silinecek:
                    await conn.execute("DELETE FROM memories WHERE id = ANY($1::bigint[])", silinecek)
                n_cevap = await conn.fetchval(
                    """
                    WITH d AS (UPDATE memories SET scope='conversation', category='conversation', importance=0.5
                               WHERE role='assistant' AND scope <> 'conversation' AND category = scope
                               RETURNING 1) SELECT COUNT(*) FROM d
                    """
                )
                # Soru kuralı blok kesildikten SONRA: "ne?[TAB_CONTEXT…]" ancak şimdi '?' ile biter
                n_soru = await conn.fetchval(
                    """
                    WITH d AS (UPDATE memories SET scope='conversation', category='conversation', importance=0.5
                               WHERE role='user' AND scope <> 'conversation' AND category = scope
                                 AND rtrim(content) LIKE '%?'
                               RETURNING 1) SELECT COUNT(*) FROM d
                    """
                )
        return {
            "blok_temizlendi": len(guncel),
            "silindi": len(silinecek),
            "cevap_konusma": n_cevap,
            "soru_konusma": n_soru,
            "yedek": str(yedek),
        }


# ------------------------------------------------------------------ #
# Singleton
# ------------------------------------------------------------------ #

_service = None


def get_memory_service():
    """Hafıza servisi (singleton). Backend config MEMORY_BACKEND ile seçilir:
    'sqlite' → gömülü sqlite-vec (paketli ürün) · aksi → pgvector (SaaS/kişisel)."""
    global _service
    if _service is None:
        from app.config import MEMORY_BACKEND
        if MEMORY_BACKEND == "sqlite":
            from app.services.memory_sqlite import SqliteVecMemoryService
            _service = SqliteVecMemoryService()
        else:
            _service = MemoryService()
    return _service

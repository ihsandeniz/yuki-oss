"""Yuki Semantic Memory — gömülü sqlite-vec arka ucu (paketli ürün, Docker'sız).

`memory.py` (pgvector) ile BİREBİR aynı public arayüz — `get_memory_service()`
config `MEMORY_BACKEND` ile birini seçer. Embedding/dataclass/karakter yardımcıları
memory.py'den paylaşılır (tek kaynak). Ultra P7 "Unutmayan Yuki" paywall'ının motoru.

Şema (iki tablo, memory_id ile bağlı):
  memories      — zengin metadata (SQL-sorgulanabilir: list/cleanup/stats/update...)
  vec_memories  — vec0 sanal tablo, YALNIZ KNN (character_key partition + cosine)

Hibrit skor pgvector ile aynı: 0.50*cosine + 0.20*importance + 0.15*recency + 0.15*scope.
Recency + skor Python'da hesaplanır (KNN over-fetch → yeniden sırala). sqlite bloklayıcı
olduğu için tüm DB işi tek bağlantı + kilit ile executor'da koşar (olay döngüsü bloke olmaz).
"""
from __future__ import annotations

import asyncio
import struct
import threading
from datetime import datetime, timedelta
from typing import Optional

from app.config import (
    MEMORY_DB_PATH,
    MEMORY_MIN_SIMILARITY,
    SESSION_ID,
)
# memory.py ile paylaşılan tek kaynak — embedding, dataclass, sabitler, karakter yardımcısı
from app.services.memory import (
    Memory,
    arama_kalibi,
    arama_katla,
    SCOPE_IMPORTANCE_WEIGHT,
    VALID_SCOPES,
    _embed,
    _embed_batch,
    _get_active_character,
    sekme_baglamini_ayikla,
)

EMBED_DIM = 384


def _serialize(vec: list[float]) -> bytes:
    """float listesi → sqlite-vec'in beklediği ham float32 bayt dizisi."""
    return struct.pack("%df" % len(vec), *vec)


# ------------------------------------------------------------------ #
# Bağlantı (tek paylaşımlı, kilitli — executor thread'lerinde güvenli)
# ------------------------------------------------------------------ #
_conn = None
# RLock ŞART: _run() kilidi alır, içindeki _get_conn() ilk çağrıda aynı kilidi
# yeniden ister (lazy şema kurulumu) → düz Lock ile ilk yazma/arama kilitlenirdi.
_conn_lock = threading.RLock()


def _get_conn():
    """sqlite-vec yüklü tek bağlantı; ilk çağrıda şemayı kurar."""
    global _conn
    if _conn is not None:
        return _conn
    with _conn_lock:
        if _conn is not None:
            return _conn
        import sqlite3
        import sqlite_vec

        conn = sqlite3.connect(MEMORY_DB_PATH, check_same_thread=False)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.execute("PRAGMA journal_mode=WAL")
        # Kelime araması: LIKE yalnız ASCII'de harf duyarsız → Türkçe katlama Python'da
        conn.create_function("arama_katla", 1, arama_katla, deterministic=True)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id    TEXT NOT NULL,
                role          TEXT NOT NULL,
                content       TEXT NOT NULL,
                category      TEXT NOT NULL DEFAULT 'conversation',
                importance    REAL NOT NULL DEFAULT 0.5,
                created_at    TEXT NOT NULL,
                scope         TEXT NOT NULL DEFAULT 'conversation',
                character_key TEXT NOT NULL DEFAULT 'yuki'
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mem_sess_char ON memories(session_id, character_key)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mem_cat ON memories(session_id, character_key, category)"
        )
        conn.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_memories USING vec0(
                memory_id     integer primary key,
                character_key text partition key,
                embedding     float[{EMBED_DIM}] distance_metric=cosine
            )
            """
        )
        conn.commit()
        _conn = conn
        return _conn


async def _run(fn):
    """Bloklayıcı sqlite işini kilitli executor'da koştur (olay döngüsünü bloke etmez)."""
    def _locked():
        with _conn_lock:
            return fn(_get_conn())
    return await asyncio.get_running_loop().run_in_executor(None, _locked)


def _now_iso() -> str:
    return datetime.now().isoformat()


def _parse_dt(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime.now()


def _row_to_memory(r, similarity: float = 0.0) -> Memory:
    # r: (id, session_id, role, content, category, importance, created_at, scope, character_key)
    return Memory(
        id=r[0], session_id=r[1], role=r[2], content=r[3], category=r[4],
        importance=r[5], created_at=_parse_dt(r[6]), scope=r[8],
        character_key=r[7] if len(r) > 7 else "yuki", similarity=similarity,
    )


_COLS = "id, session_id, role, content, category, importance, created_at, character_key, scope"


def _hybrid(similarity: float, importance: float, created_at: datetime, scope: str) -> float:
    hours = max(0.0, (datetime.now() - created_at).total_seconds() / 3600.0)
    recency = 0.995 ** hours
    scope_w = SCOPE_IMPORTANCE_WEIGHT.get(scope, 0.5)
    return 0.50 * similarity + 0.20 * importance + 0.15 * recency + 0.15 * scope_w


class SqliteVecMemoryService:
    """MemoryService (pgvector) ile aynı arayüz — gömülü sqlite-vec üzerinde."""

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
        if scope not in VALID_SCOPES:
            scope = "conversation"
        # Sekme bağlamı hafızaya girmez — kullanıcı kurulumu BU servisi kullanır (memory.py'deki
        # kapı tek başına kullanıcıyı korumaz)
        content = sekme_baglamini_ayikla(content)
        if not content:
            return None
        char_key = character_key or _get_active_character()
        vec = await _embed(content)
        blob = _serialize(vec)
        created = _now_iso()

        def _do(conn):
            cur = conn.execute(
                "INSERT INTO memories (session_id, role, content, category, importance, created_at, scope, character_key) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (session_id, role, content, category, importance, created, scope, char_key),
            )
            rid = cur.lastrowid
            conn.execute(
                "INSERT INTO vec_memories(memory_id, character_key, embedding) VALUES (?,?,?)",
                (rid, char_key, blob),
            )
            conn.commit()
            return rid

        rid = await _run(_do)
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
        char_key = character_key or _get_active_character()
        vec = await _embed(query)
        blob = _serialize(vec)
        # KNN'i cömert over-fetch ile al → metadata filtre + hibrit skoru Python'da uygula
        k = min(max(limit * 10, 50), 500)

        def _do(conn):
            if cross_character:
                knn = conn.execute(
                    f"SELECT memory_id, distance FROM vec_memories "
                    f"WHERE embedding MATCH ? AND k = {k} ORDER BY distance",
                    (blob,),
                ).fetchall()
            else:
                knn = conn.execute(
                    f"SELECT memory_id, distance FROM vec_memories "
                    f"WHERE embedding MATCH ? AND character_key = ? AND k = {k} ORDER BY distance",
                    (blob, char_key),
                ).fetchall()
            if not knn:
                return []
            sim_by_id = {row[0]: (1.0 - row[1]) for row in knn}
            ids = list(sim_by_id.keys())
            ph = ",".join("?" * len(ids))
            meta_filters = "AND session_id = ?"
            params: list = list(ids) + [session_id]
            if category:
                meta_filters += " AND category = ?"; params.append(category)
            if scope:
                meta_filters += " AND scope = ?"; params.append(scope)
            rows = conn.execute(
                f"SELECT {_COLS} FROM memories WHERE id IN ({ph}) {meta_filters}",
                params,
            ).fetchall()
            return rows, sim_by_id

        res = await _run(_do)
        if not res:
            return []
        rows, sim_by_id = res
        scored: list[tuple[float, Memory]] = []
        for r in rows:
            sim = sim_by_id.get(r[0], 0.0)
            if sim < min_similarity:
                continue
            mem = _row_to_memory(r, similarity=sim)
            scored.append((_hybrid(sim, r[5], mem.created_at, r[8]), mem))
        scored.sort(key=lambda t: t[0], reverse=True)
        # Sıra-duyarlı kapı: en iyi benzerliğe göre göreli eleme (mutlak taban yukarıda).
        from app.config import MEMORY_REL_RATIO
        from app.services.memory_gate import filter_relative
        kept = filter_relative(
            [m for _, m in scored], floor=min_similarity, ratio=MEMORY_REL_RATIO
        )
        return kept[:limit]

    async def get_recent(
        self,
        limit: int = 20,
        session_id: str = SESSION_ID,
        category: str = "conversation",
        character_key: Optional[str] = None,
    ) -> list[Memory]:
        char_key = character_key or _get_active_character()

        def _do(conn):
            return conn.execute(
                f"SELECT {_COLS} FROM memories "
                "WHERE session_id = ? AND category = ? AND character_key = ? "
                "ORDER BY id DESC LIMIT ?",
                (session_id, category, char_key, limit),
            ).fetchall()

        rows = await _run(_do)
        return list(reversed([_row_to_memory(r) for r in rows]))

    async def cleanup(
        self,
        session_id: str = SESSION_ID,
        importance_threshold: float = 0.35,
        days_old: int = 7,
        character_key: Optional[str] = None,
    ) -> int:
        char_key = character_key or _get_active_character()
        cutoff = (datetime.now() - timedelta(days=days_old)).isoformat()

        def _do(conn):
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM memories WHERE session_id=? AND character_key=? "
                "AND category='conversation' AND importance < ? AND created_at < ?",
                (session_id, char_key, importance_threshold, cutoff),
            ).fetchall()]
            if not ids:
                return 0
            ph = ",".join("?" * len(ids))
            conn.execute(f"DELETE FROM memories WHERE id IN ({ph})", ids)
            conn.execute(f"DELETE FROM vec_memories WHERE memory_id IN ({ph})", ids)
            conn.commit()
            return len(ids)

        return await _run(_do)

    async def update(
        self,
        memory_id: int,
        importance: Optional[float] = None,
        content: Optional[str] = None,
        character_key: Optional[str] = None,
    ) -> bool:
        char_key = character_key or _get_active_character()
        if importance is None and content is None:
            return False
        new_vec = await _embed(content) if content is not None else None

        def _do(conn):
            sets, params = [], []
            if importance is not None:
                sets.append("importance = ?"); params.append(importance)
            if content is not None:
                sets.append("content = ?"); params.append(content)
            params += [memory_id, char_key]
            cur = conn.execute(
                f"UPDATE memories SET {', '.join(sets)} WHERE id = ? AND character_key = ?",
                params,
            )
            changed = cur.rowcount == 1
            if changed and new_vec is not None:
                # embedding değişti → vec satırını tazele (partition key sabit kalır)
                conn.execute("DELETE FROM vec_memories WHERE memory_id = ?", (memory_id,))
                conn.execute(
                    "INSERT INTO vec_memories(memory_id, character_key, embedding) VALUES (?,?,?)",
                    (memory_id, char_key, _serialize(new_vec)),
                )
            conn.commit()
            return changed

        return await _run(_do)

    async def delete(self, memory_id: int, character_key: Optional[str] = None) -> bool:
        char_key = character_key or _get_active_character()

        def _do(conn):
            cur = conn.execute(
                "DELETE FROM memories WHERE id = ? AND character_key = ?",
                (memory_id, char_key),
            )
            ok = cur.rowcount == 1
            if ok:
                conn.execute("DELETE FROM vec_memories WHERE memory_id = ?", (memory_id,))
            conn.commit()
            return ok

        return await _run(_do)

    async def clear_conversations(
        self,
        session_id: str = SESSION_ID,
        character_key: Optional[str] = None,
    ) -> int:
        """Bir oturumun 'conversation' anılarını sil (fact/preference KALIR).

        pgvector MemoryService.clear_conversations ile birebir davranış — vec
        tablosu da temizlenir (yetim vektör kalmaz).
        """
        char_key = character_key or _get_active_character()

        def _do(conn):
            rows = conn.execute(
                "SELECT id FROM memories WHERE session_id = ? AND character_key = ? "
                "AND category = 'conversation'",
                (session_id, char_key),
            ).fetchall()
            ids = [r[0] for r in rows]
            if not ids:
                return 0
            marks = ",".join("?" * len(ids))
            conn.execute(f"DELETE FROM memories WHERE id IN ({marks})", ids)
            conn.execute(f"DELETE FROM vec_memories WHERE memory_id IN ({marks})", ids)
            conn.commit()
            return len(ids)

        return await _run(_do)

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
        char_key = character_key or _get_active_character()

        def _do(conn):
            filters, params = "", [session_id, char_key]
            if icerik:
                filters += " AND arama_katla(content) LIKE ? ESCAPE '\\'"; params.append(arama_kalibi(icerik))
            if category:
                filters += " AND category = ?"; params.append(category)
            if scope:
                filters += " AND scope = ?"; params.append(scope)
            params += [limit, offset]
            return conn.execute(
                f"SELECT {_COLS} FROM memories "
                f"WHERE session_id = ? AND character_key = ? {filters} "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()

        rows = await _run(_do)
        return [_row_to_memory(r) for r in rows]

    async def add_batch(
        self,
        items: list[dict],
        session_id: str = SESSION_ID,
        character_key: Optional[str] = None,
    ) -> list[int]:
        char_key = character_key or _get_active_character()
        # Sekme bağlamı hafızaya girmez (bkz. add); dedup'tan önce
        items = [dict(it, content=sekme_baglamini_ayikla(it["content"])) for it in items]
        items = [it for it in items if it["content"]]
        # In-batch dedup (role, content)
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
        created = _now_iso()
        cutoff = (datetime.now() - timedelta(seconds=60)).isoformat()

        def _do(conn):
            recent = {
                (r[0], r[1]) for r in conn.execute(
                    "SELECT role, content FROM memories "
                    "WHERE session_id=? AND character_key=? AND created_at > ?",
                    (session_id, char_key, cutoff),
                ).fetchall()
            }
            ids: list[int] = []
            for item, vec in zip(items, vecs):
                key = (item.get("role", "user"), item["content"])
                if key in recent:
                    continue
                scope = item.get("scope", item.get("category", "conversation"))
                if scope not in VALID_SCOPES:
                    scope = "conversation"
                cur = conn.execute(
                    "INSERT INTO memories (session_id, role, content, category, importance, created_at, scope, character_key) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (session_id, item.get("role", "user"), item["content"],
                     item.get("category", "conversation"), item.get("importance", 0.5),
                     created, scope, char_key),
                )
                rid = cur.lastrowid
                conn.execute(
                    "INSERT INTO vec_memories(memory_id, character_key, embedding) VALUES (?,?,?)",
                    (rid, char_key, _serialize(vec)),
                )
                ids.append(rid)
            conn.commit()
            return ids

        return await _run(_do)

    async def count(
        self,
        session_id: str = SESSION_ID,
        character_key: Optional[str] = None,
    ) -> int:
        char_key = character_key or _get_active_character()

        def _do(conn):
            r = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE session_id=? AND character_key=?",
                (session_id, char_key),
            ).fetchone()
            return r[0] if r else 0

        return await _run(_do)

    async def reinforce(self, memory_ids: list[int], delta: float = 0.03, character_key: Optional[str] = None) -> None:
        if not memory_ids:
            return
        char_key = character_key or _get_active_character()

        def _do(conn):
            ph = ",".join("?" * len(memory_ids))
            conn.execute(
                f"UPDATE memories SET importance = MIN(1.0, importance + ?) "
                f"WHERE id IN ({ph}) AND character_key = ?",
                [delta] + list(memory_ids) + [char_key],
            )
            conn.commit()

        await _run(_do)

    async def consolidate_facts(
        self,
        session_id: str = SESSION_ID,
        threshold: float = 0.92,
        character_key: Optional[str] = None,
    ) -> int:
        """fact/preference anılarını brute-force cosine ile karşılaştır, eski yinelenenleri sil.

        Ürün ölçeği küçük (tek kullanıcı) → tüm fact/preference vektörlerini çekip
        çiftler arası cosine hesaplamak yeterince hızlı (numpy).
        """
        char_key = character_key or _get_active_character()

        def _fetch(conn):
            return conn.execute(
                "SELECT m.id, m.created_at, v.embedding FROM memories m "
                "JOIN vec_memories v ON v.memory_id = m.id "
                "WHERE m.session_id=? AND m.character_key=? AND m.scope IN ('fact','preference') "
                "ORDER BY m.created_at ASC",
                (session_id, char_key),
            ).fetchall()

        rows = await _run(_fetch)
        if len(rows) < 2:
            return 0
        import numpy as np
        ids = [r[0] for r in rows]
        vecs = np.array([struct.unpack("%df" % EMBED_DIM, r[2]) for r in rows], dtype=np.float32)
        # normalize (embed zaten normalize; garanti için)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vecs = vecs / norms
        sims = vecs @ vecs.T  # cosine (satırlar created_at ASC sıralı)
        to_delete: set[int] = set()
        n = len(ids)
        for i in range(n):
            if ids[i] in to_delete:
                continue
            for j in range(i + 1, n):
                if ids[j] in to_delete:
                    continue
                if sims[i, j] >= threshold:
                    to_delete.add(ids[i])  # i eski (ASC) → sil
                    break
        if not to_delete:
            return 0
        dids = list(to_delete)

        def _del(conn):
            ph = ",".join("?" * len(dids))
            conn.execute(f"DELETE FROM memories WHERE id IN ({ph})", dids)
            conn.execute(f"DELETE FROM vec_memories WHERE memory_id IN ({ph})", dids)
            conn.commit()
            return len(dids)

        return await _run(_del)

    async def stats(
        self,
        session_id: str = SESSION_ID,
        character_key: Optional[str] = None,
    ) -> dict:
        char_key = character_key or _get_active_character()

        def _do(conn):
            total = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE session_id=? AND character_key=?",
                (session_id, char_key),
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT scope, COUNT(*), AVG(importance) FROM memories "
                "WHERE session_id=? AND character_key=? GROUP BY scope ORDER BY COUNT(*) DESC",
                (session_id, char_key),
            ).fetchall()
            # 🔴 Süzgeç `category` ile filtreliyor, `scope` başka bir kavram
            #    (hibrit skor ağırlığı). Ayrıntı: `memory.py::stats` yorumu.
            kat = conn.execute(
                "SELECT category, COUNT(*) FROM memories "
                "WHERE session_id=? AND character_key=? GROUP BY category",
                (session_id, char_key),
            ).fetchall()
            return total, rows, kat

        total, rows, kat = await _run(_do)
        scopes = {
            r[0]: {"count": r[1], "avg_importance": round(float(r[2]), 3)}
            for r in rows
        }
        return {"total": total, "scopes": scopes,
                "categories": {r[0]: r[1] for r in kat},
                "character_key": char_key}

    async def sekme_baglami_temizle(self) -> dict:
        """Eski sürümlerin hafızaya yanlış yazdıklarını BİR KEZ düzeltir (açılışta çağrılır).

        1e508d4'ten önce ① her kullanıcı mesajı [TAB_CONTEXT …] bloğuyla yazılıyordu,
        ② Yuki'nin cevabı ve ③ "?" ile biten sorular kullanıcının kapsamıyla (bilgi/tercih/
        beceri) kaydediliyordu. Yeni yazımlar temiz; bu, kullanıcının ESKİ kayıtları içindir.
        ② ve ③ yalnız `_save_exchange` imzası taşıyan satırlara dokunur (category = scope):
        `/öğren` satırları category='conversation' olduğu için korunur.
        Kendiliğinden tekrarsız: düzeltilecek satır yoksa hiçbir şey yazmaz, yedek almaz.
        Değişiklikten önce veritabanının tam kopyası DATA_DIR/yedek/ altına alınır.
        """
        import os
        import sqlite3
        from app import config

        if not os.path.exists(MEMORY_DB_PATH):
            return {}   # hiç hafızası olmayan kurulumda boş veritabanı yaratma

        def _say(conn):
            bloklu = conn.execute(
                "SELECT id, character_key, content FROM memories WHERE content LIKE '%[TAB_CONTEXT%'"
            ).fetchall()
            cevap = conn.execute(
                "SELECT id FROM memories WHERE role='assistant' AND scope != 'conversation' "
                "AND category = scope"
            ).fetchall()
            soru = conn.execute(
                "SELECT id FROM memories WHERE role='user' AND scope != 'conversation' "
                "AND category = scope AND rtrim(content) LIKE '%?'"
            ).fetchall()
            return bloklu, [r[0] for r in cevap], [r[0] for r in soru]

        bloklu, cevap_ids, soru_ids = await _run(_say)
        if not (bloklu or cevap_ids or soru_ids):
            return {}

        yedek_dizin = config.DATA_DIR / "yedek"
        yedek_dizin.mkdir(parents=True, exist_ok=True)
        yedek = yedek_dizin / f"hafiza-sekme-{datetime.now():%Y%m%d-%H%M%S}.db"

        def _yedekle(conn):
            with sqlite3.connect(str(yedek)) as hedef:
                conn.backup(hedef)

        await _run(_yedekle)

        temiz = [(rid, ck, sekme_baglamini_ayikla(c)) for rid, ck, c in bloklu]
        guncel = [t for t in temiz if t[2]]
        silinecek = [t[0] for t in temiz if not t[2]]
        vecs = await _embed_batch([t[2] for t in guncel]) if guncel else []

        def _yaz(conn):
            try:
                return _yaz_islem(conn)
            except Exception:
                # Bağlantı paylaşılıyor: geri alınmazsa sonraki sıradan commit yarım temizliği yazar
                conn.rollback()
                raise

        def _yaz_islem(conn):
            for (rid, ck, metin), vec in zip(guncel, vecs):
                conn.execute("UPDATE memories SET content = ? WHERE id = ?", (metin, rid))
                conn.execute("DELETE FROM vec_memories WHERE memory_id = ?", (rid,))
                conn.execute(
                    "INSERT INTO vec_memories(memory_id, character_key, embedding) VALUES (?,?,?)",
                    (rid, ck, _serialize(vec)),
                )
            for rid in silinecek:
                conn.execute("DELETE FROM memories WHERE id = ?", (rid,))
                conn.execute("DELETE FROM vec_memories WHERE memory_id = ?", (rid,))
            conn.execute(
                "UPDATE memories SET scope='conversation', category='conversation', importance=0.5 "
                "WHERE role='assistant' AND scope != 'conversation' AND category = scope"
            )
            # Soru kuralı blok kesildikten SONRA sayılır: "ne?[TAB_CONTEXT…]" satırı ancak
            # blok gidince '?' ile biter — ilk sayımdaki soru_ids bu yüzden yalnız tetikleyici.
            n_soru = conn.execute(
                "UPDATE memories SET scope='conversation', category='conversation', importance=0.5 "
                "WHERE role='user' AND scope != 'conversation' AND category = scope "
                "AND rtrim(content) LIKE '%?'"
            ).rowcount
            conn.commit()
            return n_soru

        n_soru = await _run(_yaz)
        return {
            "blok_temizlendi": len(guncel),
            "silindi": len(silinecek),
            "cevap_konusma": len(cevap_ids),
            "soru_konusma": n_soru,
            "yedek": str(yedek),
        }

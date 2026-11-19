"""
Yuki — Custom Todo Sistemi
Endpoint prefix: /api/todo

DB: PostgreSQL (mevcut asyncpg pool) — kişisel Alice / self-host.
Postgres YOKSA (satılan AppImage/zip: `electron/main.js` pakete Postgres koymaz)
her uç `app.services.todo_store`'a düşer. Eskiden bu durumda tüm PLAN ekranı 503
dönüyordu; Yuki sohbetten görev ekleyebiliyor ama ekranda göremiyordun.

Kural: PG dalı DEĞİŞMEZ (parite), depo dalı yalnızca havuz None'ken devreye girer.
"""
from __future__ import annotations

import math
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.limiter import limiter
from app.db.connection import get_pool
from app.services import todo_store
from app.mesajlar import M

logger = logging.getLogger(__name__)


def require_planner() -> None:
    """PLAN ekranı (görsel planlayıcı) Pro özelliğidir — vitrindeki söz bu.

    Free'de görev yönetimi Yuki'yle KONUŞARAK yapılır (create_todo/list_todos/
    complete_todo P1 araçları) — o yol bu kapıdan geçmez, açık kalır. Kapatılan
    tek şey ekranın REST yüzeyi. Router düzeyinde: yeni uç eklenince kapıyı
    yazmayı unutmak imkânsız (memory.py'de tek tek yazılıyordu, bir uç atlanmıştı).
    """
    try:
        from app.services import yetki
        allowed = yetki.feature_allowed("planner")
    except Exception:
        allowed = False        # hata → kapalı (üst kademe sızmasın)
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=M("kademe.plan-pro"),
        )


router = APIRouter(prefix="/api/todo", tags=["todo"],
                   dependencies=[Depends(require_planner)])

_INIT_SQL = Path(__file__).parent.parent / "db" / "todo_init.sql"


# priority metin: `ORDER BY priority DESC` sırası mid, low, high çıkar (alfabetik).
# Depo yolu (`todo_store._prio_key`) high önce sıralıyor; PG yolu da öyle yapmalı.
_ONCELIK_SIRA = "CASE t.priority WHEN 'high' THEN 0 WHEN 'mid' THEN 1 ELSE 2 END"


# ── DB init ────────────────────────────────────────────────────────────────────

async def init_todo_db() -> None:
    """Todo tablolarını oluştur (idempotent)."""
    pool = await get_pool()
    if pool is None:
        # Ürün paketi: Postgres yok → gömülü JSON depo. Uyarı DEĞİL, normal mod.
        todo_store.get_lists()      # dosyayı kur + eski todos.json'ı taşı
        logger.info("Todo: PostgreSQL yok → gömülü depo (todo_store.json) kullanılıyor")
        return
    async with pool.acquire() as conn:
        await conn.execute(_INIT_SQL.read_text(encoding="utf-8"))
    logger.info("Todo DB hazır.")


# ── Yardımcılar ────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _yerel_bugun() -> date:
    """Takvim günü YEREL saatle. Bütçe günü/ayı UTC'den alınınca UTC+3'te gece 00-03 arası
    kayıt önceki güne, ayın 1'inde önceki aya yazılıyordu; Yuki'nin bütçe aracı ve
    todo_store zaten yerel `date.today()` kullanıyor."""
    return datetime.now().date()


async def _pool():
    """Postgres havuzu. None dönerse çağıran uç todo_store'a düşer."""
    return await get_pool()


def _row(r) -> dict:
    return dict(r)


def _rows(rs) -> list[dict]:
    return [dict(r) for r in rs]


# ══════════════════════════════════════════════════════════════════════════════
# LISTELER
# ══════════════════════════════════════════════════════════════════════════════

class ListCreate(BaseModel):
    name: str
    color: str = "cyan"
    icon: str = "⬡"


class ListUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    icon: str | None = None
    position: float | None = None


@router.get("/lists")
@limiter.limit("100/minute")
async def get_lists(request: Request):

    """Tüm listeler + her liste için görev sayısı."""
    pool = await _pool()
    if pool is None:
        return todo_store.get_lists()
    async with pool.acquire() as conn:
        lists = await conn.fetch("""
            SELECT l.*,
                   COUNT(t.id) FILTER (WHERE t.completed_at IS NULL AND NOT t.is_archived) AS open_count,
                   COUNT(t.id) FILTER (WHERE t.completed_at IS NOT NULL)                   AS done_count
            FROM todo_lists l
            LEFT JOIN todo_tasks t ON t.list_id = l.id
            WHERE NOT l.is_archived
            GROUP BY l.id
            ORDER BY l.position, l.created_at
        """)
    return {"lists": _rows(lists)}


@router.post("/lists", status_code=201)
@limiter.limit("30/minute")
async def create_list(request: Request, body: ListCreate):

    pool = await _pool()
    if pool is None:
        return todo_store.create_list(body.name, body.color, body.icon)
    async with pool.acquire() as conn:
        max_pos = await conn.fetchval("SELECT COALESCE(MAX(position),0) FROM todo_lists")
        row = await conn.fetchrow("""
            INSERT INTO todo_lists (id, name, color, icon, position)
            VALUES ($1,$2,$3,$4,$5) RETURNING *
        """, str(uuid4()), body.name, body.color, body.icon, (max_pos or 0) + 1)
    return _row(row)


@router.patch("/lists/{list_id}")
@limiter.limit("30/minute")
async def update_list(request: Request, list_id: str, body: ListUpdate):

    pool = await _pool()
    if pool is None:
        row = todo_store.update_list(list_id, body.name, body.color, body.icon, body.position)
        if not row:
            raise HTTPException(404, M("todo.liste-yok"))
        return row
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            UPDATE todo_lists
            SET name = COALESCE($2, name),
                color = COALESCE($3, color),
                icon = COALESCE($4, icon),
                position = COALESCE($5, position)
            WHERE id=$1 RETURNING *
        """, list_id, body.name, body.color, body.icon, body.position)
        if not row:
            raise HTTPException(404, M("todo.liste-yok"))
    return _row(row)


@router.delete("/lists/{list_id}")
@limiter.limit("30/minute")
async def delete_list(request: Request, list_id: str):

    pool = await _pool()
    if pool is None:
        todo_store.delete_list(list_id)
        return {"ok": True}
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE todo_tasks SET deleted_at=$2 WHERE list_id=$1 AND deleted_at IS NULL",
            list_id, _now()
        )
        await conn.execute(
            "UPDATE todo_lists SET is_archived=TRUE WHERE id=$1", list_id
        )
    return {"ok": True}


class ReorderLists(BaseModel):
    ordered_ids: list[str]   # id listesi, istenen sırayla


@router.post("/lists/reorder")
@limiter.limit("30/minute")
async def reorder_lists(request: Request, body: ReorderLists):

    pool = await _pool()
    if pool is None:
        todo_store.reorder_lists(body.ordered_ids)
        return {"ok": True}
    async with pool.acquire() as conn:
        async with conn.transaction():
            for i, lid in enumerate(body.ordered_ids):
                await conn.execute(
                    "UPDATE todo_lists SET position=$2 WHERE id=$1", lid, float(i)
                )
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# GÖREVLER
# ══════════════════════════════════════════════════════════════════════════════

class TaskCreate(BaseModel):
    title: str
    notes: str = ""
    priority: str = "mid"
    status: str = "todo"              # todo | in_progress | blocked | done
    start_date: str | None = None    # "YYYY-MM-DD"
    due_date: str | None = None      # "YYYY-MM-DD"
    reminder_at: str | None = None   # ISO datetime
    repeat: str = "none"
    tags: list[str] = []
    estimated_time: int | None = None  # dakika (#8)
    section_name: str | None = None    # section (#12)


class TaskUpdate(BaseModel):
    title: str | None = None
    notes: str | None = None
    priority: str | None = None
    status: str | None = None
    start_date: str | None = None
    due_date: str | None = None
    reminder_at: str | None = None
    repeat: str | None = None
    tags: list[str] | None = None
    position: float | None = None
    estimated_time: int | None = None  # dakika (#8)
    section_name: str | None = None    # section (#12)


_VALID_REPEATS = {"none", "daily", "weekdays", "weekly", "biweekly", "monthly", "yearly"}

def _validate_repeat(v: str) -> str:
    if v in _VALID_REPEATS:
        return v
    if v.startswith("custom:") and v[7:].isdigit() and int(v[7:]) > 0:
        return v
    return "none"


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


# Depo dalı ISO metin saklar; PG dalı geçersiz tarihi None'a çevirdiği için
# aynı normalleştirmeyi burada da yaparız → iki yol aynı şeyi döndürür.
def _iso_date(s: str | None) -> str | None:
    d = _parse_date(s)
    return d.isoformat() if d else None


def _iso_dt(s: str | None) -> str | None:
    d = _parse_dt(s)
    return d.isoformat() if d else None


@router.get("/lists/{list_id}/tasks")
@limiter.limit("100/minute")
async def get_tasks(request: Request, list_id: str, include_completed: bool = False):

    pool = await _pool()
    if pool is None:
        return todo_store.get_tasks(list_id, include_completed)
    filter_clause = "" if include_completed else "AND t.completed_at IS NULL"
    async with pool.acquire() as conn:
        tasks = await conn.fetch(f"""
            SELECT t.*,
                   array_agg(s.id ORDER BY s.position) FILTER (WHERE s.id IS NOT NULL) AS subtask_ids
            FROM todo_tasks t
            LEFT JOIN todo_subtasks s ON s.task_id = t.id
            WHERE t.list_id=$1 AND NOT t.is_archived AND t.deleted_at IS NULL {filter_clause}
            GROUP BY t.id
            ORDER BY t.section_name NULLS LAST, t.position, t.created_at
        """, list_id)
        # subtask detayları
        result = []
        for t in tasks:
            d = _row(t)
            if d.get("subtask_ids"):
                subs = await conn.fetch(
                    "SELECT * FROM todo_subtasks WHERE task_id=$1 ORDER BY position", t["id"]
                )
                d["subtasks"] = _rows(subs)
            else:
                d["subtasks"] = []
            d.pop("subtask_ids", None)
            result.append(d)
    return {"tasks": result}


@router.post("/lists/{list_id}/tasks", status_code=201)
@limiter.limit("30/minute")
async def create_task(request: Request, list_id: str, body: TaskCreate):

    pool = await _pool()
    if pool is None:
        if not todo_store.list_exists(list_id):
            raise HTTPException(404, M("todo.liste-yok"))
        return todo_store.create_task(
            list_id, title=body.title, notes=body.notes or None,
            priority=body.priority, status=body.status,
            start_date=_iso_date(body.start_date), due_date=_iso_date(body.due_date),
            reminder_at=_iso_dt(body.reminder_at), repeat=_validate_repeat(body.repeat),
            tags=body.tags, estimated_time=body.estimated_time,
            section_name=body.section_name,
        )
    async with pool.acquire() as conn:
        lst = await conn.fetchrow("SELECT id FROM todo_lists WHERE id=$1 AND NOT is_archived", list_id)
        if not lst:
            raise HTTPException(404, M("todo.liste-yok"))
        max_pos = await conn.fetchval(
            "SELECT COALESCE(MAX(position),0) FROM todo_tasks WHERE list_id=$1", list_id
        )
        row = await conn.fetchrow("""
            INSERT INTO todo_tasks
              (id, list_id, title, notes, priority, status, start_date, due_date, reminder_at, repeat, tags, position, estimated_time, section_name)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
            RETURNING *
        """,
            str(uuid4()), list_id, body.title, body.notes or None,
            body.priority, body.status, _parse_date(body.start_date), _parse_date(body.due_date),
            _parse_dt(body.reminder_at), _validate_repeat(body.repeat), body.tags, (max_pos or 0) + 1,
            body.estimated_time, body.section_name,
        )
    return {**_row(row), "subtasks": []}


@router.patch("/tasks/{task_id}")
@limiter.limit("30/minute")
async def update_task(request: Request, task_id: str, body: TaskUpdate):

    pool = await _pool()
    if pool is None:
        # Yalnız GÖNDERİLEN alanlar sözlüğe girer (PG'deki COALESCE mantığı);
        # gönderilen ama boş olan tarih alanı None olur = temizle.
        fields: dict[str, Any] = {}
        for name in ("title", "notes", "priority", "status", "tags",
                     "position", "estimated_time", "section_name"):
            val = getattr(body, name)
            if val is not None:
                fields[name] = val
        if body.start_date is not None:
            fields["start_date"] = _iso_date(body.start_date)
        if body.due_date is not None:
            fields["due_date"] = _iso_date(body.due_date)
        if body.reminder_at is not None:
            fields["reminder_at"] = _iso_dt(body.reminder_at)
        if body.repeat is not None:
            fields["repeat"] = _validate_repeat(body.repeat)
        row = todo_store.update_task(task_id, fields)
        if not row:
            raise HTTPException(404, M("todo.gorev-yok"))
        return row
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM todo_tasks WHERE id=$1", task_id)
        if not row:
            raise HTTPException(404, M("todo.gorev-yok"))
        title      = body.title      if body.title      is not None else row["title"]
        notes      = body.notes      if body.notes      is not None else row["notes"]
        priority   = body.priority   if body.priority   is not None else row["priority"]
        status     = body.status     if body.status     is not None else row["status"]
        start_date = _parse_date(body.start_date) if body.start_date is not None else row["start_date"]
        due_date   = _parse_date(body.due_date) if body.due_date is not None else row["due_date"]
        reminder   = _parse_dt(body.reminder_at) if body.reminder_at is not None else row["reminder_at"]
        repeat     = _validate_repeat(body.repeat) if body.repeat is not None else row["repeat"]
        tags       = body.tags       if body.tags       is not None else list(row["tags"] or [])
        position   = body.position   if body.position   is not None else row["position"]
        estimated_time = body.estimated_time if body.estimated_time is not None else row.get("estimated_time")
        section_name   = body.section_name   if body.section_name   is not None else row.get("section_name")
        row = await conn.fetchrow("""
            UPDATE todo_tasks
            SET title=$2, notes=$3, priority=$4, status=$5, start_date=$6, due_date=$7,
                reminder_at=$8, repeat=$9, tags=$10, position=$11, estimated_time=$12, section_name=$13
            WHERE id=$1 RETURNING *
        """, task_id, title, notes, priority, status, start_date, due_date, reminder, repeat, tags, position,
            estimated_time, section_name)
    return _row(row)


@router.delete("/tasks/{task_id}")
@limiter.limit("30/minute")
async def delete_task(request: Request, task_id: str):

    """Görevi çöp kutusuna taşır (soft delete, #13)."""
    pool = await _pool()
    if pool is None:
        todo_store.delete_task(task_id)
        return {"ok": True}
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE todo_tasks SET deleted_at=$2 WHERE id=$1", task_id, _now()
        )
    return {"ok": True}


@router.get("/trash")
@limiter.limit("100/minute")
async def get_trash(request: Request):

    """Çöp kutusundaki görevler (#13). 30 günden eski olanlar otomatik temizlenir."""
    pool = await _pool()
    if pool is None:
        return todo_store.get_trash()
    async with pool.acquire() as conn:
        # 30 günden eski soft-deleted görevleri kalıcı sil
        await conn.execute(
            "DELETE FROM todo_tasks WHERE deleted_at IS NOT NULL AND deleted_at < NOW() - INTERVAL '30 days'"
        )
        tasks = await conn.fetch("""
            SELECT t.*, l.name AS list_name
            FROM todo_tasks t
            JOIN todo_lists l ON l.id = t.list_id
            WHERE t.deleted_at IS NOT NULL
            ORDER BY t.deleted_at DESC
        """)
    return {"tasks": _rows(tasks)}


@router.post("/tasks/{task_id}/restore")
@limiter.limit("30/minute")
async def restore_task(request: Request, task_id: str):

    """Görevi çöp kutusundan geri yükle (#13)."""
    pool = await _pool()
    if pool is None:
        if not todo_store.restore_task(task_id):
            raise HTTPException(404, M("todo.gorev-zaten-aktif"))
        return {"ok": True}
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE todo_tasks SET deleted_at=NULL WHERE id=$1 AND deleted_at IS NOT NULL RETURNING id",
            task_id
        )
    if not row:
        raise HTTPException(404, M("todo.gorev-zaten-aktif"))
    return {"ok": True}


@router.delete("/tasks/{task_id}/permanent")
@limiter.limit("30/minute")
async def permanent_delete_task(request: Request, task_id: str):

    """Görevi kalıcı olarak sil (çöp kutusundan) (#13)."""
    pool = await _pool()
    if pool is None:
        if not todo_store.permanent_delete_task(task_id):
            raise HTTPException(404, M("todo.gorev-copte-degil"))
        return {"ok": True}
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "DELETE FROM todo_tasks WHERE id=$1 AND deleted_at IS NOT NULL RETURNING id",
            task_id
        )
    if not row:
        raise HTTPException(404, M("todo.gorev-copte-degil"))
    return {"ok": True}


@router.post("/tasks/{task_id}/complete")
@limiter.limit("30/minute")
async def complete_task(request: Request, task_id: str):

    pool = await _pool()
    if pool is None:
        row = todo_store.complete_task(task_id)   # tekrarlı görev klonu depoda
        if not row:
            raise HTTPException(404, M("todo.gorev-yok"))
        return row
    async with pool.acquire() as conn:
        # Yalnız AÇIK görevi kapat: çift tık / ağ tekrarı ikinci klon açmasın.
        row = await conn.fetchrow(
            "UPDATE todo_tasks SET completed_at=$2 WHERE id=$1 AND completed_at IS NULL RETURNING *",
            task_id, _now()
        )
        if not row:
            mevcut = await conn.fetchrow("SELECT * FROM todo_tasks WHERE id=$1", task_id)
            if not mevcut:
                raise HTTPException(404, M("todo.gorev-yok"))
            return _row(mevcut)
    # Tekrarlayan görev → yeni klon
    if row["repeat"] != "none" and row["due_date"]:
        await _clone_recurring(row)
    return _row(row)


@router.post("/tasks/{task_id}/uncomplete")
@limiter.limit("30/minute")
async def uncomplete_task(request: Request, task_id: str):

    pool = await _pool()
    if pool is None:
        todo_store.uncomplete_task(task_id)
        return {"ok": True}
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE todo_tasks SET completed_at=NULL WHERE id=$1", task_id
        )
    return {"ok": True}


class ReorderTasks(BaseModel):
    ordered_ids: list[str]


@router.post("/tasks/reorder")
@limiter.limit("30/minute")
async def reorder_tasks(request: Request, body: ReorderTasks):

    pool = await _pool()
    if pool is None:
        todo_store.reorder_tasks(body.ordered_ids)
        return {"ok": True}
    async with pool.acquire() as conn:
        async with conn.transaction():
            for i, tid in enumerate(body.ordered_ids):
                await conn.execute(
                    "UPDATE todo_tasks SET position=$2 WHERE id=$1", tid, float(i)
                )
    return {"ok": True}


class BulkComplete(BaseModel):
    ids: list[str]


@router.post("/tasks/bulk-complete")
@limiter.limit("30/minute")
async def bulk_complete(request: Request, body: BulkComplete):

    pool = await _pool()
    if pool is None:
        return {"ok": True, "count": todo_store.bulk_complete(body.ids)}
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE todo_tasks SET completed_at=$1 WHERE id=ANY($2::uuid[])",
            _now(), body.ids
        )
    return {"ok": True, "count": len(body.ids)}


# ── Tekrarlayan görev klonu ────────────────────────────────────────────────────

async def _clone_recurring(row: Any) -> None:
    from datetime import timedelta
    pool = await get_pool()
    if not pool:
        return
    due: date | None = row["due_date"]
    if not due:
        return
    # Tarih kuralı tek yerde (SQLite yoluyla aynı): hafta içi / 2 haftada / yıllık / özel
    # dahil; ay sonu kırpılır (31 Ocak → 28 Şubat).
    new_due = todo_store.sonraki_tarih(due, row["repeat"] or "none")
    if new_due is None:
        if (row["repeat"] or "none") != "none":
            logger.warning("tekrarlı görev klonlanamadı: bilinmeyen tekrar %r", row["repeat"])
        return
    async with pool.acquire() as conn:
        max_pos = await conn.fetchval(
            "SELECT COALESCE(MAX(position),0) FROM todo_tasks WHERE list_id=$1", row["list_id"]
        )
        await conn.execute("""
            INSERT INTO todo_tasks
              (id, list_id, title, notes, priority, due_date, repeat, tags, position)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        """,
            str(uuid4()), row["list_id"], row["title"], row["notes"],
            row["priority"], new_due, row["repeat"], list(row["tags"] or []),
            (max_pos or 0) + 1,
        )


# ══════════════════════════════════════════════════════════════════════════════
# BAĞIMLILIKLAR (#11)
# ══════════════════════════════════════════════════════════════════════════════

class DepCreate(BaseModel):
    depends_on: str   # task UUID


@router.get("/tasks/{task_id}/dependencies")
@limiter.limit("100/minute")
async def get_dependencies(request: Request, task_id: str):

    """Görevin bağımlılıklarını ve bağımlılarını döndürür."""
    pool = await _pool()
    if pool is None:
        return todo_store.get_dependencies(task_id)
    async with pool.acquire() as conn:
        # Bu görev hangi görevlere bağlı? (blocked by)
        blocked_by = await conn.fetch("""
            SELECT t.id, t.title, t.completed_at, t.priority, t.due_date
            FROM todo_dependencies d
            JOIN todo_tasks t ON t.id = d.depends_on
            WHERE d.task_id=$1 AND t.deleted_at IS NULL
        """, task_id)
        # Hangi görevler bu göreve bağlı? (blocks)
        blocks = await conn.fetch("""
            SELECT t.id, t.title, t.completed_at, t.priority, t.due_date
            FROM todo_dependencies d
            JOIN todo_tasks t ON t.id = d.task_id
            WHERE d.depends_on=$1 AND t.deleted_at IS NULL
        """, task_id)
    return {"blocked_by": _rows(blocked_by), "blocks": _rows(blocks)}


@router.post("/tasks/{task_id}/dependencies")
@limiter.limit("30/minute")
async def add_dependency(request: Request, task_id: str, body: DepCreate):

    """Bağımlılık ekle: task_id, depends_on'dan sonra tamamlanmalı."""
    if task_id == body.depends_on:
        raise HTTPException(400, M("todo.kendine-bagimli"))
    pool = await _pool()
    if pool is None:
        todo_store.add_dependency(task_id, body.depends_on)
        return {"ok": True}
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO todo_dependencies (task_id, depends_on) VALUES ($1,$2) ON CONFLICT DO NOTHING",
                task_id, body.depends_on
            )
        except Exception as e:
            raise HTTPException(400, str(e))
    return {"ok": True}


@router.delete("/tasks/{task_id}/dependencies/{dep_id}")
@limiter.limit("30/minute")
async def remove_dependency(request: Request, task_id: str, dep_id: str):

    pool = await _pool()
    if pool is None:
        todo_store.remove_dependency(task_id, dep_id)
        return {"ok": True}
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM todo_dependencies WHERE task_id=$1 AND depends_on=$2",
            task_id, dep_id
        )
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# SUBTASKLAR
# ══════════════════════════════════════════════════════════════════════════════

class SubtaskCreate(BaseModel):
    title: str


class SubtaskUpdate(BaseModel):
    title: str | None = None
    completed: bool | None = None


@router.post("/tasks/{task_id}/subtasks", status_code=201)
@limiter.limit("30/minute")
async def create_subtask(request: Request, task_id: str, body: SubtaskCreate):

    pool = await _pool()
    if pool is None:
        return todo_store.create_subtask(task_id, body.title)
    async with pool.acquire() as conn:
        max_pos = await conn.fetchval(
            "SELECT COALESCE(MAX(position),0) FROM todo_subtasks WHERE task_id=$1", task_id
        )
        row = await conn.fetchrow("""
            INSERT INTO todo_subtasks (id, task_id, title, position)
            VALUES ($1,$2,$3,$4) RETURNING *
        """, str(uuid4()), task_id, body.title, (max_pos or 0) + 1)
    return _row(row)


@router.patch("/tasks/{task_id}/subtasks/{sub_id}")
@limiter.limit("30/minute")
async def update_subtask(request: Request, task_id: str, sub_id: str, body: SubtaskUpdate):

    pool = await _pool()
    if pool is None:
        row = todo_store.update_subtask(task_id, sub_id, body.title, body.completed)
        if not row:
            raise HTTPException(404, M("todo.alt-gorev-yok"))
        return row
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM todo_subtasks WHERE id=$1 AND task_id=$2", sub_id, task_id
        )
        if not row:
            raise HTTPException(404, M("todo.alt-gorev-yok"))
        title = body.title if body.title is not None else row["title"]
        if body.completed is True:
            completed_at = _now()
        elif body.completed is False:
            completed_at = None
        else:
            completed_at = row["completed_at"]
        row = await conn.fetchrow("""
            UPDATE todo_subtasks SET title=$2, completed_at=$3
            WHERE id=$1 RETURNING *
        """, sub_id, title, completed_at)
    return _row(row)


@router.delete("/tasks/{task_id}/subtasks/{sub_id}")
@limiter.limit("30/minute")
async def delete_subtask(request: Request, task_id: str, sub_id: str):

    pool = await _pool()
    if pool is None:
        todo_store.delete_subtask(task_id, sub_id)
        return {"ok": True}
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM todo_subtasks WHERE id=$1 AND task_id=$2", sub_id, task_id
        )
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE CALENDAR SYNC
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/tasks/{task_id}/calendar")
@limiter.limit("30/minute")
async def sync_to_calendar(request: Request, task_id: str):

    """Görevi Google Calendar'a ekle."""
    pool = await _pool()
    if pool is None:
        task = todo_store.get_task(task_id)
    else:
        async with pool.acquire() as conn:
            task = await conn.fetchrow("SELECT * FROM todo_tasks WHERE id=$1", task_id)
    if not task:
        raise HTTPException(404, M("todo.gorev-yok"))
    if not task["due_date"]:
        raise HTTPException(400, M("todo.tarihsiz-takvim"))

    # planner.py'deki Google Calendar API'yi kullan
    try:
        from app.api.planner import _google_token
        import httpx
        access_token = await _google_token()
        # PG dalı date nesnesi, depo dalı ISO metin verir → ikisini de tek biçime indir.
        due_raw = task["due_date"]
        due_str = due_raw.isoformat() if hasattr(due_raw, "isoformat") else str(due_raw)[:10]
        payload = {
            "summary": task["title"],
            "description": task["notes"] or "",
            "start": {"date": due_str},
            "end": {"date": due_str},
        }
        async with httpx.AsyncClient() as c:
            r = await c.post(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            event = r.json()

        pool2 = await _pool()
        if pool2 is None:
            todo_store.set_calendar_link(task_id, event["id"])
        else:
            async with pool2.acquire() as conn:
                await conn.execute(
                    "UPDATE todo_tasks SET calendar_event_id=$2, calendar_synced=TRUE WHERE id=$1",
                    task_id, event["id"]
                )
        return {"ok": True, "event_id": event["id"], "html_link": event.get("htmlLink")}
    except Exception as e:
        # 🔎 2026-08-02: kaynak adı MESAJA yazılıyor. Sebep: geliştiricinin Windows turunda
        # ekranda `401 Missing Authentication header` çıktı ve **iki tur boyunca kimin
        # söylediği bulunamadı** — 5 dış servis tek tek elendi. Yukarı akış metnini
        # kullanıcıya sızdıran uç, KİMİN konuştuğunu da söylemek zorunda; yoksa ekran
        # görüntüsü teşhis için yetersiz kalıyor.
        raise HTTPException(502, M("todo.takvim-esitleme-hatasi", sebep=e))


@router.delete("/tasks/{task_id}/calendar")
@limiter.limit("30/minute")
async def remove_from_calendar(request: Request, task_id: str):

    """Görevi Google Calendar'dan kaldır."""
    pool = await _pool()
    if pool is None:
        task = todo_store.get_task(task_id)
    else:
        async with pool.acquire() as conn:
            task = await conn.fetchrow("SELECT * FROM todo_tasks WHERE id=$1", task_id)
    if not task or not task["calendar_event_id"]:
        raise HTTPException(404, M("todo.takvim-etkinligi-yok"))

    try:
        from app.api.planner import _google_token
        import httpx
        access_token = await _google_token()
        async with httpx.AsyncClient() as c:
            await c.delete(
                f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{task['calendar_event_id']}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        pool2 = await _pool()
        if pool2 is None:
            todo_store.set_calendar_link(task_id, None)
        else:
            async with pool2.acquire() as conn:
                await conn.execute(
                    "UPDATE todo_tasks SET calendar_event_id=NULL, calendar_synced=FALSE WHERE id=$1",
                    task_id
                )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(502, M("todo.takvim-silme-hatasi", sebep=e))


# ══════════════════════════════════════════════════════════════════════════════
# FİLTRE, ARAMA, İSTATİSTİK
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/filter")
@limiter.limit("100/minute")
async def filter_tasks(request: Request, f: str = Query("today")):
    """
    Filtreler:
      today    — bugün bitenler
      week     — bu hafta bitenler
      overdue  — gecikmiş
      priority — öncelik high
      completed — tamamlanmış (son 7 gün)
      archived  — arşivlenenler
    """
    pool = await _pool()
    if pool is None:
        res = todo_store.filter_tasks(f)
        if res is None:
            raise HTTPException(400, M("todo.gecersiz-filtre", filtre=f, gecerli=list(todo_store.FILTERS)))
        return res
    today = date.today()

    queries: dict[str, str] = {
        "today": f"""
            SELECT t.*, l.name AS list_name, l.color AS list_color
            FROM todo_tasks t JOIN todo_lists l ON l.id=t.list_id
            WHERE t.due_date = '{today}' AND t.completed_at IS NULL AND NOT t.is_archived AND t.deleted_at IS NULL
            ORDER BY {_ONCELIK_SIRA}, t.position
        """,
        "week": f"""
            SELECT t.*, l.name AS list_name, l.color AS list_color
            FROM todo_tasks t JOIN todo_lists l ON l.id=t.list_id
            WHERE t.due_date BETWEEN '{today}' AND '{today}'::date + 6 AND t.deleted_at IS NULL
              AND t.completed_at IS NULL AND NOT t.is_archived
            ORDER BY t.due_date, {_ONCELIK_SIRA}
        """,
        "overdue": f"""
            SELECT t.*, l.name AS list_name, l.color AS list_color
            FROM todo_tasks t JOIN todo_lists l ON l.id=t.list_id
            WHERE t.due_date < '{today}' AND t.completed_at IS NULL AND NOT t.is_archived AND t.deleted_at IS NULL
            ORDER BY t.due_date
        """,
        "priority": """
            SELECT t.*, l.name AS list_name, l.color AS list_color
            FROM todo_tasks t JOIN todo_lists l ON l.id=t.list_id
            WHERE t.priority='high' AND t.completed_at IS NULL AND NOT t.is_archived AND t.deleted_at IS NULL
            ORDER BY t.due_date NULLS LAST, t.position
        """,
        "completed": f"""
            SELECT t.*, l.name AS list_name, l.color AS list_color
            FROM todo_tasks t JOIN todo_lists l ON l.id=t.list_id
            WHERE t.completed_at >= NOW() - INTERVAL '7 days' AND t.deleted_at IS NULL
            ORDER BY t.completed_at DESC
        """,
        "archived": """
            SELECT t.*, l.name AS list_name, l.color AS list_color
            FROM todo_tasks t JOIN todo_lists l ON l.id=t.list_id
            WHERE t.is_archived AND t.deleted_at IS NULL
            ORDER BY t.created_at DESC
        """,
        "in_progress": """
            SELECT t.*, l.name AS list_name, l.color AS list_color
            FROM todo_tasks t JOIN todo_lists l ON l.id=t.list_id
            WHERE t.status='in_progress' AND t.completed_at IS NULL AND NOT t.is_archived AND t.deleted_at IS NULL
            ORDER BY t.due_date NULLS LAST, t.position
        """,
        "blocked": """
            SELECT t.*, l.name AS list_name, l.color AS list_color
            FROM todo_tasks t JOIN todo_lists l ON l.id=t.list_id
            WHERE t.status='blocked' AND t.completed_at IS NULL AND NOT t.is_archived AND t.deleted_at IS NULL
            ORDER BY t.due_date NULLS LAST, t.position
        """,
    }
    sql = queries.get(f)
    if not sql:
        raise HTTPException(400, M("todo.gecersiz-filtre", filtre=f, gecerli=list(queries)))

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql)
    return {"filter": f, "tasks": _rows(rows)}


@router.get("/search")
@limiter.limit("100/minute")
async def search_tasks(request: Request, q: str = Query(..., min_length=1)):
    """PostgreSQL full-text search (Türkçe)."""
    pool = await _pool()
    if pool is None:
        return todo_store.search_tasks(q)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT t.*, l.name AS list_name, l.color AS list_color,
                   ts_rank(to_tsvector('turkish', t.title || ' ' || COALESCE(t.notes,'')),
                           plainto_tsquery('turkish',$1)) AS rank
            FROM todo_tasks t JOIN todo_lists l ON l.id=t.list_id
            WHERE to_tsvector('turkish', t.title || ' ' || COALESCE(t.notes,''))
                  @@ plainto_tsquery('turkish',$1)
              AND NOT t.is_archived AND t.deleted_at IS NULL
            ORDER BY rank DESC, t.due_date NULLS LAST
            LIMIT 30
        """, q)
    return {"query": q, "tasks": _rows(rows)}


@router.get("/stats")
@limiter.limit("100/minute")
async def get_stats(request: Request):

    """Dashboard özet istatistikleri."""
    pool = await _pool()
    if pool is None:
        return todo_store.get_stats()
    today = date.today()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(f"""
            SELECT
              COUNT(*) FILTER (WHERE due_date = '{today}' AND completed_at IS NULL)       AS due_today,
              COUNT(*) FILTER (WHERE due_date = '{today}' AND completed_at IS NOT NULL)   AS done_today,
              COUNT(*) FILTER (WHERE due_date < '{today}' AND completed_at IS NULL)       AS overdue,
              COUNT(*) FILTER (WHERE due_date BETWEEN '{today}' AND '{today}'::date+6
                               AND completed_at IS NULL)                                  AS due_week,
              COUNT(*) FILTER (WHERE completed_at IS NOT NULL)                            AS total_done,
              COUNT(*) FILTER (WHERE completed_at IS NULL AND NOT is_archived)            AS total_open
            FROM todo_tasks WHERE NOT is_archived AND deleted_at IS NULL
        """)
    return dict(row)


# ─── BÜTÇE / HARCAMA ──────────────────────────────────────────────────────────

def _check_month(month: str) -> None:
    """PG dalındaki 'month must be YYYY-MM or all' doğrulamasının depo karşılığı."""
    if month == "all":
        return
    try:
        year, mon = map(int, month.split("-"))
    except ValueError:
        raise HTTPException(400, "month must be YYYY-MM or 'all'")
    if not (1 <= mon <= 12):
        raise HTTPException(400, "month must be YYYY-MM or 'all'")


BUDGET_CATEGORIES = [
    "market", "fatura", "kira", "ulaşım", "yemek", "sağlık",  # i18n-istisna: kategori değeri (planner.html <option value>)
    "eğlence", "giyim", "eğitim", "teknoloji", "maaş", "freelance",  # i18n-istisna: kategori değeri (planner.html <option value>)
    "yatırım", "hediye", "diğer",  # i18n-istisna: kategori değeri (planner.html <option value>)
]


class BudgetEntry(BaseModel):
    type: str           # "income" | "expense"
    amount: float
    category: str = "diğer"  # i18n-istisna: kategori değeri (DB + planner.html)
    note: str | None = None
    entry_date: str | None = None   # YYYY-MM-DD, None → bugün


@router.post("/budget")
@limiter.limit("30/minute")
async def add_budget_entry(request: Request, body: BudgetEntry):

    if body.type not in ("income", "expense"):
        raise HTTPException(400, "type must be 'income' or 'expense'")
    # `not (x > 0)`: NaN her karşılaştırmada False — `<= 0` onu geçiriyordu. Sonsuz da reddedilir: ikisi de
    # JSON'a yazılamaz, o ayın özeti kalıcı 500 dönüyordu (denetim 2026-11-16, MNT-F001).
    if not (body.amount > 0) or not math.isfinite(body.amount):
        raise HTTPException(400, "amount must be > 0")
    category = body.category if body.category in BUDGET_CATEGORIES else "diğer"  # i18n-istisna: kategori değeri (DB + planner.html)
    entry_date = date.fromisoformat(body.entry_date) if body.entry_date else _yerel_bugun()
    pool = await _pool()
    if pool is None:
        return todo_store.add_budget_entry(
            body.type, body.amount, category, body.note, entry_date.isoformat()
        )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO budget_entries (type, amount, category, note, entry_date)
               VALUES ($1, $2, $3, $4, $5) RETURNING *""",
            body.type, body.amount, category, body.note, entry_date,
        )
    return dict(row)


@router.get("/budget/summary")
@limiter.limit("100/minute")
async def get_budget_summary(request: Request, month: str | None = None):

    """Aylık özet — month: YYYY-MM veya 'all', None → bu ay."""
    if month is None:
        month = _yerel_bugun().strftime("%Y-%m")
    pool = await _pool()
    if pool is None:
        _check_month(month)
        return todo_store.get_budget_summary(month)
    async with pool.acquire() as conn:
        if month == "all":
            row = await conn.fetchrow(
                """SELECT
                     COALESCE(SUM(amount) FILTER (WHERE type='income'),  0) AS income,
                     COALESCE(SUM(amount) FILTER (WHERE type='expense'), 0) AS expense,
                     COUNT(*) AS count
                   FROM budget_entries""",
            )
            cats = await conn.fetch(
                """SELECT category,
                     COALESCE(SUM(amount) FILTER (WHERE type='expense'), 0) AS total
                   FROM budget_entries WHERE type = 'expense'
                   GROUP BY category ORDER BY total DESC LIMIT 5""",
            )
        else:
            try:
                year, mon = map(int, month.split("-"))
            except ValueError:
                raise HTTPException(400, "month must be YYYY-MM or 'all'")
            row = await conn.fetchrow(
                """SELECT
                     COALESCE(SUM(amount) FILTER (WHERE type='income'),  0) AS income,
                     COALESCE(SUM(amount) FILTER (WHERE type='expense'), 0) AS expense,
                     COUNT(*) AS count
                   FROM budget_entries
                   WHERE EXTRACT(YEAR  FROM entry_date) = $1
                     AND EXTRACT(MONTH FROM entry_date) = $2""",
                year, mon,
            )
            cats = await conn.fetch(
                """SELECT category,
                     COALESCE(SUM(amount) FILTER (WHERE type='expense'), 0) AS total
                   FROM budget_entries
                   WHERE EXTRACT(YEAR  FROM entry_date) = $1
                     AND EXTRACT(MONTH FROM entry_date) = $2
                     AND type = 'expense'
                   GROUP BY category ORDER BY total DESC LIMIT 5""",
                year, mon,
            )
    income = float(row["income"])
    expense = float(row["expense"])
    return {
        "month": month,
        "income": income,
        "expense": expense,
        "balance": round(income - expense, 2),
        "count": row["count"],
        "top_categories": [{"category": r["category"], "total": float(r["total"])} for r in cats],
    }


@router.get("/budget/entries")
@limiter.limit("100/minute")
async def get_budget_entries(request: Request, month: str | None = None, limit: int = 200):

    if month is None:
        month = _yerel_bugun().strftime("%Y-%m")
    pool = await _pool()
    if pool is None:
        _check_month(month)
        return todo_store.get_budget_entries(month, limit)
    async with pool.acquire() as conn:
        if month == "all":
            rows = await conn.fetch(
                """SELECT * FROM budget_entries
                   ORDER BY entry_date DESC, created_at DESC
                   LIMIT $1""",
                limit,
            )
        else:
            try:
                year, mon = map(int, month.split("-"))
            except ValueError:
                raise HTTPException(400, "month must be YYYY-MM or 'all'")
            rows = await conn.fetch(
                """SELECT * FROM budget_entries
                   WHERE EXTRACT(YEAR  FROM entry_date) = $1
                     AND EXTRACT(MONTH FROM entry_date) = $2
                   ORDER BY entry_date DESC, created_at DESC
                   LIMIT $3""",
                year, mon, limit,
            )
    return {"entries": [dict(r) for r in rows]}


@router.delete("/budget/{entry_id}")
@limiter.limit("30/minute")
async def delete_budget_entry(request: Request, entry_id: str):

    pool = await _pool()
    if pool is None:
        if not todo_store.delete_budget_entry(entry_id):
            raise HTTPException(404, M("todo.kayit-yok"))
        return {"ok": True}
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "DELETE FROM budget_entries WHERE id=$1 RETURNING id", entry_id
        )
    if not row:
        raise HTTPException(404, M("todo.kayit-yok"))
    return {"ok": True}

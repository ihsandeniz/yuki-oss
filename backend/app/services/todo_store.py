"""Postgres'siz todo deposu — satılan ürünün (AppImage/zip) tek todo kaynağı.

NEDEN VAR: `electron/main.js` pakete Postgres koymaz ("üründe Postgres YOK, .env de
paketlenmiyor"). `api/todo.py` yalnızca asyncpg biliyordu → PLAN ekranının bütün veri
uçları pakette 503 dönüyordu (Free'de de, parasını ödeyen Pro'da da). `todo_tools.py`
kendi düz JSON yedeğini taşıdığı için Yuki sohbetten görev ekleyebiliyor ama aynı görev
PLAN ekranında görünmüyordu — iki ayrı dünya.

Bu modül o iki dünyayı birleştirir: hem `api/todo.py` (PLAN ekranı) hem `todo_tools.py`
(Yuki sohbeti) Postgres yokken BURAYI kullanır → aynı veri.

Desen `todo_tools.py`'deki JSON yedeğinden alındı (RLock + temp dosya + os.replace).
Postgres varsa (kişisel Alice / self-host) bu modüle hiç girilmez; PG yolu dokunulmadı.

Şema `app/db/todo_init.sql` ile alan-alan aynı tutulur — frontend iki yolda da aynı
JSON'u görmeli. Tarihler ISO metin olarak saklanır; asyncpg'nin date/datetime nesneleri
de FastAPI'de aynı ISO metne serileşiyor, yani şekil birebir korunur.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from app.config import DATA_DIR
from app.services import bicim

logger = logging.getLogger(__name__)

_STORE_FILE = DATA_DIR / "todo_store.json"
_LEGACY_FILE = DATA_DIR / "todos.json"      # todo_tools.py'nin eski düz deposu
_lock = threading.RLock()

INBOX_ID = "00000000-0000-0000-0000-000000000001"   # todo_init.sql'deki sabit tohum
_SCHEMA_VERSION = 1

BUDGET_CATEGORIES = [
    "market", "fatura", "kira", "ulaşım", "yemek", "sağlık",
    "eğlence", "giyim", "eğitim", "teknoloji", "maaş", "freelance",
    "yatırım", "hediye", "diğer",
]

TRASH_RETENTION_DAYS = 30   # api/todo.py'deki "30 days" ile aynı


# ══════════════════════════════════════════════════════════════════════════════
# Dosya katmanı
# ══════════════════════════════════════════════════════════════════════════════

def _empty_db() -> dict:
    return {
        "version": _SCHEMA_VERSION,
        "lists": [{
            "id": INBOX_ID, "name": "Gelen Kutusu", "color": "cyan", "icon": "⬡",
            "position": 0.0, "is_archived": False, "created_at": _now_iso(),
        }],
        "tasks": [],
        "subtasks": [],
        "dependencies": [],
        "budget": [],
    }


def _load() -> dict:
    """Depoyu oku; yoksa kur, eski düz todos.json varsa taşı."""
    with _lock:
        if _STORE_FILE.exists():
            try:
                db = json.loads(_STORE_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                # Bozuk dosyayı SİLME — yedekle ve boş başla (veri kaybını görünür kıl).
                logger.error("todo_store.json okunamadı (%s) — .bozuk olarak yedeklendi", e)
                try:
                    _STORE_FILE.replace(_STORE_FILE.with_suffix(".json.bozuk"))
                except OSError:
                    pass
                db = _empty_db()
                _save(db)
                return db
            for key in ("lists", "tasks", "subtasks", "dependencies", "budget"):
                db.setdefault(key, [])
            if not db["lists"]:
                db["lists"] = _empty_db()["lists"]
            return db

        db = _empty_db()
        _migrate_legacy(db)
        _save(db)
        return db


def _save(db: dict) -> None:
    """Atomik yazma — yarım dosya bırakmaz (todo_tools.py deseni)."""
    with _lock:
        tmp = _STORE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, _STORE_FILE)


def _migrate_legacy(db: dict) -> None:
    """Eski düz todos.json'daki görevleri yeni modele taşı (veri kaybetme)."""
    if not _LEGACY_FILE.exists():
        return
    try:
        items = json.loads(_LEGACY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(items, list) or not items:
        return

    for pos, it in enumerate(items):
        list_name = (it.get("list_name") or "gelen kutusu").strip()
        # 🔴 2026-09-18 (FAZ 0): burası `list_name.title()` idi. Python'un `.title()`'ı
        # Unicode (İngilizce) haritası kullanır → "işler" → **"Işler"** (doğrusu "İşler").
        # Bu ad diske KALICI yazıldığı için hata kullanıcının listesinde kalıyordu.
        lst = _find_list_by_name(db, list_name) or _create_list_row(
            db, bicim.baslik(list_name), "cyan", "⬡"
        )
        db["tasks"].append(_task_row(
            list_id=lst["id"],
            title=it.get("title") or "(başlıksız)",
            notes=it.get("notes") or None,
            priority=it.get("priority") or "mid",
            due_date=it.get("due_date"),
            reminder_at=it.get("reminder_at"),
            position=float(pos + 1),
            created_at=it.get("created_at") or _now_iso(),
            completed_at=it.get("completed_at"),
        ))
    logger.info("todo_store: eski todos.json'dan %d görev taşındı", len(items))
    try:
        _LEGACY_FILE.replace(_LEGACY_FILE.with_suffix(".json.tasindi"))
    except OSError:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# Yardımcılar
# ══════════════════════════════════════════════════════════════════════════════

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _uid() -> str:
    return str(uuid.uuid4())


def _as_date(v: Any) -> Optional[date]:
    if not v:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (ValueError, TypeError):
        return None


def _as_dt(v: Any) -> Optional[datetime]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v))
    except (ValueError, TypeError):
        return None


def _norm(s: str) -> str:
    """Türkçe-duyarlı küçültme (İ→i, I→ı) — arama/eşleşme için."""
    return (s or "").replace("İ", "i").replace("I", "ı").lower()


_PRIO_RANK = {"high": 0, "mid": 1, "low": 2}


def _prio_key(t: dict) -> int:
    return _PRIO_RANK.get(t.get("priority"), 1)


def _task_row(**kw) -> dict:
    """todo_tasks satırı — todo_init.sql'deki tüm sütunlar, aynı adlarla."""
    return {
        "id": kw.get("id") or _uid(),
        "list_id": kw["list_id"],
        "title": kw["title"],
        "notes": kw.get("notes"),
        "priority": kw.get("priority") if kw.get("priority") in _PRIO_RANK else "mid",
        "status": kw.get("status") or "todo",
        "start_date": kw.get("start_date"),
        "due_date": kw.get("due_date"),
        "reminder_at": kw.get("reminder_at"),
        "repeat": kw.get("repeat") or "none",
        "tags": list(kw.get("tags") or []),
        "position": float(kw.get("position") or 0),
        "estimated_time": kw.get("estimated_time"),
        "section_name": kw.get("section_name"),
        "is_archived": bool(kw.get("is_archived", False)),
        "completed_at": kw.get("completed_at"),
        "deleted_at": kw.get("deleted_at"),
        "calendar_event_id": kw.get("calendar_event_id"),
        "calendar_synced": bool(kw.get("calendar_synced", False)),
        "created_at": kw.get("created_at") or _now_iso(),
    }


def _create_list_row(db: dict, name: str, color: str, icon: str) -> dict:
    max_pos = max([l.get("position") or 0 for l in db["lists"]], default=0)
    row = {
        "id": _uid(), "name": name, "color": color, "icon": icon,
        "position": float(max_pos) + 1, "is_archived": False, "created_at": _now_iso(),
    }
    db["lists"].append(row)
    return row


def _find_list_by_name(db: dict, name: str) -> Optional[dict]:
    """PG'deki `LOWER(name) LIKE %ad%` davranışının karşılığı."""
    needle = _norm(name)
    hits = [l for l in db["lists"] if not l["is_archived"] and needle in _norm(l["name"])]
    hits.sort(key=lambda l: l.get("position") or 0)
    return hits[0] if hits else None


def _find(rows: list[dict], **kw) -> Optional[dict]:
    for r in rows:
        if all(r.get(k) == v for k, v in kw.items()):
            return r
    return None


def _live_tasks(db: dict) -> list[dict]:
    """Çöpte olmayan görevler."""
    return [t for t in db["tasks"] if not t.get("deleted_at")]


def _list_meta(db: dict, list_id: str) -> tuple[str, str]:
    lst = _find(db["lists"], id=list_id)
    return (lst["name"], lst["color"]) if lst else ("", "cyan")


def _with_list_meta(db: dict, tasks: list[dict]) -> list[dict]:
    out = []
    for t in tasks:
        name, color = _list_meta(db, t["list_id"])
        out.append({**t, "list_name": name, "list_color": color})
    return out


# ══════════════════════════════════════════════════════════════════════════════
# LİSTELER
# ══════════════════════════════════════════════════════════════════════════════

def get_lists() -> dict:
    db = _load()
    out = []
    for l in sorted([x for x in db["lists"] if not x["is_archived"]],
                    key=lambda x: (x.get("position") or 0, x.get("created_at") or "")):
        tasks = [t for t in _live_tasks(db) if t["list_id"] == l["id"]]
        out.append({
            **l,
            "open_count": sum(1 for t in tasks if not t["completed_at"] and not t["is_archived"]),
            "done_count": sum(1 for t in tasks if t["completed_at"]),
        })
    return {"lists": out}


def create_list(name: str, color: str = "cyan", icon: str = "⬡") -> dict:
    with _lock:
        db = _load()
        row = _create_list_row(db, name, color, icon)
        _save(db)
    return row


def update_list(list_id: str, name=None, color=None, icon=None, position=None) -> Optional[dict]:
    with _lock:
        db = _load()
        row = _find(db["lists"], id=list_id)
        if not row:
            return None
        if name is not None:
            row["name"] = name
        if color is not None:
            row["color"] = color
        if icon is not None:
            row["icon"] = icon
        if position is not None:
            row["position"] = float(position)
        _save(db)
    return row


def delete_list(list_id: str) -> None:
    """PG ile aynı: listeyi arşivle, görevlerini çöpe taşı (soft)."""
    with _lock:
        db = _load()
        now = _now_iso()
        for t in db["tasks"]:
            if t["list_id"] == list_id and not t.get("deleted_at"):
                t["deleted_at"] = now
        row = _find(db["lists"], id=list_id)
        if row:
            row["is_archived"] = True
        _save(db)


def reorder_lists(ordered_ids: list[str]) -> None:
    with _lock:
        db = _load()
        for i, lid in enumerate(ordered_ids):
            row = _find(db["lists"], id=lid)
            if row:
                row["position"] = float(i)
        _save(db)


# ══════════════════════════════════════════════════════════════════════════════
# GÖREVLER
# ══════════════════════════════════════════════════════════════════════════════

def _attach_subtasks(db: dict, task: dict) -> dict:
    subs = sorted([s for s in db["subtasks"] if s["task_id"] == task["id"]],
                  key=lambda s: s.get("position") or 0)
    return {**task, "subtasks": subs}


def get_tasks(list_id: str, include_completed: bool = False) -> dict:
    db = _load()
    rows = [t for t in _live_tasks(db)
            if t["list_id"] == list_id and not t["is_archived"]
            and (include_completed or not t["completed_at"])]
    # PG: ORDER BY section_name NULLS LAST, position, created_at
    rows.sort(key=lambda t: (t.get("section_name") is None, t.get("section_name") or "",
                             t.get("position") or 0, t.get("created_at") or ""))
    return {"tasks": [_attach_subtasks(db, t) for t in rows]}


def list_exists(list_id: str) -> bool:
    db = _load()
    row = _find(db["lists"], id=list_id)
    return bool(row and not row["is_archived"])


def create_task(list_id: str, **kw) -> dict:
    with _lock:
        db = _load()
        siblings = [t["position"] or 0 for t in db["tasks"] if t["list_id"] == list_id]
        row = _task_row(list_id=list_id, position=max(siblings, default=0) + 1, **kw)
        db["tasks"].append(row)
        _save(db)
    return {**row, "subtasks": []}


def get_task(task_id: str) -> Optional[dict]:
    return _find(_load()["tasks"], id=task_id)


_UPDATABLE = ("title", "notes", "priority", "status", "start_date", "due_date",
              "reminder_at", "repeat", "tags", "position", "estimated_time", "section_name")


def update_task(task_id: str, fields: dict) -> Optional[dict]:
    """`fields`te BULUNAN her anahtar uygulanır — değeri None ise alan temizlenir.

    Ayrım önemli: PG dalında `due_date=""` tarihi SİLER, alanın hiç gönderilmemesi
    ise dokunmaz. Bu yüzden "gönderilmedi" = anahtar yok, "temizle" = anahtar var+None.
    """
    with _lock:
        db = _load()
        row = _find(db["tasks"], id=task_id)
        if not row:
            return None
        for k in _UPDATABLE:
            if k in fields:
                row[k] = list(fields[k] or []) if k == "tags" else fields[k]
        _save(db)
    return row


def delete_task(task_id: str) -> None:
    """Soft delete — çöp kutusuna taşır."""
    with _lock:
        db = _load()
        row = _find(db["tasks"], id=task_id)
        if row:
            row["deleted_at"] = _now_iso()
            _save(db)


def get_trash() -> dict:
    """Çöptekiler + 30 günü geçenleri kalıcı temizle (PG ile aynı davranış)."""
    with _lock:
        db = _load()
        cutoff = datetime.now(timezone.utc) - timedelta(days=TRASH_RETENTION_DAYS)
        keep, purged = [], set()
        for t in db["tasks"]:
            d = _as_dt(t.get("deleted_at"))
            if d is not None and d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            if d and d < cutoff:
                purged.add(t["id"])
                continue
            keep.append(t)
        if purged:
            db["tasks"] = keep
            db["subtasks"] = [s for s in db["subtasks"] if s["task_id"] not in purged]
            db["dependencies"] = [d for d in db["dependencies"]
                                  if d["task_id"] not in purged and d["depends_on"] not in purged]
            _save(db)
        rows = [t for t in db["tasks"] if t.get("deleted_at")]
        rows.sort(key=lambda t: t.get("deleted_at") or "", reverse=True)
        out = [{**t, "list_name": _list_meta(db, t["list_id"])[0]} for t in rows]
    return {"tasks": out}


def restore_task(task_id: str) -> bool:
    with _lock:
        db = _load()
        row = _find(db["tasks"], id=task_id)
        if not row or not row.get("deleted_at"):
            return False
        row["deleted_at"] = None
        _save(db)
    return True


def permanent_delete_task(task_id: str) -> bool:
    with _lock:
        db = _load()
        row = _find(db["tasks"], id=task_id)
        if not row or not row.get("deleted_at"):
            return False
        db["tasks"] = [t for t in db["tasks"] if t["id"] != task_id]
        db["subtasks"] = [s for s in db["subtasks"] if s["task_id"] != task_id]
        db["dependencies"] = [d for d in db["dependencies"]
                              if d["task_id"] != task_id and d["depends_on"] != task_id]
        _save(db)
    return True


def complete_task(task_id: str) -> Optional[dict]:
    with _lock:
        db = _load()
        row = _find(db["tasks"], id=task_id)
        if not row:
            return None
        if row.get("completed_at"):
            # Zaten tamamlanmış (çift tık / ağ tekrarı): ilk zamanı ezme, ikinci tekrar açma.
            return row
        row["completed_at"] = _now_iso()
        _clone_recurring(db, row)
        _save(db)
    return row


def uncomplete_task(task_id: str) -> None:
    with _lock:
        db = _load()
        row = _find(db["tasks"], id=task_id)
        if row:
            row["completed_at"] = None
            _save(db)


def reorder_tasks(ordered_ids: list[str]) -> None:
    with _lock:
        db = _load()
        for i, tid in enumerate(ordered_ids):
            row = _find(db["tasks"], id=tid)
            if row:
                row["position"] = float(i)
        _save(db)


def bulk_complete(ids: list[str]) -> int:
    with _lock:
        db = _load()
        now = _now_iso()
        n = 0
        for tid in ids:
            row = _find(db["tasks"], id=tid)
            if row and not row.get("completed_at"):
                row["completed_at"] = now
                # Tekli tamamlamayla aynı: tekrarlı görev zinciri toplu yolda da kopmasın.
                _clone_recurring(db, row)
                n += 1
        _save(db)
    return n


def _sonraki_ay(due: date) -> date:
    """Bir sonraki ayın aynı günü; o gün yoksa ayın son günü (31 Ocak → 28/29 Şubat).

    🔴 Eskiden 31 Şubat yok diye klon HİÇ açılmıyordu: ayın 29/30/31'indeki aylık görevin
    tekrarı ilk kısa ayda sessizce bitiyordu.
    """
    import calendar
    y = due.year + (1 if due.month == 12 else 0)
    m = due.month % 12 + 1
    return due.replace(year=y, month=m, day=min(due.day, calendar.monthrange(y, m)[1]))


def sonraki_tarih(due: date, repeat: str) -> Optional[date]:
    """Tekrarlı görevin bir sonraki tarihi; tanınmayan tekrar → None.

    🔴 `api/todo._VALID_REPEATS`'teki HER değer burada karşılanmalı: eskiden yalnız
    daily/weekly/monthly vardı; hafta içi / 2 haftada / yıllık / özel ilk tamamlamada
    zinciri sessizce kaybediyordu. SQLite ve Postgres yolu bu tek kuralı kullanır.
    """
    import calendar
    if repeat == "daily":
        return due + timedelta(days=1)
    if repeat == "weekdays":                         # Cuma → Pazartesi
        n = due + timedelta(days=1)
        while n.weekday() >= 5:
            n += timedelta(days=1)
        return n
    if repeat == "weekly":
        return due + timedelta(weeks=1)
    if repeat == "biweekly":
        return due + timedelta(weeks=2)
    if repeat == "monthly":
        return _sonraki_ay(due)
    if repeat == "yearly":                           # 29 Şubat → 28 Şubat
        y = due.year + 1
        return due.replace(year=y, day=min(due.day, calendar.monthrange(y, due.month)[1]))
    if repeat.startswith("custom:") and repeat[7:].isdigit() and int(repeat[7:]) > 0:
        return due + timedelta(days=int(repeat[7:]))  # arayüz: "Her N günde bir"
    return None


def _clone_recurring(db: dict, row: dict) -> None:
    """PG'deki _clone_recurring ile AYNI davranış (tarih kuralı `sonraki_tarih`)."""
    due = _as_date(row.get("due_date"))
    repeat = row.get("repeat") or "none"
    if repeat == "none" or not due:
        return
    new_due = sonraki_tarih(due, repeat)
    if new_due is None:
        return
    # Aynı tekrar zaten açıksa (tamamla → geri al → tamamla) ikinci kopya açma.
    if any(t is not row and t["list_id"] == row["list_id"] and t["title"] == row["title"]
           and (t.get("repeat") or "none") == repeat and t.get("due_date") == new_due.isoformat()
           and not t.get("completed_at") and not t.get("deleted_at")
           for t in db["tasks"]):
        return
    siblings = [t["position"] or 0 for t in db["tasks"] if t["list_id"] == row["list_id"]]
    db["tasks"].append(_task_row(
        list_id=row["list_id"], title=row["title"], notes=row.get("notes"),
        priority=row.get("priority"), due_date=new_due.isoformat(),
        repeat=repeat, tags=list(row.get("tags") or []),
        position=max(siblings, default=0) + 1,
    ))


# ══════════════════════════════════════════════════════════════════════════════
# BAĞIMLILIKLAR
# ══════════════════════════════════════════════════════════════════════════════

_DEP_FIELDS = ("id", "title", "completed_at", "priority", "due_date")


def get_dependencies(task_id: str) -> dict:
    db = _load()
    live = {t["id"]: t for t in _live_tasks(db)}

    def _slim(tid: str) -> Optional[dict]:
        t = live.get(tid)
        return {k: t[k] for k in _DEP_FIELDS} if t else None

    blocked_by = [x for x in (_slim(d["depends_on"]) for d in db["dependencies"]
                              if d["task_id"] == task_id) if x]
    blocks = [x for x in (_slim(d["task_id"]) for d in db["dependencies"]
                          if d["depends_on"] == task_id) if x]
    return {"blocked_by": blocked_by, "blocks": blocks}


def add_dependency(task_id: str, depends_on: str) -> None:
    with _lock:
        db = _load()
        if not _find(db["dependencies"], task_id=task_id, depends_on=depends_on):
            db["dependencies"].append({
                "id": _uid(), "task_id": task_id,
                "depends_on": depends_on, "created_at": _now_iso(),
            })
            _save(db)


def remove_dependency(task_id: str, dep_id: str) -> None:
    with _lock:
        db = _load()
        db["dependencies"] = [d for d in db["dependencies"]
                              if not (d["task_id"] == task_id and d["depends_on"] == dep_id)]
        _save(db)


# ══════════════════════════════════════════════════════════════════════════════
# ALT GÖREVLER
# ══════════════════════════════════════════════════════════════════════════════

def create_subtask(task_id: str, title: str) -> dict:
    with _lock:
        db = _load()
        siblings = [s.get("position") or 0 for s in db["subtasks"] if s["task_id"] == task_id]
        row = {"id": _uid(), "task_id": task_id, "title": title,
               "position": max(siblings, default=0) + 1, "completed_at": None}
        db["subtasks"].append(row)
        _save(db)
    return row


def update_subtask(task_id: str, sub_id: str, title=None, completed=None) -> Optional[dict]:
    with _lock:
        db = _load()
        row = _find(db["subtasks"], id=sub_id, task_id=task_id)
        if not row:
            return None
        if title is not None:
            row["title"] = title
        if completed is True:
            row["completed_at"] = _now_iso()
        elif completed is False:
            row["completed_at"] = None
        _save(db)
    return row


def delete_subtask(task_id: str, sub_id: str) -> None:
    with _lock:
        db = _load()
        db["subtasks"] = [s for s in db["subtasks"]
                          if not (s["id"] == sub_id and s["task_id"] == task_id)]
        _save(db)


# ══════════════════════════════════════════════════════════════════════════════
# TAKVİM BAĞI
# ══════════════════════════════════════════════════════════════════════════════

def set_calendar_link(task_id: str, event_id: Optional[str]) -> None:
    with _lock:
        db = _load()
        row = _find(db["tasks"], id=task_id)
        if row:
            row["calendar_event_id"] = event_id
            row["calendar_synced"] = event_id is not None
            _save(db)


# ══════════════════════════════════════════════════════════════════════════════
# FİLTRE · ARAMA · İSTATİSTİK
# ══════════════════════════════════════════════════════════════════════════════

FILTERS = ("today", "week", "overdue", "priority", "completed",
           "archived", "in_progress", "blocked")


def filter_tasks(f: str) -> Optional[dict]:
    """PG'deki filter_tasks sorgularının birebir karşılığı. Geçersiz filtre → None."""
    if f not in FILTERS:
        return None
    db = _load()
    today = date.today()
    live = _live_tasks(db)
    open_active = [t for t in live if not t["completed_at"] and not t["is_archived"]]

    if f == "today":
        sel = [t for t in open_active if _as_date(t["due_date"]) == today]
        sel.sort(key=lambda t: (_prio_key(t), t.get("position") or 0))
    elif f == "week":
        end = today + timedelta(days=6)
        sel = [t for t in open_active if _as_date(t["due_date"]) and today <= _as_date(t["due_date"]) <= end]
        sel.sort(key=lambda t: (_as_date(t["due_date"]), _prio_key(t)))
    elif f == "overdue":
        sel = [t for t in open_active if _as_date(t["due_date"]) and _as_date(t["due_date"]) < today]
        sel.sort(key=lambda t: _as_date(t["due_date"]))
    elif f == "priority":
        sel = [t for t in open_active if t["priority"] == "high"]
        sel.sort(key=lambda t: (_as_date(t["due_date"]) is None,
                                _as_date(t["due_date"]) or today, t.get("position") or 0))
    elif f == "completed":
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        sel = []
        for t in live:
            c = _as_dt(t["completed_at"])
            if c is None:
                continue
            if c.tzinfo is None:
                c = c.replace(tzinfo=timezone.utc)
            if c >= cutoff:
                sel.append(t)
        sel.sort(key=lambda t: t["completed_at"] or "", reverse=True)
    elif f == "archived":
        sel = [t for t in live if t["is_archived"]]
        sel.sort(key=lambda t: t.get("created_at") or "", reverse=True)
    else:   # in_progress | blocked
        sel = [t for t in open_active if t["status"] == f]
        sel.sort(key=lambda t: (_as_date(t["due_date"]) is None,
                                _as_date(t["due_date"]) or today, t.get("position") or 0))

    return {"filter": f, "tasks": _with_list_meta(db, sel)}


def search_tasks(q: str) -> dict:
    """PG'de Türkçe full-text + ts_rank. Burada Türkçe-duyarlı alt dizge + basit skor.

    Skor: başlıkta geçen kelime 2 puan, notlarda 1 puan (ts_rank'ın kaba karşılığı).
    """
    db = _load()
    words = [w for w in _norm(q).split() if w]
    scored = []
    for t in _live_tasks(db):
        if t["is_archived"]:
            continue
        title, notes = _norm(t["title"]), _norm(t.get("notes") or "")
        rank = sum(2 for w in words if w in title) + sum(1 for w in words if w in notes)
        if rank:
            scored.append((rank, t))
    scored.sort(key=lambda p: (-p[0], _as_date(p[1]["due_date"]) is None,
                               _as_date(p[1]["due_date"]) or date.max))
    rows = []
    for rank, t in scored[:30]:
        name, color = _list_meta(db, t["list_id"])
        rows.append({**t, "list_name": name, "list_color": color, "rank": float(rank)})
    return {"query": q, "tasks": rows}


def get_stats() -> dict:
    db = _load()
    today = date.today()
    week_end = today + timedelta(days=6)
    tasks = [t for t in _live_tasks(db) if not t["is_archived"]]

    def due(t):
        return _as_date(t["due_date"])

    return {
        "due_today":  sum(1 for t in tasks if due(t) == today and not t["completed_at"]),
        "done_today": sum(1 for t in tasks if due(t) == today and t["completed_at"]),
        "overdue":    sum(1 for t in tasks if due(t) and due(t) < today and not t["completed_at"]),
        "due_week":   sum(1 for t in tasks if due(t) and today <= due(t) <= week_end
                          and not t["completed_at"]),
        "total_done": sum(1 for t in tasks if t["completed_at"]),
        "total_open": sum(1 for t in tasks if not t["completed_at"]),
    }


# ══════════════════════════════════════════════════════════════════════════════
# BÜTÇE
# ══════════════════════════════════════════════════════════════════════════════

def add_budget_entry(type_: str, amount: float, category: str,
                     note: Optional[str], entry_date: Optional[str]) -> dict:
    with _lock:
        db = _load()
        row = {
            "id": _uid(),
            "type": type_,
            "amount": float(amount),
            "category": category if category in BUDGET_CATEGORIES else "diğer",
            "note": note,
            "entry_date": entry_date or date.today().isoformat(),
            "created_at": _now_iso(),
        }
        db["budget"].append(row)
        _save(db)
    return row


def _budget_of_month(db: dict, month: Optional[str]) -> list[dict]:
    if month == "all":
        return list(db["budget"])
    return [e for e in db["budget"] if (e.get("entry_date") or "")[:7] == month]


def get_budget_summary(month: str) -> dict:
    db = _load()
    rows = _budget_of_month(db, month)
    income = sum(e["amount"] for e in rows if e["type"] == "income")
    expense = sum(e["amount"] for e in rows if e["type"] == "expense")
    by_cat: dict[str, float] = {}
    for e in rows:
        if e["type"] == "expense":
            by_cat[e["category"]] = by_cat.get(e["category"], 0.0) + e["amount"]
    top = sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return {
        "month": month,
        "income": round(float(income), 2),
        "expense": round(float(expense), 2),
        "balance": round(float(income - expense), 2),
        "count": len(rows),
        "top_categories": [{"category": c, "total": round(float(v), 2)} for c, v in top],
    }


def get_budget_entries(month: str, limit: int = 200) -> dict:
    db = _load()
    rows = _budget_of_month(db, month)
    rows.sort(key=lambda e: (e.get("entry_date") or "", e.get("created_at") or ""), reverse=True)
    return {"entries": rows[:limit]}


def delete_budget_entry(entry_id: str) -> bool:
    with _lock:
        db = _load()
        before = len(db["budget"])
        db["budget"] = [e for e in db["budget"] if e["id"] != entry_id]
        if len(db["budget"]) == before:
            return False
        _save(db)
    return True


# ══════════════════════════════════════════════════════════════════════════════
# Araç katmanı (todo_tools.py) için yardımcılar
# ══════════════════════════════════════════════════════════════════════════════

def resolve_list_id(name: str) -> str:
    """Ada göre liste bul; yoksa Gelen Kutusu (PG'deki davranışın aynısı)."""
    db = _load()
    lst = _find_list_by_name(db, name or "gelen kutusu")
    return lst["id"] if lst else INBOX_ID


def open_tasks() -> list[dict]:
    """Tamamlanmamış, arşivsiz, çöpte olmayan görevler + liste adı."""
    db = _load()
    rows = [t for t in _live_tasks(db) if not t["completed_at"] and not t["is_archived"]]
    return _with_list_meta(db, rows)


def all_tasks_with_list() -> list[dict]:
    db = _load()
    return _with_list_meta(db, _live_tasks(db))


def lists_with_counts() -> list[dict]:
    return get_lists()["lists"]

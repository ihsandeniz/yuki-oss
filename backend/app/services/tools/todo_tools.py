"""Todo araçları: Yuki için görev yönetimi (create/list/complete/search).

Depo stratejisi: Postgres (todo_lists/todo_tasks) erişilebilirse onu kullanır;
DB yoksa (ürün / Lite paketi) `app.services.todo_store`'a düşer. Böylece P1
sürümü hiç veritabanı gerektirmez; Postgres'li kurulumda PG yolu aynen çalışır
(kişisel Alice parity).

⚠️ 2026-07-31: burası eskiden KENDİ düz `todos.json`'unu tutuyordu. Sonuç: Yuki
sohbetten görev ekliyordu ama aynı görev PLAN ekranında görünmüyordu (ekran
`api/todo.py` → Postgres istiyordu, üründe Postgres yok → 503). Artık iki yol da
todo_store'u kullanıyor → TEK veri. Eski todos.json ilk açılışta oraya taşınır.
"""
import asyncio
import re
from datetime import date, datetime, timedelta
from typing import Optional

from app.services import bicim, todo_store


async def _pool():
    """DB havuzu; erişilemezse (ürün/Lite) None döner → todo_store devreye girer."""
    from app.db.connection import get_pool
    try:
        return await get_pool()
    except Exception:
        return None


_PRIO_TR = {"high": "yüksek", "mid": "orta", "low": "düşük"}
_DURUMLAR = ("todo", "in_progress", "blocked", "done")

#: priority metin sütunu: `ORDER BY priority DESC` sırası mid, low, high çıkar (api/todo.py ile aynı ifade).
_ONCELIK_SIRA = "CASE t.priority WHEN 'high' THEN 0 WHEN 'mid' THEN 1 ELSE 2 END"

#: Model kimi zaman Türkçe yazıyor; eskiden bilinmeyen her değer sessizce "tümü" sayılıyordu.
_FILTRE_ADLARI = {
    "today": "today", "bugün": "today", "bugun": "today",
    "week": "week", "hafta": "week", "bu hafta": "week",
    "overdue": "overdue", "gecikmiş": "overdue", "gecikmis": "overdue",
    "all": "all", "tümü": "all", "tumu": "all", "hepsi": "all", "tüm": "all",
}

_TR_EKLER = ("larından", "lerinden", "larını", "lerini", "larına", "lerine", "ların", "lerin", "ları", "leri",
             "lar", "ler", "nın", "nin", "nun", "nün", "dan", "den", "da", "de", "ya", "ye", "yı", "yi", "yu", "yü")


def _kaba_kokler(sorgu: str) -> list[str]:
    """Sorgu sözcüklerinin eki atılmış hâli; yalnız asıl arama boş dönünce kullanılır.

    PG'nin `turkish` gövdeleyicisi `faturalar`ı `fatura`ya indirmiyor (kişiselde ölçüldü),
    depo yolu da alt dizge arıyor: "faturalar" → "fatura öde" bulunmuyordu.
    """
    kokler = []
    for s in re.findall(r"[^\W_]+", todo_store._norm(sorgu)):
        for ek in _TR_EKLER:
            if s.endswith(ek) and len(s) - len(ek) >= 3:
                s = s[:-len(ek)]
                break
        if len(s) >= 3:
            kokler.append(s)
    return kokler


def _tarih_hatasi(due_date, reminder_at) -> Optional[str]:
    """Anlaşılmayan tarih sessizce düşerse görev tarihsiz eklenir, kullanıcı fark etmez."""
    if due_date:
        try:
            date.fromisoformat(due_date)
        except ValueError:
            return f"Hata: Bitiş tarihi anlaşılamadı ('{due_date}'), YYYY-AA-GG olmalı. Görev EKLENMEDİ."
    if reminder_at:
        try:
            datetime.fromisoformat(reminder_at)
        except ValueError:
            return f"Hata: Hatırlatma zamanı anlaşılamadı ('{reminder_at}'), ISO 8601 olmalı. Görev EKLENMEDİ."
    return None
_PRIO_ICON = {"high": "🔴", "mid": "🟡", "low": "🟢"}


def _due_of(item: dict) -> Optional[date]:
    try:
        return date.fromisoformat(str(item["due_date"])[:10]) if item.get("due_date") else None
    except (ValueError, TypeError):
        return None


# ── todo_store dalı (DB yokken — ürün/Lite). PLAN ekranıyla AYNI veri. ──

def _store_create_todo(title, list_name, due_date, priority, notes, reminder_at) -> str:
    prio = priority if priority in _PRIO_TR else "mid"
    due = None
    if due_date:
        try:
            due = date.fromisoformat(due_date).isoformat()
        except ValueError:
            pass
    row = todo_store.create_task(
        todo_store.resolve_list_id(list_name),
        title=title, notes=notes or None, priority=prio,
        due_date=due, reminder_at=reminder_at or None,
    )
    due_str = f", bitiş: {due}" if due else ""
    return f"Görev eklendi: '{title}' [{_PRIO_TR[prio]} öncelik{due_str}] (id: {row['id']})"


def _store_complete_todo(task_id: str) -> str:
    task = todo_store.get_task(task_id)
    if not task or task.get("completed_at"):
        return f"Görev bulunamadı veya zaten tamamlanmış: {task_id}"
    todo_store.complete_task(task_id)
    return f"Görev tamamlandı: '{task['title']}'"


def _store_list_todos(filter: str) -> str:
    items = todo_store.open_tasks()
    today = date.today()
    if filter == "today":
        sel = [i for i in items if _due_of(i) == today]
        label = "Bugün"
    elif filter == "week":
        end = today + timedelta(days=6)
        sel = [i for i in items if _due_of(i) and today <= _due_of(i) <= end]
        label = "Bu Hafta"
    elif filter == "overdue":
        sel = [i for i in items if _due_of(i) and _due_of(i) < today]
        label = "Gecikmiş"
    else:
        sel = items[:20]
        label = "Tüm Görevler"
    if not sel:
        return f"{label}: Görev yok."
    order = {"high": 0, "mid": 1, "low": 2}
    sel.sort(key=lambda i: order.get(i.get("priority"), 1))
    lines = [f"{label} ({len(sel)} görev):"]
    for i in sel:
        icon = _PRIO_ICON.get(i.get("priority"), "•")
        due = f" [{str(i['due_date'])[:10]}]" if i.get("due_date") else ""
        lines.append(f"  {icon} {i['title']}{due} ({i.get('list_name') or 'gelen kutusu'}) · id: {i['id']}")
    return "\n".join(lines)


async def create_todo(
    title: str,
    list_name: str = "gelen kutusu",
    due_date: Optional[str] = None,
    priority: str = "mid",
    notes: str = "",
    reminder_at: Optional[str] = None,
) -> str:
    """Yeni görev oluşturur.

    Args:
        title: Görev başlığı
        list_name: Liste adı veya 'gelen kutusu' (default)
        due_date: Bitiş tarihi (YYYY-MM-DD formatı, opsiyonel)
        priority: 'high', 'mid' veya 'low'
        notes: Notlar (opsiyonel)
        reminder_at: Hatırlatma zamanı ISO 8601 (opsiyonel)
    """
    if not (title or "").strip():
        return "Hata: Görev başlığı boş olamaz. Görev EKLENMEDİ."
    hata = _tarih_hatasi(due_date, reminder_at)
    if hata:
        return hata
    pool = await _pool()
    if pool is None:
        return _store_create_todo(title, list_name, due_date, priority, notes, reminder_at)
    try:
        async with pool.acquire() as conn:
            # Liste adına göre ID bul
            list_row = await conn.fetchrow(
                "SELECT id FROM todo_lists WHERE LOWER(name) LIKE $1 AND is_archived = FALSE ORDER BY position LIMIT 1",
                f"%{list_name.lower()}%",
            )
            if list_row:
                list_id = list_row["id"]
            else:
                # Bulunamazsa inbox kullan
                list_id = "00000000-0000-0000-0000-000000000001"

            # Pozisyon: mevcut max + 1
            max_pos = await conn.fetchval(
                "SELECT COALESCE(MAX(position), 0) FROM todo_tasks WHERE list_id = $1",
                list_id,
            )

            due = None
            if due_date:
                try:
                    due = date.fromisoformat(due_date)
                except ValueError:
                    pass

            remind = None
            if reminder_at:
                try:
                    remind = datetime.fromisoformat(reminder_at)
                except ValueError:
                    pass

            row = await conn.fetchrow(
                """
                INSERT INTO todo_tasks (list_id, title, notes, priority, due_date, reminder_at, position)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id, title, priority, due_date
                """,
                list_id,
                title,
                notes or None,
                priority if priority in ("high", "mid", "low") else "mid",
                due,
                remind,
                max_pos + 1,
            )

        due_str = f", bitiş: {row['due_date']}" if row["due_date"] else ""
        prio_map = {"high": "yüksek", "mid": "orta", "low": "düşük"}
        prio_str = prio_map.get(row["priority"], "orta")
        return f"Görev eklendi: '{row['title']}' [{prio_str} öncelik{due_str}] (id: {row['id']})"
    except Exception as e:
        return f"Hata: Görev eklenemedi. {e}"


async def complete_todo(task_id: str) -> str:
    """Görevi tamamlandı olarak işaretler.

    Args:
        task_id: Görev UUID'si
    """
    pool = await _pool()
    if pool is None:
        return _store_complete_todo(task_id)
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE todo_tasks
                SET completed_at = NOW()
                WHERE id = $1 AND completed_at IS NULL
                RETURNING *
                """,
                task_id,
            )
            if not row:
                return f"Görev bulunamadı veya zaten tamamlanmış: {task_id}"
        # Tekrarlı görev → sonraki kopya (panel ucuyla aynı yol). Eskiden bu yol klonlamıyordu:
        # sesle tamamlanan günlük görevin ertesi günü hiç açılmıyordu.
        if (row["repeat"] or "none") != "none" and row["due_date"]:
            from app.api.todo import _clone_recurring
            await _clone_recurring(row)
        return f"Görev tamamlandı: '{row['title']}'"
    except Exception as e:
        return f"Hata: Görev tamamlanamadı. {e}"


async def list_todos(filter: str = "today") -> str:
    """Görevleri listeler.

    Args:
        filter: 'today' (bugün), 'week' (bu hafta), 'overdue' (gecikmiş), 'all' (tümü)
    """
    filter = _FILTRE_ADLARI.get((filter or "").strip().lower(), "")
    if not filter:
        return "Hata: Geçersiz görev filtresi. Geçerli değerler: today, week, overdue, all."
    pool = await _pool()
    if pool is None:
        return _store_list_todos(filter)
    try:
        async with pool.acquire() as conn:
            if filter == "today":
                rows = await conn.fetch(
                    f"""
                    SELECT t.title, t.priority, t.due_date, l.name AS list_name
                    FROM todo_tasks t
                    JOIN todo_lists l ON l.id = t.list_id
                    WHERE t.completed_at IS NULL AND t.is_archived = FALSE AND t.deleted_at IS NULL
                      AND t.due_date = CURRENT_DATE
                    ORDER BY {_ONCELIK_SIRA}, t.position
                    """
                )
                label = "Bugün"
            elif filter == "week":
                rows = await conn.fetch(
                    f"""
                    SELECT t.title, t.priority, t.due_date, l.name AS list_name
                    FROM todo_tasks t
                    JOIN todo_lists l ON l.id = t.list_id
                    WHERE t.completed_at IS NULL AND t.is_archived = FALSE AND t.deleted_at IS NULL
                      AND t.due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 6
                    ORDER BY t.due_date, {_ONCELIK_SIRA}
                    """
                )
                label = "Bu Hafta"
            elif filter == "overdue":
                rows = await conn.fetch(
                    f"""
                    SELECT t.title, t.priority, t.due_date, l.name AS list_name
                    FROM todo_tasks t
                    JOIN todo_lists l ON l.id = t.list_id
                    WHERE t.completed_at IS NULL AND t.is_archived = FALSE AND t.deleted_at IS NULL
                      AND t.due_date < CURRENT_DATE
                    ORDER BY t.due_date, {_ONCELIK_SIRA}
                    """
                )
                label = "Gecikmiş"
            else:  # all
                rows = await conn.fetch(
                    f"""
                    SELECT t.title, t.priority, t.due_date, l.name AS list_name
                    FROM todo_tasks t
                    JOIN todo_lists l ON l.id = t.list_id
                    WHERE t.completed_at IS NULL AND t.is_archived = FALSE AND t.deleted_at IS NULL
                    ORDER BY t.due_date NULLS LAST, {_ONCELIK_SIRA}, t.position
                    LIMIT 20
                    """
                )
                label = "Tüm Görevler"

        if not rows:
            return f"{label}: Görev yok."

        prio_map = {"high": "🔴", "mid": "🟡", "low": "🟢"}
        lines = [f"{label} ({len(rows)} görev):"]
        for r in rows:
            prio = prio_map.get(r["priority"], "•")
            due = f" [{r['due_date']}]" if r["due_date"] else ""
            lines.append(f"  {prio} {r['title']}{due} ({r['list_name']})")
        return "\n".join(lines)
    except Exception as e:
        return f"Hata: Görevler listelenemedi. {e}"


async def search_todos(query: str) -> str:
    """Görevlerde tam metin arama yapar (Türkçe).

    Args:
        query: Arama metni
    """
    try:
        pool = await _pool()
        if pool is None:
            rows = todo_store.search_tasks(query)["tasks"][:10]
            if not rows:
                kokler = _kaba_kokler(query)
                if kokler:
                    rows = [r for r in todo_store.search_tasks(" ".join(kokler))["tasks"]
                            if all(k in todo_store._norm(f"{r['title']} {r.get('notes') or ''}")
                                   for k in kokler)][:10]
            if not rows:
                return f"'{query}' için sonuç bulunamadı."
            lines = [f"'{query}' arama sonuçları ({len(rows)} görev):"]
            for r in rows:
                status = "✓" if r["completed_at"] else "☐"
                due = f" [{str(r['due_date'])[:10]}]" if r["due_date"] else ""
                lines.append(f"  {status} {r['title']}{due} — {r['list_name']} (id: {r['id']})")
            return "\n".join(lines)
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT t.id, t.title, t.priority, t.due_date, t.completed_at, l.name AS list_name,
                       ts_rank(to_tsvector('turkish', t.title || ' ' || COALESCE(t.notes, '')),
                               plainto_tsquery('turkish', $1)) AS rank
                FROM todo_tasks t
                JOIN todo_lists l ON l.id = t.list_id
                WHERE t.is_archived = FALSE
                  AND to_tsvector('turkish', t.title || ' ' || COALESCE(t.notes, ''))
                      @@ plainto_tsquery('turkish', $1)
                ORDER BY rank DESC
                LIMIT 10
                """,
                query,
            )
            if not rows:
                kokler = _kaba_kokler(query)
                if kokler:
                    rows = await conn.fetch(
                        """
                        SELECT t.id, t.title, t.priority, t.due_date, t.completed_at, l.name AS list_name
                        FROM todo_tasks t
                        JOIN todo_lists l ON l.id = t.list_id
                        WHERE t.is_archived = FALSE AND t.deleted_at IS NULL
                          AND NOT EXISTS (
                              SELECT 1 FROM unnest($1::text[]) k
                              WHERE t.title || ' ' || COALESCE(t.notes, '') NOT ILIKE '%' || k || '%')
                        ORDER BY t.position
                        LIMIT 10
                        """,
                        kokler,
                    )

        if not rows:
            return f"'{query}' için sonuç bulunamadı."

        lines = [f"'{query}' arama sonuçları ({len(rows)} görev):"]
        for r in rows:
            status = "✓" if r["completed_at"] else "☐"
            due = f" [{r['due_date']}]" if r["due_date"] else ""
            lines.append(f"  {status} {r['title']}{due} — {r['list_name']} (id: {r['id']})")
        return "\n".join(lines)
    except Exception as e:
        return f"Hata: Arama yapılamadı. {e}"


async def delete_todo(task_id: str) -> str:
    """Görevi kalıcı olarak siler.

    Args:
        task_id: Görev UUID'si (önce search_todos ile bul)
    """
    try:
        pool = await _pool()
        if pool is None:
            task = todo_store.get_task(task_id)
            if not task:
                return f"Görev bulunamadı: {task_id}"
            # Aracın sözleşmesi "kalıcı sil" → çöpe atmadan doğrudan kaldır.
            todo_store.delete_task(task_id)
            todo_store.permanent_delete_task(task_id)
            return f"Görev silindi: '{task['title']}'"
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "DELETE FROM todo_tasks WHERE id = $1 RETURNING title",
                task_id,
            )
            if not row:
                return f"Görev bulunamadı: {task_id}"
        return f"Görev silindi: '{row['title']}'"
    except Exception as e:
        return f"Hata: Görev silinemedi. {e}"


async def update_todo(
    task_id: str,
    title: Optional[str] = None,
    priority: Optional[str] = None,
    due_date: Optional[str] = None,
    notes: Optional[str] = None,
    reminder_at: Optional[str] = None,
    status: Optional[str] = None,
) -> str:
    """Görevi günceller (başlık, öncelik, tarih, notlar, durum).

    Args:
        task_id: Görev UUID'si (önce search_todos ile bul)
        title: Yeni başlık (opsiyonel)
        priority: 'high', 'mid' veya 'low' (opsiyonel)
        due_date: Bitiş tarihi YYYY-MM-DD, temizlemek için '' (opsiyonel)
        notes: Notlar (opsiyonel)
        reminder_at: Hatırlatma zamanı ISO 8601, temizlemek için '' (opsiyonel)
        status: 'todo', 'in_progress', 'blocked', 'done' (opsiyonel)
    """
    try:
        pool = await _pool()
        updates = []
        params: list = []

        # Geçersiz değer sessizce atlanırsa kalan alanlar yazılır, model "güncellendi" der.
        if priority is not None and priority not in _PRIO_TR:
            return "Hata: Geçersiz öncelik; high, mid ya da low olmalı. Görev değişmedi."
        if status is not None and status not in _DURUMLAR:
            return "Hata: Geçersiz durum; todo, in_progress, blocked ya da done olmalı. Görev değişmedi."
        if title is not None:
            params.append(title)
            updates.append(f"title = ${len(params)}")
        if priority is not None:
            params.append(priority)
            updates.append(f"priority = ${len(params)}")
        if due_date is not None:
            val = date.fromisoformat(due_date) if due_date else None
            params.append(val)
            updates.append(f"due_date = ${len(params)}")
        if notes is not None:
            params.append(notes or None)
            updates.append(f"notes = ${len(params)}")
        if reminder_at is not None:
            val = datetime.fromisoformat(reminder_at) if reminder_at else None
            params.append(val)
            updates.append(f"reminder_at = ${len(params)}")
        if status is not None:
            params.append(status)
            updates.append(f"status = ${len(params)}")
            # Listeler "bitti"yi completed_at'ten anlar; yazılmazsa görev açık görünür.
            updates.append("completed_at = COALESCE(completed_at, NOW())" if status == "done"
                           else "completed_at = NULL")

        if not updates:
            return "Hata: Güncellenecek alan belirtilmedi."

        if pool is None:
            # PG'deki "gönderildi = uygula, boş metin = temizle" davranışının aynısı.
            fields: dict = {}
            if title is not None:
                fields["title"] = title
            if priority is not None:
                fields["priority"] = priority
            if due_date is not None:
                fields["due_date"] = date.fromisoformat(due_date).isoformat() if due_date else None
            if notes is not None:
                fields["notes"] = notes or None
            if reminder_at is not None:
                fields["reminder_at"] = (datetime.fromisoformat(reminder_at).isoformat()
                                         if reminder_at else None)
            if status is not None:
                fields["status"] = status
            onceki = todo_store.get_task(task_id) if status is not None else None
            row = todo_store.update_task(task_id, fields)
            if row and onceki is not None:
                if status == "done" and not onceki.get("completed_at"):
                    todo_store.complete_task(task_id)
                elif status != "done" and onceki.get("completed_at"):
                    todo_store.uncomplete_task(task_id)
            if not row:
                return f"Görev bulunamadı: {task_id}"
            changed = []
            if title is not None: changed.append(f"başlık→'{title}'")
            if priority is not None: changed.append(f"öncelik→'{priority}'")
            if due_date is not None: changed.append(f"tarih→'{due_date or 'temizlendi'}'")
            if notes is not None: changed.append("notlar güncellendi")
            if reminder_at is not None: changed.append(f"hatırlatıcı→'{reminder_at or 'temizlendi'}'")
            if status is not None: changed.append(f"durum→'{status}'")
            return f"Görev güncellendi: '{row['title']}' [{', '.join(changed)}]"

        params.append(task_id)
        sql = f"UPDATE todo_tasks SET {', '.join(updates)} WHERE id = ${len(params)} RETURNING title"

        async with pool.acquire() as conn:
            row = await conn.fetchrow(sql, *params)
            if not row:
                return f"Görev bulunamadı: {task_id}"

        changed = []
        if title is not None: changed.append(f"başlık→'{title}'")
        if priority is not None: changed.append(f"öncelik→'{priority}'")
        if due_date is not None: changed.append(f"tarih→'{due_date or 'temizlendi'}'")
        if notes is not None: changed.append("notlar güncellendi")
        if reminder_at is not None: changed.append(f"hatırlatıcı→'{reminder_at or 'temizlendi'}'")
        if status is not None: changed.append(f"durum→'{status}'")
        return f"Görev güncellendi: '{row['title']}' [{', '.join(changed)}]"
    except Exception as e:
        return f"Hata: Görev güncellenemedi. {e}"


async def list_todo_lists() -> str:
    """Tüm aktif görev listelerini gösterir.

    Hangi listeler var, kaç görevi var gibi bilgileri verir.
    """
    try:
        pool = await _pool()
        if pool is None:
            rows = todo_store.lists_with_counts()
            if not rows:
                return "Hiç liste yok."
            lines = [f"Görev listeleri ({len(rows)} liste):"]
            for r in rows:
                lines.append(
                    f"  {r['icon']} {r['name']} — {r['open_count']} aktif, {r['done_count']} tamamlandı"
                )
            return "\n".join(lines)
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT l.id, l.name, l.icon, l.color,
                       COUNT(t.id) FILTER (WHERE t.completed_at IS NULL) AS active_count,
                       COUNT(t.id) FILTER (WHERE t.completed_at IS NOT NULL) AS done_count
                FROM todo_lists l
                LEFT JOIN todo_tasks t ON t.list_id = l.id AND t.is_archived = FALSE
                WHERE l.is_archived = FALSE
                GROUP BY l.id, l.name, l.icon, l.color
                ORDER BY l.position
                """
            )
        if not rows:
            return "Hiç liste yok."
        lines = [f"Görev listeleri ({len(rows)} liste):"]
        for r in rows:
            lines.append(
                f"  {r['icon']} {r['name']} — {r['active_count']} aktif, {r['done_count']} tamamlandı"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Hata: Listeler alınamadı. {e}"


async def get_budget_summary(month: Optional[str] = None) -> str:
    """Belirli bir ay için bütçe özetini döndürür.

    Args:
        month: 'YYYY-MM' formatında ay (opsiyonel, varsayılan: bu ay)
    """
    try:
        from datetime import date as _date
        if not month:
            d = _date.today()
            month = f"{d.year}-{d.month:02d}"
        pool = await _pool()
        if pool is None:
            s = todo_store.get_budget_summary(month)
            income, expense = s["income"], s["expense"]
            balance = s["balance"]
            sign = "+" if balance >= 0 else ""
            lines = [
                f"📊 {month} Bütçe Özeti:",
                f"  Gelir  : {bicim.para(income)}",
                f"  Gider  : {bicim.para(expense)}",
                f"  Bakiye : {sign}{bicim.para(balance)}",
            ]
            if s["top_categories"]:
                lines.append("  En çok harcama:")
                for c in s["top_categories"]:
                    lines.append(f"    • {c['category']}: {bicim.para(c['total'])}")
            if s["count"] == 0:
                lines.append("  (Bu ay henüz kayıt yok.)")
            return "\n".join(lines)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COALESCE(SUM(amount) FILTER (WHERE type='income'),  0) AS income,
                    COALESCE(SUM(amount) FILTER (WHERE type='expense'), 0) AS expense,
                    COUNT(*) AS total
                FROM budget_entries
                WHERE TO_CHAR(entry_date, 'YYYY-MM') = $1
                """,
                month,
            )
            cats = await conn.fetch(
                """
                SELECT category, SUM(amount) AS total
                FROM budget_entries
                WHERE TO_CHAR(entry_date, 'YYYY-MM') = $1 AND type='expense'
                GROUP BY category ORDER BY total DESC LIMIT 5
                """,
                month,
            )

        income  = float(row["income"] or 0)
        expense = float(row["expense"] or 0)
        balance = income - expense
        sign    = "+" if balance >= 0 else ""
        lines   = [
            f"📊 {month} Bütçe Özeti:",
            f"  Gelir  : {bicim.para(income)}",
            f"  Gider  : {bicim.para(expense)}",
            f"  Bakiye : {sign}{bicim.para(balance)}",
        ]
        if cats:
            lines.append("  En çok harcama:")
            for c in cats:
                lines.append(f"    • {c['category']}: {bicim.para(float(c['total']))}")
        if row["total"] == 0:
            lines.append("  (Bu ay henüz kayıt yok.)")
        return "\n".join(lines)
    except Exception as e:
        return f"Hata: Bütçe özeti alınamadı. {e}"


async def get_todo_stats() -> dict:
    """Todo istatistiklerini döndürür (scheduler morning briefing için)."""
    try:
        pool = await _pool()
        if pool is None:
            s = todo_store.get_stats()
            return {k: s[k] for k in ("due_today", "done_today", "overdue", "due_week")}
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE completed_at IS NULL AND due_date = CURRENT_DATE)  AS due_today,
                    COUNT(*) FILTER (WHERE completed_at IS NOT NULL AND due_date = CURRENT_DATE) AS done_today,
                    COUNT(*) FILTER (WHERE completed_at IS NULL AND due_date < CURRENT_DATE)   AS overdue,
                    COUNT(*) FILTER (WHERE completed_at IS NULL AND due_date BETWEEN CURRENT_DATE AND CURRENT_DATE+6) AS due_week
                FROM todo_tasks WHERE is_archived = FALSE
                """
            )
        return {
            "due_today": row["due_today"] or 0,
            "done_today": row["done_today"] or 0,
            "overdue": row["overdue"] or 0,
            "due_week": row["due_week"] or 0,
        }
    except Exception:
        return {"due_today": 0, "done_today": 0, "overdue": 0, "due_week": 0}

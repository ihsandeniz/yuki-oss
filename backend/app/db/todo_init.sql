-- Todo sistemi tablolar (idempotent)

CREATE TABLE IF NOT EXISTS todo_lists (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    color       TEXT NOT NULL DEFAULT 'cyan',
    icon        TEXT NOT NULL DEFAULT '⬡',
    position    REAL NOT NULL DEFAULT 0,
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS todo_tasks (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    list_id           UUID NOT NULL REFERENCES todo_lists(id) ON DELETE CASCADE,
    title             TEXT NOT NULL,
    notes             TEXT,
    priority          TEXT NOT NULL DEFAULT 'mid' CHECK (priority IN ('high','mid','low')),
    due_date          DATE,
    reminder_at       TIMESTAMPTZ,
    repeat            TEXT NOT NULL DEFAULT 'none' CHECK (repeat IN ('none','daily','weekly','monthly')),
    tags              TEXT[] NOT NULL DEFAULT '{}',
    position          REAL NOT NULL DEFAULT 0,
    is_archived       BOOLEAN NOT NULL DEFAULT FALSE,
    completed_at      TIMESTAMPTZ,
    calendar_event_id TEXT,
    calendar_synced   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS todo_subtasks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id      UUID NOT NULL REFERENCES todo_tasks(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    position     REAL NOT NULL DEFAULT 0,
    completed_at TIMESTAMPTZ
);

-- Yeni sütunlar (idempotent ALTER)
ALTER TABLE todo_tasks ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'todo'
  CHECK (status IN ('todo','in_progress','blocked','done'));
ALTER TABLE todo_tasks ADD COLUMN IF NOT EXISTS start_date DATE;
ALTER TABLE todo_tasks ADD COLUMN IF NOT EXISTS estimated_time INTEGER;   -- dakika cinsinden (#8)
ALTER TABLE todo_tasks ADD COLUMN IF NOT EXISTS section_name TEXT;         -- section/grup adı (#12)
ALTER TABLE todo_tasks ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;   -- soft delete (#13)

-- Tekrar constraint genişlet (eski kısıtı kaldır, yeni değerler + custom:N formatı Python'da doğrulanır)
ALTER TABLE todo_tasks DROP CONSTRAINT IF EXISTS todo_tasks_repeat_check;

-- Görev bağımlılıkları (#11)
CREATE TABLE IF NOT EXISTS todo_dependencies (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id      UUID NOT NULL REFERENCES todo_tasks(id) ON DELETE CASCADE,
    depends_on   UUID NOT NULL REFERENCES todo_tasks(id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (task_id, depends_on)
);

CREATE INDEX IF NOT EXISTS idx_todo_tasks_list     ON todo_tasks(list_id);
CREATE INDEX IF NOT EXISTS idx_todo_tasks_due      ON todo_tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_todo_tasks_archived ON todo_tasks(is_archived);
CREATE INDEX IF NOT EXISTS idx_todo_tasks_reminder ON todo_tasks(reminder_at) WHERE reminder_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_todo_tasks_fts
    ON todo_tasks USING GIN(to_tsvector('turkish', title || ' ' || COALESCE(notes, '')));

-- Bütçe/Harcama takip tablosu
CREATE TABLE IF NOT EXISTS budget_entries (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type        TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    amount      NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    category    TEXT NOT NULL DEFAULT 'diğer',
    note        TEXT,
    entry_date  DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_budget_date ON budget_entries(entry_date DESC);

-- Varsayılan "Gelen Kutusu" listesi
INSERT INTO todo_lists (id, name, color, icon, position)
VALUES ('00000000-0000-0000-0000-000000000001', 'Gelen Kutusu', 'cyan', '⬡', 0)
ON CONFLICT (id) DO NOTHING;

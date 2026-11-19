-- Fitness sistemi tablolar (idempotent)

CREATE TABLE IF NOT EXISTS fitness_meals (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_date  DATE NOT NULL DEFAULT CURRENT_DATE,
    meal        TEXT NOT NULL DEFAULT 'ara' CHECK (meal IN ('kahvalti','ogle','aksam','ara')),
    name        TEXT NOT NULL,
    cal         NUMERIC(8,1) NOT NULL DEFAULT 0,
    protein     NUMERIC(8,1) NOT NULL DEFAULT 0,
    carb        NUMERIC(8,1) NOT NULL DEFAULT 0,
    fat         NUMERIC(8,1) NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_fitness_meals_date ON fitness_meals(entry_date DESC);

CREATE TABLE IF NOT EXISTS fitness_workouts (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_date DATE NOT NULL UNIQUE,
    notes        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fitness_exercises (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workout_id  UUID NOT NULL REFERENCES fitness_workouts(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    position    REAL NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_fitness_exercises_workout ON fitness_exercises(workout_id);

CREATE TABLE IF NOT EXISTS fitness_sets (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exercise_id UUID NOT NULL REFERENCES fitness_exercises(id) ON DELETE CASCADE,
    reps        INTEGER NOT NULL DEFAULT 0,
    weight      NUMERIC(7,2) NOT NULL DEFAULT 0,
    completed   BOOLEAN NOT NULL DEFAULT FALSE,
    position    REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_fitness_sets_exercise ON fitness_sets(exercise_id);

CREATE TABLE IF NOT EXISTS fitness_templates (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    exercises   JSONB NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fitness_config (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

INSERT INTO fitness_config (key, value) VALUES
    ('calGoal',     '2000'),
    ('proteinGoal', '150'),
    ('carbGoal',    '200'),
    ('fatGoal',     '65')
ON CONFLICT (key) DO NOTHING;

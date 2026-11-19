-- Yuki — pgvector schema
-- Faz 3: Semantik hafıza sistemi
-- Faz C: Named Memory Scopes + HNSW

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS memories (
    id             BIGSERIAL PRIMARY KEY,
    session_id     TEXT NOT NULL DEFAULT 'default',
    role           TEXT NOT NULL,                    -- 'user' | 'assistant' | 'system'
    content        TEXT NOT NULL,
    embedding      vector(384),                      -- paraphrase-multilingual-MiniLM-L12-v2
    category       TEXT NOT NULL DEFAULT 'conversation',  -- 'conversation' | 'preference' | 'fact'
    scope          VARCHAR(20) NOT NULL DEFAULT 'conversation',  -- 'conversation' | 'fact' | 'preference' | 'skill'
    importance     FLOAT NOT NULL DEFAULT 0.5,       -- 0.0–1.0 öncelik skoru
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    character_key  VARCHAR(10) NOT NULL DEFAULT 'yuki',  -- Faz 17: per-karakter izolasyon
    -- Ad listesi değil BİÇİM kısıtı (2026-11-14): geçerli karakter kümesi uygulamada
    -- (personas.PERSONAS) yaşar; yeni karakter şema göçü istemez, kaldırılmış
    -- karakterin eski satırları da kısıtı bozmaz.
    CONSTRAINT memories_character_key_check
        CHECK (character_key ~ '^[a-z][a-z0-9_]{0,9}$')
);

-- Zaman bazlı sorgular için indeks (get_recent)
CREATE INDEX IF NOT EXISTS memories_session_time_idx
    ON memories (session_id, created_at DESC);

-- Kategori filtreleme indeksi
CREATE INDEX IF NOT EXISTS memories_category_idx
    ON memories (session_id, category);

-- Scope filtreleme indeksi
CREATE INDEX IF NOT EXISTS memories_scope_idx
    ON memories (session_id, scope);

-- HNSW vektör indeksi — cosine similarity için
CREATE INDEX IF NOT EXISTS memories_embedding_hnsw_idx
    ON memories USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 128);

-- Faz 17: per-karakter izolasyon indeksleri
CREATE INDEX IF NOT EXISTS memories_character_session_time_idx
    ON memories (character_key, session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS memories_character_scope_idx
    ON memories (character_key, scope);

-- ------------------------------------------------------------------ --
-- Faz L — Multi-Person Yüz Tanıma
-- ------------------------------------------------------------------ --

CREATE TABLE IF NOT EXISTS faces (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    embedding   vector(512) NOT NULL,               -- InsightFace buffalo_l ArcFace 512-dim
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS faces_name_idx
    ON faces (name);

-- Cosine distance (InsightFace L2-normalized embeddings)
CREATE INDEX IF NOT EXISTS faces_embedding_hnsw_idx
    ON faces USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 128);

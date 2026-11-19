-- Migration: Named Memory Scopes (Faz C)
-- Mevcut DB'ye scope sütunu ekle + HNSW indeksi oluştur
-- Kullanım: psql -U yuki -d alice_ai -f migrate_scope.sql

-- 1. scope sütunu ekle (yoksa)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'memories' AND column_name = 'scope'
    ) THEN
        ALTER TABLE memories ADD COLUMN scope VARCHAR(20) NOT NULL DEFAULT 'conversation';
        -- Mevcut kayıtları category'den scope'a kopyala
        UPDATE memories SET scope = category WHERE category IN ('fact', 'preference', 'skill');
    END IF;
END $$;

-- 2. Scope indeksi
CREATE INDEX IF NOT EXISTS memories_scope_idx
    ON memories (session_id, scope);

-- 3. HNSW indeksi (ivfflat yerine, pgvector 0.5+)
DROP INDEX IF EXISTS memories_embedding_ivfflat_idx;
CREATE INDEX IF NOT EXISTS memories_embedding_hnsw_idx
    ON memories USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 128);

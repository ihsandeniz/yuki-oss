-- Migration: Per-Character Memory (Faz 17)
-- memories tablosuna character_key sütunu ekle — her karakterin anıları izole
-- Güvenli: idempotent DO $$ blokları, mevcut veriler bozulmaz
-- Kullanım: psql -U yuki -d alice_ai -f migrate_character.sql

-- 1. character_key sütunu ekle (yoksa) — mevcut kayıtlar 'yuki' varsayılanı alır
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'memories' AND column_name = 'character_key'
    ) THEN
        ALTER TABLE memories
            ADD COLUMN character_key VARCHAR(10) NOT NULL DEFAULT 'yuki';
    END IF;
END $$;

-- 2. CHECK constraint — BİÇİM kısıtı (2026-11-14), ad listesi değil.
--    Eski kurulumlarda kısıt ad listesiydi (IN ('yuki', ...)). Yuki dışındaki
--    karakterler uygulamadan kaldırıldı ama o karakterlerin eski satırları DB'de
--    kalabilir: listeyi daraltmak ADD CONSTRAINT'i bu satırlarda düşürür (ve açılışı
--    kırar), satırları silmek kullanıcı verisini yok eder. Biçim kısıtı ikisini de
--    yapmaz; geçerli karakter kümesi uygulamadadır (personas.PERSONAS).
--    Eski ad-listesi kısıtı (tanımında regex '~' geçmeyen) bir kez biçim kısıtıyla değiştirilir;
--    sonraki açılışlarda koşul sağlanmaz → idempotent, tablo yeniden taranmaz.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'memories_character_key_check'
          AND conrelid = to_regclass('memories')
          AND pg_get_constraintdef(oid) NOT LIKE '%~%'
    ) THEN
        ALTER TABLE memories DROP CONSTRAINT memories_character_key_check;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'memories'
          AND constraint_name = 'memories_character_key_check'
    ) THEN
        ALTER TABLE memories
            ADD CONSTRAINT memories_character_key_check
            CHECK (character_key ~ '^[a-z][a-z0-9_]{0,9}$');
    END IF;
END $$;

-- 3. Karakter+oturum+zaman B-tree indeksi (WHERE + ORDER BY sorgularını hızlandırır)
CREATE INDEX IF NOT EXISTS memories_character_session_time_idx
    ON memories (character_key, session_id, created_at DESC);

-- 4. Karakter+scope B-tree indeksi (scope filtreli aramalarda)
CREATE INDEX IF NOT EXISTS memories_character_scope_idx
    ON memories (character_key, scope);

-- Row Level Security: sadece uygulama DB rolü (yuki) erişebilir
-- Çalıştırma: psql -U yuki -d alice_ai -f rls.sql
-- Not: Bu betik superuser bağlantısı veya tablo sahibi olarak çalıştırılmalıdır.

-- memories tablosu
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE memories FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS memories_app_only ON memories;
CREATE POLICY memories_app_only ON memories
    TO yuki
    USING (true)
    WITH CHECK (true);

-- faces tablosu
ALTER TABLE faces ENABLE ROW LEVEL SECURITY;
ALTER TABLE faces FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS faces_app_only ON faces;
CREATE POLICY faces_app_only ON faces
    TO yuki
    USING (true)
    WITH CHECK (true);

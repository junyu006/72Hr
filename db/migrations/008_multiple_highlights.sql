-- Multiple highlighted spans may point to the same entry or provenance source.
-- Provenance is traceability metadata, not a highlight identity.
ALTER TABLE highlights DROP CONSTRAINT IF EXISTS highlights_provenance_pointer_key;
CREATE INDEX IF NOT EXISTS highlights_provenance_pointer_idx ON highlights(provenance_pointer);

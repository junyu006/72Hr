ALTER TABLE highlights ADD COLUMN origin text NOT NULL DEFAULT 'clinician' CHECK (origin IN ('clinician','ai'));
ALTER TABLE highlights ADD COLUMN reason_entry_id text REFERENCES care_entries(id);

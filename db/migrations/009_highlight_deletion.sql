-- Clinicians and admins may delete highlights attached to records they can see.
DROP POLICY IF EXISTS highlights_delete ON highlights;
CREATE POLICY highlights_delete ON highlights FOR DELETE USING (
  current_setting('app.role', true) IN ('clinician','admin')
  AND EXISTS (SELECT 1 FROM care_entries e WHERE e.id = entry_id)
);

GRANT DELETE ON highlights TO nightingale_app;

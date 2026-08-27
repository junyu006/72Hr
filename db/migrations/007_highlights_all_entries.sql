-- Clinicians and admins may manually highlight any record visible in their clinic.
-- System-originated automatic highlights remain limited to AI records.
DROP POLICY IF EXISTS highlights_insert ON highlights;
CREATE POLICY highlights_insert ON highlights FOR INSERT WITH CHECK (
  (current_setting('app.role', true) IN ('clinician','admin')
   AND EXISTS (SELECT 1 FROM care_entries e WHERE e.id = entry_id))
  OR
  (current_setting('app.role', true) = 'system'
   AND origin = 'ai'
   AND EXISTS (
     SELECT 1 FROM care_entries e
     WHERE e.id = entry_id AND e.entry_type IN ('ai_scribe_log','ai_patient_consult')))
);

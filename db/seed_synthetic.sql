-- English-only synthetic demonstration data. No real patient information.
-- Reset transient authentication and notification state too, so every technical
-- demo starts logged out and contains no mentions from an earlier run.
TRUNCATE app_sessions, comment_mentions, audit_log, comments, entry_versions,
  highlights, care_entries, patient_accounts, patients, importance_feedback,
  app_users
  RESTART IDENTITY CASCADE;

INSERT INTO patients (id, clinic_id, display_label) VALUES
  ('patient_ava_synthetic', 'clinic_demo', 'Ava Morgan (Synthetic)'),
  ('patient_noah_synthetic', 'clinic_demo', 'Noah Chen (Synthetic)');

INSERT INTO patient_accounts (patient_id, patient_user_id, clinic_id) VALUES
  ('patient_ava_synthetic', 'patient_demo', 'clinic_demo');

INSERT INTO care_entries (id,patient_id,clinic_id,section,content,author_id,author_role,entry_type,provenance_pointer,risk_level,tags,open_action) VALUES
  ('entry_a11ce001','patient_ava_synthetic','clinic_demo','patient_facing','Please complete your follow-up blood test this week and contact the clinic if dizziness worsens.','doctor_demo','clinician','patient_facing_log',NULL,1,ARRAY['follow-up'],true),
  ('entry_b22ce002','patient_ava_synthetic','clinic_demo','clinician_sections','The patient reports intermittent morning dizziness and denies chest pain. Medication adherence and routine blood testing were discussed.','doctor_demo','clinician','doctor_patient_consult',NULL,2,ARRAY['dizziness','medication'],true),
  ('entry_c33ce003','patient_ava_synthetic','clinic_demo','staff_notes','Preferred contact window: weekdays after 2 PM. Follow-up call scheduled for Thursday.','staff_demo','staff','staff_manual_log',NULL,0,ARRAY['contact-preference'],true),
  ('entry_d44ce004','patient_ava_synthetic','clinic_demo','ai_scribed',E'The patient reported intermittent morning dizziness and denied chest pain. Medication adherence and routine blood testing were discussed.\n\nSource consult: entry_b22ce002','qwen2.5-0.5b','system','ai_scribe_log','entry:entry_b22ce002',2,ARRAY['dizziness','medication'],false),
  ('entry_e55ce005','patient_noah_synthetic','clinic_demo','clinician_sections','Routine wellness review completed. Continue the current care plan.','doctor_demo','clinician','clinician_manual_log',NULL,0,ARRAY['wellness'],false),
  ('entry_f66ce006','patient_ava_synthetic','clinic_demo','ai_scribed','Patient chart created and access policy initialized.','system_demo','system','system_generated_event',NULL,0,ARRAY['system'],false),
  ('entry_a77ce007','patient_noah_synthetic','clinic_demo','clinician_sections','The patient discussed sleep routine and hydration. No urgent concern was reported.','nurse_demo','clinician','nurse_patient_consult',NULL,0,ARRAY['wellness'],false),
  ('entry_b88ce008','patient_noah_synthetic','clinic_demo','ai_scribed','AI-guided synthetic check-in completed. The patient requested general appointment preparation instructions.','system_demo','system','ai_patient_consult',NULL,0,ARRAY['ai-consult'],false);

INSERT INTO entry_versions (entry_id,version,content,changed_by,change_reason)
SELECT id,version,content,author_id,'created' FROM care_entries;

INSERT INTO comments (id,entry_id,author_id,author_role,body,mention_user_id) VALUES
  ('comment_a001','entry_b22ce002','staff_demo','staff','Blood test scheduling request received.','doctor_demo');

INSERT INTO audit_log (entry_id,actor_id,action,metadata)
SELECT id,author_id,'created',jsonb_build_object('synthetic',true,'section',section::text) FROM care_entries;

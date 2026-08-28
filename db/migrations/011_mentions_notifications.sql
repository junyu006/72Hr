-- Multi-recipient @mentions double as durable, per-user notifications.
CREATE TABLE comment_mentions (
  comment_id text NOT NULL REFERENCES comments(id) ON DELETE CASCADE,
  mentioned_user_id text NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  clinic_id text NOT NULL,
  read_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (comment_id, mentioned_user_id)
);

CREATE INDEX comment_mentions_user_inbox_idx
  ON comment_mentions(mentioned_user_id, created_at DESC);
CREATE INDEX comment_mentions_user_unread_idx
  ON comment_mentions(mentioned_user_id, created_at DESC)
  WHERE read_at IS NULL;

ALTER TABLE comment_mentions ENABLE ROW LEVEL SECURITY;
ALTER TABLE comment_mentions FORCE ROW LEVEL SECURITY;

CREATE POLICY comment_mentions_read ON comment_mentions FOR SELECT USING (
  clinic_id = current_setting('app.clinic_id', true)
  AND EXISTS (
    SELECT 1 FROM comments c
    JOIN care_entries e ON e.id = c.entry_id
    WHERE c.id = comment_mentions.comment_id
      AND (
        comment_mentions.mentioned_user_id = current_setting('app.user_id', true)
        OR c.author_id = current_setting('app.user_id', true)
      )
  )
);

CREATE POLICY comment_mentions_insert ON comment_mentions FOR INSERT WITH CHECK (
  clinic_id = current_setting('app.clinic_id', true)
  AND current_setting('app.role', true) <> 'patient'
  AND EXISTS (
    SELECT 1
    FROM comments c
    JOIN care_entries e ON e.id = c.entry_id
    JOIN app_users u ON u.id = comment_mentions.mentioned_user_id
    WHERE c.id = comment_mentions.comment_id
      AND c.author_id = current_setting('app.user_id', true)
      AND e.clinic_id = comment_mentions.clinic_id
      AND u.clinic_id = comment_mentions.clinic_id
      AND u.active
      AND (
        u.role IN ('clinician','admin')
        OR (u.role = 'staff' AND e.entry_type = 'staff_manual_log')
      )
  )
);

CREATE POLICY comment_mentions_update ON comment_mentions FOR UPDATE USING (
  clinic_id = current_setting('app.clinic_id', true)
  AND mentioned_user_id = current_setting('app.user_id', true)
) WITH CHECK (
  clinic_id = current_setting('app.clinic_id', true)
  AND mentioned_user_id = current_setting('app.user_id', true)
);

GRANT SELECT,INSERT,UPDATE ON comment_mentions TO nightingale_app;

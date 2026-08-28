"""PostgreSQL persistence boundary. Requires DATABASE_URL and psycopg 3."""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from typing import Iterator

from .domain import Actor, Role, new_id
from .clinical import AI_HIGHLIGHT_TYPES, can_edit_entry, validate_entry_create
from .auth import new_session_token, token_digest, verify_password


MENTION_PATTERN = re.compile(r"(?<![\w@])@([A-Za-z0-9][A-Za-z0-9_.-]{0,63})")


class PostgresStore:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.environ["DATABASE_URL"]

    def login(self, username: str, password: str) -> tuple[str, dict]:
        import psycopg
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id,username,password_hash,role::text,clinic_id,clinician_kind,patient_id FROM app_users WHERE username=%s AND active", (username,))
                row = cur.fetchone()
                if not row or not verify_password(password, row[2]):
                    raise PermissionError("invalid username or password")
                token = new_session_token()
                expires_at = datetime.now(timezone.utc) + timedelta(hours=8)
                cur.execute("DELETE FROM app_sessions WHERE expires_at <= now()")
                cur.execute("INSERT INTO app_sessions(token_hash,user_id,expires_at) VALUES (%s,%s,%s)", (token_digest(token), row[0], expires_at))
                return token, {"id": row[0], "username": row[1], "role": row[3], "clinic_id": row[4], "clinician_kind": row[5], "patient_id": row[6], "expires_at": expires_at}

    def session_user(self, token: str) -> dict | None:
        if not token:
            return None
        import psycopg
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT u.id,u.username,u.role::text,u.clinic_id,u.clinician_kind,u.patient_id,s.expires_at
                    FROM app_sessions s JOIN app_users u ON u.id=s.user_id
                    WHERE s.token_hash=%s AND s.expires_at>now() AND u.active""", (token_digest(token),))
                row = cur.fetchone()
                if not row:
                    return None
                return {"id": row[0], "username": row[1], "role": row[2], "clinic_id": row[3], "clinician_kind": row[4], "patient_id": row[5], "expires_at": row[6]}

    def logout(self, token: str) -> None:
        if not token:
            return
        import psycopg
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM app_sessions WHERE token_hash=%s", (token_digest(token),))

    @contextmanager
    def request(self, actor: Actor) -> Iterator[object]:
        """One transaction with non-forgeable database-local RBAC context."""
        import psycopg
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.clinic_id', %s, true)", (actor.clinic_id,))
                cur.execute("SELECT set_config('app.role', %s, true)", (actor.role.value,))
                cur.execute("SELECT set_config('app.user_id', %s, true)", (actor.id,))
                cur.execute("SELECT set_config('app.clinician_kind', %s, true)", (actor.clinician_kind.value if actor.clinician_kind else "",))
                yield cur

    def timeline(self, actor: Actor, patient_id: str) -> list[dict]:
        with self.request(actor) as cur:
            cur.execute("SELECT id, section, content, author_id, author_role, entry_type, provenance_pointer, risk_level, tags, open_action, version, created_at FROM care_entries WHERE patient_id = %s ORDER BY created_at DESC", (patient_id,))
            return self._rows(cur)

    @staticmethod
    def _rows(cur: object) -> list[dict]:
        columns = [d.name for d in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

    def patients(self, actor: Actor) -> list[dict]:
        with self.request(actor) as cur:
            cur.execute("SELECT id, display_label, created_at FROM patients ORDER BY created_at DESC")
            return self._rows(cur)

    def create_patient(self, actor: Actor, display_label: str) -> dict:
        if actor.role not in {Role.STAFF, Role.CLINICIAN, Role.ADMIN}:
            raise PermissionError("role cannot create patients")
        patient_id = new_id("patient")
        with self.request(actor) as cur:
            cur.execute("INSERT INTO patients(id, clinic_id, display_label) VALUES (%s,%s,%s) RETURNING id, display_label, created_at", (patient_id, actor.clinic_id, display_label))
            row = cur.fetchone()
            return dict(zip([d.name for d in cur.description], row))

    def delete_patient(self, actor: Actor, patient_id: str) -> dict:
        if actor.role != Role.ADMIN:
            raise PermissionError("only admins can delete patient pages")
        with self.request(actor) as cur:
            cur.execute("DELETE FROM patients WHERE id=%s RETURNING id,display_label", (patient_id,))
            row = cur.fetchone()
            if not row:
                raise PermissionError("patient page is unavailable or outside this clinic")
            return dict(zip([d.name for d in cur.description], row))

    def bind_patient_account(self, actor: Actor, patient_id: str, patient_user_id: str) -> None:
        if actor.role != Role.ADMIN:
            raise PermissionError("only admins can bind a patient account")
        with self.request(actor) as cur:
            cur.execute(
                "INSERT INTO patient_accounts(patient_id,patient_user_id,clinic_id) VALUES (%s,%s,%s) "
                "ON CONFLICT (patient_id) DO UPDATE SET patient_user_id=EXCLUDED.patient_user_id, clinic_id=EXCLUDED.clinic_id",
                (patient_id, patient_user_id, actor.clinic_id),
            )

    def create_entry(self, actor: Actor, patient_id: str, section: str, content: str,
                     entry_type: str, risk_level: int = 0, tags: list[str] | None = None,
                     open_action: bool = False, provenance_pointer: str | None = None) -> dict:
        validate_entry_create(actor, section, entry_type)
        entry_id = new_id("entry")
        with self.request(actor) as cur:
            cur.execute("""INSERT INTO care_entries(id,patient_id,clinic_id,section,content,author_id,author_role,entry_type,provenance_pointer,risk_level,tags,open_action)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id,section,content,author_id,author_role,entry_type,provenance_pointer,risk_level,tags,open_action,version,created_at""",
                (entry_id, patient_id, actor.clinic_id, section, content, actor.id, actor.role.value, entry_type, provenance_pointer, risk_level, tags or [], open_action))
            row = cur.fetchone(); result = dict(zip([d.name for d in cur.description], row))
            cur.execute("INSERT INTO entry_versions(entry_id,version,content,changed_by,change_reason) VALUES (%s,1,%s,%s,'created')", (entry_id, content, actor.id))
            cur.execute("INSERT INTO audit_log(entry_id,actor_id,action,metadata) VALUES (%s,%s,'created',jsonb_build_object('section',%s::text))", (entry_id, actor.id, section))
            return result

    def comments(self, actor: Actor, entry_id: str) -> list[dict]:
        with self.request(actor) as cur:
            cur.execute("""SELECT c.id,c.author_id,c.author_role,c.body,c.mention_user_id,
                c.assigned_to,c.resolved,c.created_at,
                COALESCE((SELECT array_agg(u.username ORDER BY u.username)
                  FROM comment_mentions cm JOIN app_users u ON u.id=cm.mentioned_user_id
                  WHERE cm.comment_id=c.id), ARRAY[]::text[]) AS mention_usernames
                FROM comments c WHERE c.entry_id=%s ORDER BY c.created_at""", (entry_id,))
            return self._rows(cur)

    def mentionable_users(self, actor: Actor, entry_id: str) -> list[dict]:
        """People in the same clinic who can read comments on this entry."""
        if actor.role == Role.PATIENT:
            return []
        with self.request(actor) as cur:
            cur.execute("SELECT entry_type FROM care_entries WHERE id=%s", (entry_id,))
            entry = cur.fetchone()
            if not entry:
                raise PermissionError("entry is unavailable")
            cur.execute("""SELECT u.id,u.username,u.role::text,u.clinician_kind
                FROM app_users u
                WHERE u.active AND u.clinic_id=%s AND u.id<>%s
                  AND (u.role IN ('clinician','admin')
                    OR (u.role='staff' AND %s='staff_manual_log'))
                ORDER BY u.username""", (actor.clinic_id, actor.id, entry[0]))
            return self._rows(cur)

    def highlights(self, actor: Actor, patient_id: str) -> list[dict]:
        with self.request(actor) as cur:
            cur.execute("SELECT id,entry_id,span_start,span_end,risk_reason,provenance_pointer,priority,origin,reason_entry_id FROM highlights WHERE patient_id=%s ORDER BY created_at", (patient_id,))
            results = self._rows(cur)
            cur.execute("SELECT id FROM care_entries WHERE patient_id=%s", (patient_id,))
            visible_ids = {row[0] for row in cur.fetchall()}
            for result in results:
                result["reason_visible"] = bool(result["reason_entry_id"] and result["reason_entry_id"] in visible_ids)
            return results

    def create_highlight(self, actor: Actor, *, patient_id: str, entry_id: str, keyword: str,
                         reason: str, reason_entry_id: str | None, origin: str = "clinician") -> dict:
        if actor.role not in {Role.CLINICIAN, Role.ADMIN} and origin != "ai":
            raise PermissionError("only clinicians and admins can manually highlight records")
        with self.request(actor) as cur:
            cur.execute("SELECT content,entry_type FROM care_entries WHERE id=%s AND patient_id=%s", (entry_id, patient_id))
            target = cur.fetchone()
            if not target:
                raise PermissionError("highlight target is unavailable")
            if origin == "ai" and target[1] not in AI_HIGHLIGHT_TYPES:
                raise PermissionError("automatic AI highlights can only target AI records")
            start = target[0].lower().find(keyword.lower())
            if start < 0: raise ValueError("keyword does not appear in the AI-scribed entry")
            if reason_entry_id:
                cur.execute("SELECT id FROM care_entries WHERE id=%s AND patient_id=%s", (reason_entry_id, patient_id))
                if not cur.fetchone(): raise PermissionError("reason source is unavailable")
            pointer = f"timeline:{reason_entry_id or entry_id}"
            highlight_id = new_id("highlight")
            cur.execute("""INSERT INTO highlights(id,patient_id,entry_id,span_start,span_end,risk_reason,provenance_pointer,priority,origin,reason_entry_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id,entry_id,span_start,span_end,risk_reason,provenance_pointer,priority,origin,reason_entry_id""",
                (highlight_id,patient_id,entry_id,start,start+len(keyword),reason,pointer,80 if origin=='clinician' else 60,origin,reason_entry_id))
            return dict(zip([d.name for d in cur.description], cur.fetchone()))

    def delete_highlight(self, actor: Actor, highlight_id: str) -> dict:
        if actor.role not in {Role.CLINICIAN, Role.ADMIN}:
            raise PermissionError("only clinicians and admins can delete highlights")
        with self.request(actor) as cur:
            cur.execute("DELETE FROM highlights WHERE id=%s RETURNING id,patient_id,entry_id", (highlight_id,))
            row = cur.fetchone()
            if not row:
                raise PermissionError("highlight is unavailable or outside this clinic")
            return dict(zip([d.name for d in cur.description], row))

    def auto_highlight(self, actor: Actor, patient_id: str, entry_id: str, reason_entry_id: str | None) -> list[dict]:
        """Lightweight AI-scribe post-processing; callers can opt out."""
        with self.request(actor) as cur:
            cur.execute("SELECT content FROM care_entries WHERE id=%s AND patient_id=%s", (entry_id, patient_id))
            row = cur.fetchone()
        if not row: return []
        candidates = ("allergy", "dizziness", "medication", "follow-up", "urgent", "risk")
        results = []
        for keyword in candidates:
            if keyword in row[0].lower():
                results.append(self.create_highlight(actor, patient_id=patient_id, entry_id=entry_id, keyword=keyword, reason=f"AI-scribed note identified '{keyword}' as clinically relevant.", reason_entry_id=reason_entry_id, origin="ai"))
        return results

    def add_comment(self, actor: Actor, entry_id: str, body: str, mention: str | None = None) -> dict:
        body = body.strip()
        if not body:
            raise ValueError("comment body is required")
        usernames = set(MENTION_PATTERN.findall(body))
        if mention:
            usernames.add(mention.lstrip("@"))
        with self.request(actor) as cur:
            cur.execute("SELECT entry_type FROM care_entries WHERE id=%s", (entry_id,))
            entry = cur.fetchone()
            if not entry or actor.role == Role.PATIENT:
                raise PermissionError("comments are unavailable")
            mentioned_users = []
            if usernames:
                cur.execute("""SELECT id,username,role::text FROM app_users
                    WHERE active AND clinic_id=%s AND username=ANY(%s)
                      AND id<>%s
                      AND (role IN ('clinician','admin') OR (role='staff' AND %s='staff_manual_log'))
                    ORDER BY username""", (actor.clinic_id, list(usernames), actor.id, entry[0]))
                mentioned_users = cur.fetchall()
                found = {row[1] for row in mentioned_users}
                unavailable = sorted(usernames - found)
                if unavailable:
                    raise PermissionError(f"mention unavailable for this entry: {', '.join(unavailable)}")
            comment_id = new_id('comment')
            legacy_mention = mentioned_users[0][0] if mentioned_users else None
            cur.execute("""INSERT INTO comments(id,entry_id,author_id,author_role,body,mention_user_id)
                VALUES (%s,%s,%s,%s,%s,%s)
                RETURNING id,author_id,author_role,body,mention_user_id,created_at""",
                (comment_id, entry_id, actor.id, actor.role.value, body, legacy_mention))
            result = dict(zip([d.name for d in cur.description], cur.fetchone()))
            for user_id, _username, _role in mentioned_users:
                cur.execute("""INSERT INTO comment_mentions(comment_id,mentioned_user_id,clinic_id)
                    VALUES (%s,%s,%s)""", (comment_id, user_id, actor.clinic_id))
            result["mention_usernames"] = [row[1] for row in mentioned_users]
            return result

    def notifications(self, actor: Actor) -> list[dict]:
        with self.request(actor) as cur:
            cur.execute("""SELECT cm.comment_id AS notification_id,cm.read_at,cm.created_at,
                c.body,c.author_id,COALESCE(author.username,c.author_id) AS author_username,
                e.id AS entry_id,e.patient_id,e.entry_type,p.display_label AS patient_label
                FROM comment_mentions cm
                JOIN comments c ON c.id=cm.comment_id
                JOIN care_entries e ON e.id=c.entry_id
                JOIN patients p ON p.id=e.patient_id
                LEFT JOIN app_users author ON author.id=c.author_id
                WHERE cm.mentioned_user_id=%s
                ORDER BY (cm.read_at IS NULL) DESC,cm.created_at DESC""", (actor.id,))
            return self._rows(cur)

    def mark_notification_read(self, actor: Actor, notification_id: str) -> dict:
        with self.request(actor) as cur:
            cur.execute("""UPDATE comment_mentions SET read_at=COALESCE(read_at,now())
                WHERE comment_id=%s AND mentioned_user_id=%s
                RETURNING comment_id AS notification_id,read_at""", (notification_id, actor.id))
            row = cur.fetchone()
            if not row:
                raise PermissionError("notification is unavailable")
            return dict(zip([d.name for d in cur.description], row))

    def versions(self, actor: Actor, entry_id: str) -> list[dict]:
        with self.request(actor) as cur:
            cur.execute("SELECT version,content,changed_by,change_reason,changed_at FROM entry_versions WHERE entry_id=%s ORDER BY version DESC", (entry_id,))
            return self._rows(cur)

    def edit_with_version(self, actor: Actor, entry_id: str, content: str, expected_version: int) -> int:
        """Optimistic locking: a stale same-section edit updates zero rows and is rejected."""
        with self.request(actor) as cur:
            cur.execute("SELECT entry_type FROM care_entries WHERE id=%s", (entry_id,))
            entry = cur.fetchone()
            if not entry or not can_edit_entry(actor, entry[0]):
                raise PermissionError("role cannot edit this record type")
            cur.execute("UPDATE care_entries SET content=%s, version=version+1, updated_at=now() WHERE id=%s AND version=%s RETURNING version", (content, entry_id, expected_version))
            row = cur.fetchone()
            if not row:
                raise ValueError("conflict or permission denied")
            version = row[0]
            cur.execute("INSERT INTO entry_versions(entry_id, version, content, changed_by, change_reason) VALUES (%s,%s,%s,%s,'edited')", (entry_id, version, content, actor.id))
            cur.execute("INSERT INTO audit_log(entry_id, actor_id, action, metadata) VALUES (%s,%s,'edited',jsonb_build_object('version',%s::integer))", (entry_id, actor.id, version))
            return version

    def revert(self, actor: Actor, entry_id: str, target_version: int) -> int:
        with self.request(actor) as cur:
            cur.execute("SELECT entry_type FROM care_entries WHERE id=%s", (entry_id,))
            entry = cur.fetchone()
            if not entry or not can_edit_entry(actor, entry[0]):
                raise PermissionError("role cannot revert this record type")
            cur.execute("SELECT content FROM entry_versions WHERE entry_id=%s AND version=%s", (entry_id, target_version))
            prior = cur.fetchone()
            if not prior:
                raise ValueError("version unavailable")
            cur.execute("UPDATE care_entries SET content=%s,version=version+1,updated_at=now() WHERE id=%s RETURNING version", (prior[0], entry_id))
            updated = cur.fetchone()
            if not updated: raise ValueError("permission denied")
            version = updated[0]
            cur.execute("INSERT INTO entry_versions(entry_id,version,content,changed_by,change_reason) VALUES (%s,%s,%s,%s,%s)", (entry_id, version, prior[0], actor.id, f"reverted to {target_version}"))
            cur.execute("INSERT INTO audit_log(entry_id,actor_id,action,metadata) VALUES (%s,%s,'reverted',jsonb_build_object('from_version',%s::integer,'to_version',%s::integer))", (entry_id, actor.id, target_version, version))
            return version

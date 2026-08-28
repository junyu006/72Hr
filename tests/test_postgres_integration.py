"""PostgreSQL integration tests for RLS, history, provenance, and concurrency.

Set NIGHTINGALE_TEST_DATABASE_URL to a fully migrated Nightingale database using
the restricted nightingale_app role. Each test creates a uniquely scoped
synthetic patient and deletes it in tearDown.
"""
from __future__ import annotations

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from nightingale.domain import Actor, ClinicianKind, Role
from nightingale.postgres import PostgresStore


TEST_DATABASE_URL = os.environ.get("NIGHTINGALE_TEST_DATABASE_URL")


@unittest.skipUnless(TEST_DATABASE_URL, "set NIGHTINGALE_TEST_DATABASE_URL to run PostgreSQL integration tests")
class PostgresIntegrationTests(unittest.TestCase):
    def setUp(self):
        suffix = uuid4().hex[:10]
        self.store = PostgresStore(TEST_DATABASE_URL)
        self.actors = {
            "admin": Actor(f"it_admin_{suffix}", Role.ADMIN, f"it_clinic_{suffix}"),
            "staff": Actor(f"it_staff_{suffix}", Role.STAFF, f"it_clinic_{suffix}"),
            "doctor": Actor(f"it_doctor_{suffix}", Role.CLINICIAN, f"it_clinic_{suffix}", ClinicianKind.DOCTOR),
            "patient": Actor(f"it_patient_{suffix}", Role.PATIENT, f"it_clinic_{suffix}"),
            "system": Actor(f"it_system_{suffix}", Role.SYSTEM, f"it_clinic_{suffix}"),
            "other_staff": Actor(f"it_other_staff_{suffix}", Role.STAFF, f"it_other_clinic_{suffix}"),
        }
        self.patient_id = self.store.create_patient(self.actors["admin"], "Integration Test Patient")["id"]
        self.addCleanup(self._delete_synthetic_patient)
        self.store.bind_patient_account(self.actors["admin"], self.patient_id, self.actors["patient"].id)

    def _delete_synthetic_patient(self):
        patient_id = getattr(self, "patient_id", None)
        if patient_id:
            self.store.delete_patient(self.actors["admin"], patient_id)
            self.patient_id = None

    def test_postgres_rls_enforces_role_and_patient_scope(self):
        staff_entry = self.store.create_entry(
            self.actors["staff"], self.patient_id, "staff_notes", "internal staff comment", "staff_manual_log"
        )
        self.store.add_comment(self.actors["doctor"], staff_entry["id"], "internal comment")
        public_entry = self.store.create_entry(
            self.actors["doctor"], self.patient_id, "patient_facing", "patient instruction", "patient_facing_log"
        )
        ai_entry = self.store.create_entry(
            self.actors["system"], self.patient_id, "ai_scribed", "raw AI-scribed note", "ai_scribe_log"
        )

        with self.assertRaises(PermissionError):
            self.store.create_entry(
                self.actors["staff"], self.patient_id, "clinician_sections", "wrong", "clinician_manual_log"
            )
        with self.assertRaises(PermissionError):
            self.store.create_entry(
                self.actors["doctor"], self.patient_id, "staff_notes", "wrong", "staff_manual_log"
            )
        with self.assertRaises(PermissionError):
            self.store.edit_with_version(self.actors["doctor"], staff_entry["id"], "wrong", 1)
        with self.assertRaises(PermissionError):
            self.store.edit_with_version(self.actors["staff"], public_entry["id"], "wrong", 1)

        # Bypass the repository's early type check and prove PostgreSQL RLS also
        # prevents the cross-role updates at the data boundary.
        with self.store.request(self.actors["doctor"]) as cursor:
            cursor.execute("UPDATE care_entries SET content='wrong' WHERE id=%s", (staff_entry["id"],))
            self.assertEqual(cursor.rowcount, 0)
        with self.store.request(self.actors["staff"]) as cursor:
            cursor.execute("UPDATE care_entries SET content='wrong' WHERE id=%s", (public_entry["id"],))
            self.assertEqual(cursor.rowcount, 0)

        patient_entries = self.store.timeline(self.actors["patient"], self.patient_id)
        self.assertEqual([entry["id"] for entry in patient_entries], [public_entry["id"]])
        self.assertNotIn(ai_entry["id"], {entry["id"] for entry in patient_entries})
        self.assertEqual(self.store.comments(self.actors["patient"], staff_entry["id"]), [])
        self.assertEqual(self.store.timeline(self.actors["other_staff"], self.patient_id), [])

    def test_postgres_revision_revert_and_metadata_only_audit(self):
        entry = self.store.create_entry(
            self.actors["doctor"], self.patient_id, "clinician_sections", "version one", "clinician_manual_log"
        )
        self.assertEqual(self.store.edit_with_version(self.actors["doctor"], entry["id"], "version two", 1), 2)
        self.assertEqual(self.store.revert(self.actors["doctor"], entry["id"], 1), 3)

        versions = self.store.versions(self.actors["doctor"], entry["id"])
        self.assertEqual([(row["version"], row["content"]) for row in versions], [(3, "version one"), (2, "version two"), (1, "version one")])
        with self.store.request(self.actors["doctor"]) as cursor:
            cursor.execute(
                "SELECT actor_id,action,metadata FROM audit_log WHERE entry_id=%s AND action='reverted'",
                (entry["id"],),
            )
            actor_id, action, metadata = cursor.fetchone()
        self.assertEqual((actor_id, action), (self.actors["doctor"].id, "reverted"))
        self.assertEqual(metadata, {"from_version": 1, "to_version": 3})
        self.assertNotIn("content", metadata)

    def test_postgres_highlight_provenance_resolves_entry_and_span(self):
        consult = self.store.create_entry(
            self.actors["doctor"], self.patient_id, "clinician_sections", "Allergy discussed", "doctor_patient_consult"
        )
        ai_entry = self.store.create_entry(
            self.actors["system"], self.patient_id, "ai_scribed", "Synthetic allergy risk", "ai_scribe_log",
            provenance_pointer=f"entry:{consult['id']}",
        )
        highlight = self.store.create_highlight(
            self.actors["doctor"], patient_id=self.patient_id, entry_id=ai_entry["id"], keyword="allergy risk",
            reason="Linked to source consult", reason_entry_id=consult["id"],
        )

        self.assertEqual(highlight["provenance_pointer"], f"timeline:{consult['id']}")
        timeline = {entry["id"]: entry for entry in self.store.timeline(self.actors["doctor"], self.patient_id)}
        resolved = timeline[highlight["entry_id"]]
        self.assertEqual(resolved["content"][highlight["span_start"]:highlight["span_end"]], "allergy risk")
        self.assertIn(consult["id"], timeline)

    def test_postgres_concurrent_edits_are_deterministic(self):
        staff_entry = self.store.create_entry(
            self.actors["staff"], self.patient_id, "staff_notes", "call", "staff_manual_log"
        )
        doctor_entry = self.store.create_entry(
            self.actors["doctor"], self.patient_id, "clinician_sections", "plan", "clinician_manual_log"
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            independent = [
                executor.submit(self.store.edit_with_version, self.actors["staff"], staff_entry["id"], "called", 1),
                executor.submit(self.store.edit_with_version, self.actors["doctor"], doctor_entry["id"], "updated plan", 1),
            ]
            self.assertEqual([future.result() for future in independent], [2, 2])

        conflict_entry = self.store.create_entry(
            self.actors["doctor"], self.patient_id, "clinician_sections", "base", "clinician_manual_log"
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            contenders = [
                executor.submit(self.store.edit_with_version, self.actors["doctor"], conflict_entry["id"], content, 1)
                for content in ("candidate A", "candidate B")
            ]
        successes, conflicts = [], []
        for future in contenders:
            try:
                successes.append(future.result())
            except ValueError as exc:
                conflicts.append(str(exc))
        self.assertEqual(successes, [2])
        self.assertEqual(conflicts, ["conflict or permission denied"])
        final_entry = next(
            entry for entry in self.store.timeline(self.actors["doctor"], self.patient_id)
            if entry["id"] == conflict_entry["id"]
        )
        self.assertIn(final_entry["content"], {"candidate A", "candidate B"})
        self.assertEqual(final_entry["version"], 2)


@unittest.skipUnless(TEST_DATABASE_URL, "set NIGHTINGALE_TEST_DATABASE_URL to run PostgreSQL integration tests")
class PostgresMentionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.store = PostgresStore(TEST_DATABASE_URL)
        self.admin = Actor("admin_demo", Role.ADMIN, "clinic_demo")
        self.doctor = Actor("doctor_demo", Role.CLINICIAN, "clinic_demo", ClinicianKind.DOCTOR)
        self.nurse = Actor("nurse_demo", Role.CLINICIAN, "clinic_demo", ClinicianKind.NURSE)
        self.patient_id = self.store.create_patient(self.admin, "Mention Integration Patient")["id"]
        self.addCleanup(self._delete_synthetic_patient)

    def _delete_synthetic_patient(self):
        if self.patient_id:
            self.store.delete_patient(self.admin, self.patient_id)
            self.patient_id = None

    def test_mentions_create_private_notification_and_deep_link_data(self):
        entry = self.store.create_entry(
            self.doctor, self.patient_id, "clinician_sections", "Care plan", "clinician_manual_log"
        )
        people = {person["username"] for person in self.store.mentionable_users(self.doctor, entry["id"])}
        if "nurse_demo" not in people:
            self.skipTest("seed the demo accounts before running mention integration tests")
        self.assertIn("admin_demo", people)
        self.assertNotIn("staff_demo", people)
        comment = self.store.add_comment(
            self.doctor, entry["id"], "Please review this plan @nurse_demo"
        )
        self.assertEqual(comment["mention_usernames"], ["nurse_demo"])
        rendered = self.store.comments(self.doctor, entry["id"])
        self.assertEqual(rendered[0]["mention_usernames"], ["nurse_demo"])

        notification = next(
            item for item in self.store.notifications(self.nurse)
            if item["notification_id"] == comment["id"]
        )
        self.assertIsNone(notification["read_at"])
        self.assertEqual(notification["patient_id"], self.patient_id)
        self.assertEqual(notification["entry_id"], entry["id"])
        self.store.mark_notification_read(self.nurse, comment["id"])
        refreshed = next(
            item for item in self.store.notifications(self.nurse)
            if item["notification_id"] == comment["id"]
        )
        self.assertIsNotNone(refreshed["read_at"])

        with self.assertRaises(PermissionError):
            self.store.add_comment(self.doctor, entry["id"], "This must not notify @staff_demo")


if __name__ == "__main__":
    unittest.main()

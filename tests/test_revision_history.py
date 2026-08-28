import unittest

from tests.helpers import setup_service


class RevisionHistoryTests(unittest.TestCase):
    def test_edit_versions_revert_and_audit_metadata(self):
        service, a = setup_service()
        entry = service.create_entry(a["clinician"], patient_id="p1", section="clinician_sections", content="v1", entry_type="clinician_manual_log")
        edited = service.edit(a["clinician"], entry.id, "v2", expected_version=1)
        self.assertEqual(edited.version, 2)
        reverted = service.revert(a["clinician"], entry.id, 1)
        self.assertEqual(reverted.content, "v1")
        self.assertEqual(reverted.version, 3)
        event = service.audit_log[-1]
        self.assertEqual(event.action, "reverted")
        self.assertEqual(event.actor_id, a["clinician"].id)
        self.assertEqual(event.metadata, {"from_version": 1, "to_version": 3})
        self.assertNotIn("content", event.metadata)
        self.assertNotIn("v1", str(event.metadata))

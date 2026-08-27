import unittest

from nightingale.service import PermissionDenied
from tests.helpers import setup_service


class ConcurrentEditTests(unittest.TestCase):
    def test_different_sections_do_not_overwrite_each_other(self):
        service, a = setup_service()
        staff = service.create_entry(a["staff"], patient_id="p1", section="staff_notes", content="call", entry_type="staff_manual_log")
        plan = service.create_entry(a["clinician"], patient_id="p1", section="clinician_sections", content="plan", entry_type="clinician_manual_log")
        service.edit(a["staff"], staff.id, "called", 1)
        service.edit(a["clinician"], plan.id, "updated plan", 1)
        self.assertEqual(service.entries[staff.id].content, "called")
        self.assertEqual(service.entries[plan.id].content, "updated plan")

    def test_same_section_uses_optimistic_version_conflict(self):
        service, a = setup_service()
        entry = service.create_entry(a["clinician"], patient_id="p1", section="clinician_sections", content="v1", entry_type="clinician_manual_log")
        service.edit(a["clinician"], entry.id, "v2", 1)
        with self.assertRaises(PermissionDenied): service.edit(a["clinician"], entry.id, "stale v2", 1)

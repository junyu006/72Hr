import unittest

from tests.helpers import setup_service


class HighlightProvenanceTests(unittest.TestCase):
    def test_ai_highlight_resolves_to_source_entry_and_span(self):
        service, a = setup_service()
        source = service.ingest_ai_scribe(a["system"], patient_id="p1", content="Synthetic allergy risk", ai_type="ai_doctor_consult_summary", session_id="session_7", risk_level=3, tags={"allergy"})
        highlight = service.highlight(a["clinician"], source.id, "risk level 3", 90, (10, 22))
        self.assertIn(source.id, highlight.provenance_pointer)
        self.assertEqual(service.resolve_provenance(a["clinician"], highlight.id).id, source.id)

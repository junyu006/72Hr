import unittest

from nightingale.importance import importance
from tests.helpers import setup_service


class SelfLearningTests(unittest.TestCase):
    def test_accepted_topic_is_prioritized_next_time(self):
        service, a = setup_service()
        first = service.ingest_ai_scribe(a["system"], patient_id="p1", content="medication issue", ai_type="ai_patient_session_summary", session_id="s1", tags={"medication"})
        h = service.highlight(a["clinician"], first.id, "review medication", 20)
        before, _ = importance(first, service.feedback_weights)
        service.record_highlight_feedback(a["clinician"], h.id, True)
        later = service.ingest_ai_scribe(a["system"], patient_id="p1", content="another medication issue", ai_type="ai_patient_session_summary", session_id="s2", tags={"medication"})
        after, _ = importance(later, service.feedback_weights)
        self.assertGreater(after, before)

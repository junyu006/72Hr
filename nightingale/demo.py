from __future__ import annotations

from time import perf_counter

from .domain import Actor, Role
from .importance import importance
from .service import CareService


def main() -> None:
    service = CareService()
    clinician = Actor("clinician_ava", Role.CLINICIAN, "clinic_demo")
    system = Actor("scribe", Role.SYSTEM, "clinic_demo")
    service.ingest_ai_scribe(system, patient_id="patient_synthetic_01", session_id="session_001",
        ai_type="ai_doctor_consult_summary", content="Synthetic summary: medication review requested.",
        risk_level=2, tags={"medication"})
    service.create_entry(clinician, patient_id="patient_synthetic_01", section="clinician_sections",
        entry_type="plan", content="Order follow-up lab.", risk_level=2, tags={"lab"}, open_action=True)
    started = perf_counter()
    entries = service.timeline(clinician, "patient_synthetic_01")
    ranked = sorted(((importance(e, service.feedback_weights), e) for e in entries), reverse=True, key=lambda x: x[0][0])
    elapsed_ms = (perf_counter() - started) * 1000
    print(f"Glance View ({elapsed_ms:.2f} ms warm-path approximation)")
    for (score, reason), entry in ranked[:3]:
        print(f"- {score:.1f}: {entry.content} [{reason}] → timeline:{entry.id}")


if __name__ == "__main__":
    main()

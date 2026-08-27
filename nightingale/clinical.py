"""Canonical record taxonomy, role permissions, and safe provenance rules."""
from __future__ import annotations

import re

from .domain import Actor, ClinicianKind, Role

SYSTEM_GENERATED_EVENT = "system_generated_event"
AI_SCRIBE_LOG = "ai_scribe_log"
DOCTOR_PATIENT_CONSULT = "doctor_patient_consult"
NURSE_PATIENT_CONSULT = "nurse_patient_consult"
AI_PATIENT_CONSULT = "ai_patient_consult"
STAFF_MANUAL_LOG = "staff_manual_log"
CLINICIAN_MANUAL_LOG = "clinician_manual_log"
PATIENT_FACING_LOG = "patient_facing_log"

ENTRY_SECTIONS = {
    SYSTEM_GENERATED_EVENT: "ai_scribed",
    AI_SCRIBE_LOG: "ai_scribed",
    DOCTOR_PATIENT_CONSULT: "clinician_sections",
    NURSE_PATIENT_CONSULT: "clinician_sections",
    AI_PATIENT_CONSULT: "ai_scribed",
    STAFF_MANUAL_LOG: "staff_notes",
    CLINICIAN_MANUAL_LOG: "clinician_sections",
    PATIENT_FACING_LOG: "patient_facing",
}

RECORD_LABELS = {
    SYSTEM_GENERATED_EVENT: "System generated event",
    AI_SCRIBE_LOG: "AI scribe log",
    DOCTOR_PATIENT_CONSULT: "Doctor–Patient Consult",
    NURSE_PATIENT_CONSULT: "Nurse–Patient Consult",
    AI_PATIENT_CONSULT: "AI–Patient Consult",
    STAFF_MANUAL_LOG: "Staff manual log",
    CLINICIAN_MANUAL_LOG: "Clinician manual log",
    PATIENT_FACING_LOG: "Patient-facing log",
}

SYSTEM_TYPES = {SYSTEM_GENERATED_EVENT, AI_SCRIBE_LOG, AI_PATIENT_CONSULT}
DOCTOR_TYPES = {DOCTOR_PATIENT_CONSULT, CLINICIAN_MANUAL_LOG, PATIENT_FACING_LOG}
NURSE_TYPES = {NURSE_PATIENT_CONSULT, CLINICIAN_MANUAL_LOG, PATIENT_FACING_LOG}
AI_HIGHLIGHT_TYPES = {AI_SCRIBE_LOG, AI_PATIENT_CONSULT}
CONSULT_SUMMARY_TYPES = {
    DOCTOR_PATIENT_CONSULT: AI_SCRIBE_LOG,
    NURSE_PATIENT_CONSULT: AI_SCRIBE_LOG,
}


def allowed_create_types(actor: Actor) -> set[str]:
    if actor.role == Role.PATIENT:
        return set()
    if actor.role == Role.STAFF:
        return {STAFF_MANUAL_LOG}
    if actor.role == Role.SYSTEM:
        return set(SYSTEM_TYPES)
    if actor.role == Role.ADMIN:
        return set(ENTRY_SECTIONS)
    if actor.role == Role.CLINICIAN:
        if actor.clinician_kind == ClinicianKind.DOCTOR:
            return set(DOCTOR_TYPES)
        if actor.clinician_kind == ClinicianKind.NURSE:
            return set(NURSE_TYPES)
    return set()


def validate_entry_create(actor: Actor, section: str, entry_type: str) -> None:
    expected_section = ENTRY_SECTIONS.get(entry_type)
    if expected_section is None:
        raise PermissionError("unknown record type")
    if section != expected_section:
        raise PermissionError("record type does not match its required section")
    if entry_type not in allowed_create_types(actor):
        raise PermissionError("role cannot create this record type")


def validate_clinical_entry(actor: Actor, entry_type: str) -> None:
    """Compatibility wrapper used by focused subtype tests."""
    if entry_type not in allowed_create_types(actor):
        raise PermissionError("role cannot create this record type")


def can_edit_entry(actor: Actor, entry_type: str) -> bool:
    if actor.role == Role.ADMIN:
        return entry_type in ENTRY_SECTIONS
    if actor.role == Role.STAFF:
        return entry_type == STAFF_MANUAL_LOG
    if actor.role == Role.CLINICIAN:
        return entry_type in allowed_create_types(actor)
    return False


def ai_summary_type(entry_type: str) -> str | None:
    return CONSULT_SUMMARY_TYPES.get(entry_type)


def attach_consult_source(summary: str, consult_entry_id: str) -> str:
    """Attach a trusted citation after inference instead of asking the model to copy an ID."""
    return f"{summary.strip()}\n\nSource consult: {consult_entry_id}"


def authorised_summary_sources(summary: str, entries: list[dict]) -> list[dict]:
    """Return only IDs mentioned by the model that are already RLS-visible."""
    referenced_ids = set(re.findall(r"\bentry_[0-9a-f]+\b", summary))
    return [
        {"entry_id": entry["id"], "label": entry["content"][:72]}
        for entry in entries if entry["id"] in referenced_ids
    ]

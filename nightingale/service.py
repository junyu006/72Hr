from __future__ import annotations

import re
from collections import defaultdict
from copy import deepcopy
from datetime import datetime

from .domain import Actor, AuditEvent, Comment, Entry, Highlight, Role, Version, new_id
from .clinical import AI_HIGHLIGHT_TYPES, AI_SCRIBE_LOG, can_edit_entry, validate_entry_create


class PermissionDenied(Exception):
    pass


class NotFound(Exception):
    pass


class CareService:
    """The server-side application boundary; callers never mutate entries directly."""
    def __init__(self) -> None:
        self.entries: dict[str, Entry] = {}
        self.versions: dict[str, list[Version]] = defaultdict(list)
        self.comments: dict[str, list[Comment]] = defaultdict(list)
        self.highlights: dict[str, Highlight] = {}
        self.audit_log: list[AuditEvent] = []
        self.feedback_weights: dict[str, int] = defaultdict(int)

    def _entry(self, entry_id: str) -> Entry:
        if entry_id not in self.entries:
            raise NotFound(entry_id)
        return self.entries[entry_id]

    def _same_clinic(self, actor: Actor, entry: Entry) -> None:
        if actor.role != Role.SYSTEM and actor.clinic_id != entry.clinic_id:
            raise PermissionDenied("cross-clinic access denied")

    def _can_read(self, actor: Actor, entry: Entry) -> bool:
        self._same_clinic(actor, entry)
        if actor.role == Role.PATIENT:
            return entry.type == "patient_facing_log"
        if actor.role == Role.STAFF:
            return entry.section == "staff_notes"
        return actor.role in {Role.CLINICIAN, Role.ADMIN, Role.SYSTEM}

    def _can_write(self, actor: Actor, entry: Entry) -> bool:
        self._same_clinic(actor, entry)
        return can_edit_entry(actor, entry.type)

    def create_entry(self, actor: Actor, *, patient_id: str, section: str, content: str,
                     entry_type: str, provenance_pointer: str | None = None, risk_level: int = 0,
                     tags: set[str] | None = None, open_action: bool = False) -> Entry:
        try:
            validate_entry_create(actor, section, entry_type)
        except PermissionError as exc:
            raise PermissionDenied(str(exc)) from exc
        entry = Entry(new_id("entry"), patient_id, actor.clinic_id, section, content, actor.id,
                      actor.role, entry_type, provenance_pointer, risk_level, tags or set(), open_action)
        self.entries[entry.id] = entry
        self.versions[entry.id].append(Version(entry.id, 1, content, actor.id, entry.created_at, "created"))
        self.audit_log.append(AuditEvent("created", actor.id, entry.id, {"section": section}))
        return deepcopy(entry)

    def ingest_ai_scribe(self, system: Actor, *, patient_id: str, content: str, ai_type: str,
                         session_id: str, risk_level: int = 0, tags: set[str] | None = None) -> Entry:
        if system.role != Role.SYSTEM:
            raise PermissionDenied("AI scribe is system generated")
        entry = Entry(new_id("entry"), patient_id, system.clinic_id, "ai_scribed", content, system.id,
                      Role.SYSTEM, AI_SCRIBE_LOG, f"session:{session_id}", risk_level, tags or set())
        self.entries[entry.id] = entry
        self.versions[entry.id].append(Version(entry.id, 1, content, system.id, entry.created_at, "AI ingest"))
        self.audit_log.append(AuditEvent("ai_ingested", system.id, entry.id, {"source": session_id}))
        return deepcopy(entry)

    def timeline(self, actor: Actor, patient_id: str) -> list[Entry]:
        results = [deepcopy(e) for e in self.entries.values() if e.patient_id == patient_id and self._can_read(actor, e)]
        return sorted(results, key=lambda e: e.created_at, reverse=True)

    def edit(self, actor: Actor, entry_id: str, content: str, expected_version: int | None = None) -> Entry:
        entry = self._entry(entry_id)
        if not self._can_write(actor, entry):
            raise PermissionDenied("role cannot edit this entry")
        if expected_version is not None and expected_version != entry.version:
            raise PermissionDenied("stale version; deterministic last approved write rejected")
        entry.content, entry.version = content, entry.version + 1
        version = Version(entry.id, entry.version, content, actor.id, datetime.now(entry.created_at.tzinfo), "edited")
        self.versions[entry.id].append(version)
        self.audit_log.append(AuditEvent("edited", actor.id, entry.id, {"version": entry.version}))
        return deepcopy(entry)

    def revert(self, actor: Actor, entry_id: str, target_version: int) -> Entry:
        entry = self._entry(entry_id)
        if not self._can_write(actor, entry):
            raise PermissionDenied("role cannot revert this entry")
        prior = next((v for v in self.versions[entry_id] if v.version == target_version), None)
        if not prior:
            raise NotFound(f"version {target_version}")
        entry.content, entry.version = prior.content, entry.version + 1
        self.versions[entry.id].append(Version(entry.id, entry.version, entry.content, actor.id, datetime.now(entry.created_at.tzinfo), f"reverted to {target_version}"))
        self.audit_log.append(AuditEvent("reverted", actor.id, entry.id, {"from_version": target_version, "to_version": entry.version}))
        return deepcopy(entry)

    def add_comment(self, actor: Actor, entry_id: str, body: str, mention: str | None = None, assignment: str | None = None) -> Comment:
        entry = self._entry(entry_id)
        if not self._can_read(actor, entry) or actor.role == Role.PATIENT:
            raise PermissionDenied("internal comments unavailable")
        comment = Comment(new_id("comment"), entry_id, actor.id, actor.role, body, mention, assignment)
        self.comments[entry_id].append(comment)
        self.audit_log.append(AuditEvent("commented", actor.id, entry_id, {"mention": mention, "assignment": assignment}))
        return deepcopy(comment)

    def highlight(self, actor: Actor, entry_id: str, reason: str, priority: float, span: tuple[int, int] = (0, 0)) -> Highlight:
        entry = self._entry(entry_id)
        if actor.role not in {Role.CLINICIAN, Role.ADMIN} or not self._can_read(actor, entry):
            raise PermissionDenied("cannot create highlight")
        pointer = f"timeline:{entry.id}#span={span[0]}:{span[1]}"
        h = Highlight(new_id("highlight"), entry.patient_id, entry.id, reason, pointer, priority, *span)
        self.highlights[h.id] = h
        self.audit_log.append(AuditEvent("highlighted", actor.id, entry.id, {"reason": reason}))
        return h

    def resolve_provenance(self, actor: Actor, highlight_id: str) -> Entry:
        h = self.highlights[highlight_id]
        entry = self._entry(h.entry_id)
        if not self._can_read(actor, entry):
            raise PermissionDenied("source unavailable")
        return deepcopy(entry)

    def delete_highlight(self, actor: Actor, highlight_id: str) -> Highlight:
        if highlight_id not in self.highlights:
            raise NotFound(highlight_id)
        highlight = self.highlights[highlight_id]
        entry = self._entry(highlight.entry_id)
        if actor.role not in {Role.CLINICIAN, Role.ADMIN} or not self._can_read(actor, entry):
            raise PermissionDenied("cannot delete highlight")
        del self.highlights[highlight_id]
        self.audit_log.append(AuditEvent("highlight_deleted", actor.id, entry.id, {"highlight_id": highlight_id}))
        return highlight

    def record_highlight_feedback(self, actor: Actor, highlight_id: str, accepted: bool) -> None:
        h = self.highlights[highlight_id]
        entry = self._entry(h.entry_id)
        if actor.role not in {Role.CLINICIAN, Role.ADMIN} or not self._can_read(actor, entry):
            raise PermissionDenied("feedback denied")
        for tag in entry.tags:
            self.feedback_weights[tag] += 1 if accepted else -1
        self.highlights[highlight_id] = Highlight(**{**h.__dict__, "accepted": accepted})


def redact_for_llm(text: str) -> str:
    """Redact basic PHI patterns before an LLM boundary; production uses a validated DLP service too."""
    text = re.sub(r"\b\d{6}-?\d{2}-?\d{4}\b", "[REDACTED_ID]", text)
    text = re.sub(r"\b(?:\+65[ -]?)?\d{4}[ -]?\d{4}\b", "[REDACTED_PHONE]", text)
    return re.sub(r"\b(?:Mr|Ms|Mrs|Dr)\.?\s+[A-Z][a-z]+\b", "[REDACTED_NAME]", text)

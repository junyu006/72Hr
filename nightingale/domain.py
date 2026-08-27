from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def now() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, Enum):
    PATIENT = "patient"
    STAFF = "staff"
    CLINICIAN = "clinician"
    ADMIN = "admin"
    SYSTEM = "system"


class ClinicianKind(str, Enum):
    DOCTOR = "doctor"
    NURSE = "nurse"


@dataclass(frozen=True)
class Actor:
    id: str
    role: Role
    clinic_id: str
    clinician_kind: ClinicianKind | None = None


@dataclass
class Entry:
    id: str
    patient_id: str
    clinic_id: str
    section: str  # staff_notes | clinician_sections | patient_facing | ai_scribed
    content: str
    author_id: str
    author_role: Role
    type: str
    provenance_pointer: str | None = None
    risk_level: int = 0
    tags: set[str] = field(default_factory=set)
    open_action: bool = False
    created_at: datetime = field(default_factory=now)
    version: int = 1


@dataclass(frozen=True)
class Version:
    entry_id: str
    version: int
    content: str
    changed_by: str
    changed_at: datetime
    reason: str


@dataclass
class Comment:
    id: str
    entry_id: str
    author_id: str
    author_role: Role
    body: str
    mention: str | None = None
    assignment: str | None = None
    resolved: bool = False


@dataclass(frozen=True)
class Highlight:
    id: str
    patient_id: str
    entry_id: str
    risk_reason: str
    provenance_pointer: str
    priority: float
    span_start: int = 0
    span_end: int = 0
    accepted: bool | None = None


@dataclass(frozen=True)
class AuditEvent:
    action: str
    actor_id: str
    entry_id: str
    metadata: dict
    at: datetime = field(default_factory=now)

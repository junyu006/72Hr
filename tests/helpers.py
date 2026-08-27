from nightingale.domain import Actor, ClinicianKind, Role
from nightingale.service import CareService


def setup_service():
    service = CareService()
    return service, {
        "staff": Actor("staff_1", Role.STAFF, "clinic_a"),
        "clinician": Actor("doctor_1", Role.CLINICIAN, "clinic_a", ClinicianKind.DOCTOR),
        "nurse": Actor("nurse_1", Role.CLINICIAN, "clinic_a", ClinicianKind.NURSE),
        "patient": Actor("patient_1", Role.PATIENT, "clinic_a"),
        "other_staff": Actor("staff_2", Role.STAFF, "clinic_b"),
        "system": Actor("scribe", Role.SYSTEM, "clinic_a"),
        "admin": Actor("admin_1", Role.ADMIN, "clinic_a"),
    }

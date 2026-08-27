"""Create/update English-only local demo accounts. Never use these in production."""
from __future__ import annotations

import os

import psycopg

from nightingale.auth import hash_password

ACCOUNTS = (
    ("patient_demo", "patient_demo", "Patient123!", "patient", "clinic_demo", None, "patient_ava_synthetic"),
    ("staff_demo", "staff_demo", "Staff1234!", "staff", "clinic_demo", None, None),
    ("doctor_demo", "doctor_demo", "Doctor123!", "clinician", "clinic_demo", "doctor", None),
    ("nurse_demo", "nurse_demo", "Nurse1234!", "clinician", "clinic_demo", "nurse", None),
    ("admin_demo", "admin_demo", "Admin1234!", "admin", "clinic_demo", None, None),
    ("system_demo", "system_demo", "System123!", "system", "clinic_demo", None, None),
)


def main() -> None:
    database_url = os.environ.get("DATABASE_OWNER_URL")
    if not database_url:
        raise SystemExit("DATABASE_OWNER_URL is required; follow README.md Quick Start.")
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            for user_id, username, password, role, clinic_id, clinician_kind, patient_id in ACCOUNTS:
                cursor.execute(
                    """INSERT INTO app_users(id,username,password_hash,role,clinic_id,clinician_kind,patient_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (username) DO UPDATE SET password_hash=EXCLUDED.password_hash,
                      role=EXCLUDED.role,clinic_id=EXCLUDED.clinic_id,
                      clinician_kind=EXCLUDED.clinician_kind,patient_id=EXCLUDED.patient_id,active=true""",
                    (user_id, username, hash_password(password), role, clinic_id, clinician_kind, patient_id),
                )
    print(f"Seeded {len(ACCOUNTS)} local demo accounts.")


if __name__ == "__main__":
    main()

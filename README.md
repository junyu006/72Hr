# Nightingale — care-note prototype

A compact Python/PostgreSQL framework for a shared longitudinal care note. It uses **synthetic data only** and demonstrates clinic-scoped RBAC, immutable audit metadata, revisions/revert, traceable highlights, deterministic concurrent updates, and lightweight importance learning.

## Quick start

```bash
PG_BIN=/Applications/Postgres.app/Contents/Versions/latest/bin
$PG_BIN/createdb -h 127.0.0.1 -p 5432 nightingale
$PG_BIN/psql -h 127.0.0.1 -p 5432 -d nightingale -f db/migrations/001_nightingale.sql
export DATABASE_URL='postgresql://nightingale_app@127.0.0.1:5432/nightingale'
conda env create -f environment.yml  # only needed if the environment does not exist
conda run -n Nightingale python -m unittest discover -s tests -v
conda run -n Nightingale python -m nightingale.demo
```

For the supplied local Postgres.app, the database has already been initialized at port `5432`, and the existing `Nightingale` Conda environment already includes `psycopg`. Copy `.env.example` into your shell environment or configure the same `DATABASE_URL` in your API runner. Postgres.app's `psql` is at `/Applications/Postgres.app/Contents/Versions/latest/bin/psql`; adding that directory to `PATH` is optional.

## Running application

Start the local full-stack application with:

```bash
export DATABASE_URL='postgresql://nightingale_app@127.0.0.1:5432/nightingale'
conda run -n Nightingale python -m nightingale.web
```

Then open [http://localhost:8000](http://localhost:8000). This is a working browser app, not a static mockup: creating a patient creates a database record; creating/editing a note creates PostgreSQL version snapshots; comments and version restores use the same API.

### Local demo sign-in

The login page creates a server-side session in an HttpOnly cookie. API identity is resolved from that session; client-supplied role headers are ignored.

| Role | Username | Password |
|---|---|---|
| Patient | `patient_demo` | `Patient123!` |
| Staff | `staff_demo` | `Staff1234!` |
| Doctor | `doctor_demo` | `Doctor123!` |
| Nurse | `nurse_demo` | `Nurse1234!` |
| Admin | `admin_demo` | `Admin1234!` |
| System | `system_demo` | `System123!` |

These credentials are for the local synthetic demonstration only and must be replaced before deployment.

## Qwen AI-scribe and Glance View

The application uses `Qwen/Qwen2.5-0.5B-Instruct` locally through Transformers for AI-scribed summaries and AI Glance View.

```bash
conda run -n Nightingale python -m nightingale.web
```

Download the Qwen model once through Hugging Face before running the app. The application then uses only the local Hugging Face cache, avoiding model-download latency on clinical requests. The server runs `redact_for_llm()` before inference and creates a distinct system-owned `ai_scribed` timeline entry with a session provenance pointer. AI output is a draft for clinician confirmation—not diagnostic or treatment advice. Qwen’s model card documents Transformers use and lists the model as Apache-2.0 licensed. [Model card](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct)

The server uses CUDA when available and otherwise uses CPU. This is the reliable default for the 0.5B model on the current macOS/PyTorch runtime; the Conda environment includes `accelerate` for compatible Transformers loading.

The demo seeds a synthetic patient timeline and prints the consult Glance View. `PostgresStore` is the application repository; its migration turns on PostgreSQL row-level security (RLS). The in-memory `CareService` is retained solely as a fast, deterministic unit-test double.

## Design choices

- **Server-side authorization:** production requests set database-local `app.clinic_id`, `app.role`, and `app.user_id` inside each transaction; RLS checks these claims in PostgreSQL. The service layer separately limits which sections a role may write. The UI is never the authorization boundary.
- **Eight record types:** `system_generated_event`, `ai_scribe_log`, `doctor_patient_consult`, `nurse_patient_consult`, `ai_patient_consult`, `staff_manual_log`, `clinician_manual_log`, and `patient_facing_log` are the only accepted record types.
- **Clinical subtypes:** doctors may write Doctor–Patient Consults, clinician manual logs, and patient-facing logs; nurses have the equivalent permission with Nurse–Patient Consults. Both clinical subtypes can read the complete clinic-scoped timeline. A consult automatically creates a short system-owned AI scribe log with a trusted link back to its source entry.
- **Protected content:** patients are read-only and receive only `patient_facing_log` records. Staff can read, create, and edit only `staff_manual_log` records. Clinicians cannot edit AI scribe logs or AI–Patient Consults. Clinicians and admins may highlight keywords in any record they can view, select and delete individual highlights from Glance View, or right-click a selected timeline keyword to remove its highlight; the underlying entry is unchanged. Patients and staff cannot create or delete highlights. Admins can read, create, and edit every record type.
- **Revision integrity:** each edit produces an immutable `Version` snapshot and audit record. Revert creates a new version rather than deleting history.
- **Provenance:** a highlight stores `entry_id`, optional character span, and source session pointer. `resolve_provenance()` resolves it to the source-of-truth timeline entry.
- **Privacy:** `redact_for_llm()` removes names, Singapore IC-like IDs and phone numbers before a note may be sent to an LLM. Do not send raw clinical text to an external model. Use TLS in transit and encrypted storage in a production deployment.
- **Latency:** a warm in-memory Glance calculation is measured in `demo.py`; the target is p95 ≤300ms. In production, precompute/cache per-patient glance projections after each write.

## Suggested production deployment

Use a Python API service, Postgres with clinic and role claims enforced through RLS, and an append-only audit table. Store recordings/transcripts separately with short-lived signed URLs. AI requests pass through the redaction pipeline; source session IDs, not raw source payloads, are retained in highlight pointers.

## Project layout

`db/migrations/001_nightingale.sql` is the PostgreSQL schema and RLS policy; `nightingale/postgres.py` is the transaction-scoped PostgreSQL repository; `nightingale/domain.py` contains application data types; `importance.py` contains transparent scoring + feedback weights. Tests map to the requested micro-tests.

## Limitations of this prototype

There is no real authentication or LLM call yet. The development role switcher becomes authenticated session claims in production; client-selected headers must not be trusted outside local development. Database integration tests require a local PostgreSQL URL.
